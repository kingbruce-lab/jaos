from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import AGENT_ROOT, settings
from .models import Chunk, Document, DocumentArtifact
from .parsers import chunk_text, clean_text, parse_image_ocr, parse_pdf
from .source_integrity import file_sha256, verify_and_record


PDF_NATIVE_TEXT_MIN_CHARS = 12
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _artifact(db: Session, document: Document, kind: str) -> DocumentArtifact:
    artifact = db.scalar(
        select(DocumentArtifact).where(
            DocumentArtifact.document_id == document.id,
            DocumentArtifact.kind == kind,
        )
    )
    if artifact:
        return artifact
    artifact = DocumentArtifact(document_id=document.id, kind=kind)
    db.add(artifact)
    db.flush()
    return artifact


def _derived_dir(document: Document) -> Path:
    target = settings.data_dir / "derived" / document.content_hash
    target.mkdir(parents=True, exist_ok=True)
    return target


def _source(db: Session, document: Document) -> Path:
    if not document.file_blob:
        raise FileNotFoundError("source_record_missing")
    source = Path(document.file_blob.source_path)
    health = verify_and_record(db, document.file_blob)
    if health.status != "verified":
        raise FileNotFoundError(
            f"source_integrity_{health.status}"
        )
    return source


def _replace_chunks(
    db: Session,
    document: Document,
    pages: list[tuple[int, str, str | None]],
) -> int:
    db.execute(delete(Chunk).where(Chunk.document_id == document.id))
    chunk_index = 0
    for page, text, section in pages:
        for value in chunk_text(text):
            db.add(
                Chunk(
                    document_id=document.id,
                    page=page,
                    chunk_index=chunk_index,
                    section=section,
                    text=value,
                )
            )
            chunk_index += 1
    return chunk_index


def _meaningful_character_count(text: str) -> int:
    return len(re.sub(r"\s+", "", clean_text(text)))


def _merge_native_and_ocr_text(native_text: str, ocr_text: str) -> str:
    native = clean_text(native_text)
    ocr = clean_text(ocr_text)
    if not native:
        return ocr
    if not ocr:
        return native

    def signature(value: str) -> str:
        return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()

    native_signature = signature(native)
    ocr_signature = signature(ocr)
    if native_signature and native_signature in ocr_signature:
        return ocr
    if ocr_signature and ocr_signature in native_signature:
        return native

    seen = {
        signature(line)
        for line in native.splitlines()
        if signature(line)
    }
    additions: list[str] = []
    for line in ocr.splitlines():
        line_signature = signature(line)
        if line_signature and line_signature not in seen:
            seen.add(line_signature)
            additions.append(line)
    return clean_text("\n".join([native, *additions]))


def convert_docx_to_pdf(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    soffice = (
        os.getenv("JINGAO_SOFFICE_PATH")
        or shutil.which("soffice")
        or shutil.which("libreoffice")
    )
    if soffice:
        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output.parent),
                str(source),
            ],
            check=True,
            timeout=180,
            capture_output=True,
        )
        generated = output.parent / f"{source.stem}.pdf"
        if not generated.is_file():
            raise RuntimeError("libreoffice_output_missing")
        if generated != output:
            generated.replace(output)
        return

    if os.name == "nt":
        script = AGENT_ROOT.parent / "scripts" / "convert-docx-word.ps1"
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-SourcePath",
                str(source),
                "-OutputPath",
                str(output),
            ],
            check=True,
            timeout=180,
            capture_output=True,
        )
        if output.is_file():
            return
    raise RuntimeError("docx_converter_unavailable")


def convert_pptx_to_pdf(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    soffice = (
        os.getenv("JINGAO_SOFFICE_PATH")
        or shutil.which("soffice")
        or shutil.which("libreoffice")
    )
    if soffice:
        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output.parent),
                str(source),
            ],
            check=True,
            timeout=180,
            capture_output=True,
        )
        generated = output.parent / f"{source.stem}.pdf"
        if not generated.is_file():
            raise RuntimeError("libreoffice_output_missing")
        if generated != output:
            generated.replace(output)
        return

    if os.name == "nt":
        script = AGENT_ROOT.parent / "scripts" / "convert-pptx-powerpoint.ps1"
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-SourcePath",
                str(source),
                "-OutputPath",
                str(output),
            ],
            check=True,
            timeout=180,
            capture_output=True,
        )
        if output.is_file():
            return
    raise RuntimeError("pptx_converter_unavailable")


def derive_docx_reference(db: Session, document: Document) -> dict:
    artifact = _artifact(db, document, "reference_pdf")
    try:
        source = _source(db, document)
        output = _derived_dir(document) / "reference.pdf"
        convert_docx_to_pdf(source, output)
        pages, _basis, page_count = parse_pdf(output)
        if not pages:
            raise RuntimeError("reference_pdf_has_no_text")
        chunks = _replace_chunks(db, document, pages)
        document.page_count = page_count
        document.citation_basis = "reference-pdf"
        artifact.path = str(output)
        artifact.content_hash = file_sha256(output)
        artifact.page_count = page_count
        artifact.status = "ready"
        artifact.error_code = None
        db.commit()
        return {
            "document_id": document.id,
            "kind": artifact.kind,
            "status": "ready",
            "pages": page_count,
            "chunks": chunks,
        }
    except Exception as exc:
        db.rollback()
        artifact = _artifact(db, document, "reference_pdf")
        artifact.status = "failed"
        artifact.error_code = str(exc)[:80]
        db.commit()
        return {
            "document_id": document.id,
            "kind": artifact.kind,
            "status": "failed",
            "error": artifact.error_code,
        }


def derive_pptx_reference(db: Session, document: Document) -> dict:
    artifact = _artifact(db, document, "reference_pdf")
    try:
        import pymupdf

        source = _source(db, document)
        output = _derived_dir(document) / "reference.pdf"
        convert_pptx_to_pdf(source, output)
        with pymupdf.open(output) as pdf:
            page_count = len(pdf)
        if page_count < 1:
            raise RuntimeError("reference_pdf_has_no_pages")
        artifact.path = str(output)
        artifact.content_hash = file_sha256(output)
        artifact.page_count = page_count
        artifact.status = "ready"
        artifact.error_code = None
        db.commit()
        return {
            "document_id": document.id,
            "kind": artifact.kind,
            "status": "ready",
            "pages": page_count,
            "chunks": len(document.chunks),
        }
    except Exception as exc:
        db.rollback()
        artifact = _artifact(db, document, "reference_pdf")
        artifact.status = "failed"
        artifact.error_code = str(exc)[:80]
        db.commit()
        return {
            "document_id": document.id,
            "kind": artifact.kind,
            "status": "failed",
            "error": artifact.error_code,
        }


def derive_pdf_ocr(db: Session, document: Document, scale: float = 2.0) -> dict:
    artifact = _artifact(db, document, "ocr_text")
    try:
        import pymupdf
        from rapidocr import RapidOCR

        source = _source(db, document)
        native_pages, _basis, parsed_page_count = parse_pdf(source)
        native_by_page = {
            page_number: clean_text(text)
            for page_number, text, _section in native_pages
        }
        ocr_by_page: dict[int, str] = {}
        confidences: list[float] = []
        attempted_pages: list[int] = []
        with pymupdf.open(source) as pdf:
            page_count = len(pdf)
            if parsed_page_count != page_count:
                raise RuntimeError("pdf_page_count_mismatch")
            attempted_pages = [
                page_number
                for page_number in range(1, page_count + 1)
                if _meaningful_character_count(
                    native_by_page.get(page_number, "")
                ) < PDF_NATIVE_TEXT_MIN_CHARS
            ]
            engine = RapidOCR() if attempted_pages else None
            for page_number in attempted_pages:
                page = pdf[page_number - 1]
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(scale, scale),
                    alpha=False,
                )
                result = engine(pixmap.tobytes("png"))
                texts = list(getattr(result, "txts", None) or [])
                scores = [
                    float(value)
                    for value in (getattr(result, "scores", None) or [])
                ]
                accepted = [
                    text
                    for text, score in zip(texts, scores, strict=False)
                    if score >= 0.45 and clean_text(text)
                ]
                if accepted:
                    ocr_by_page[page_number] = clean_text(
                        "\n".join(accepted)
                    )
                    confidences.extend(
                        score for score in scores if score >= 0.45
                    )

        pages: list[tuple[int, str, str | None]] = []
        for page_number in range(1, page_count + 1):
            text = _merge_native_and_ocr_text(
                native_by_page.get(page_number, ""),
                ocr_by_page.get(page_number, ""),
            )
            if text:
                pages.append((page_number, text, None))
        if not pages:
            raise RuntimeError("ocr_no_text")
        chunks = _replace_chunks(db, document, pages)
        native_text_pages = {
            page_number
            for page_number, text in native_by_page.items()
            if clean_text(text)
        }
        ocr_text_pages = set(ocr_by_page)
        if native_text_pages and ocr_text_pages:
            citation_basis = "hybrid-page"
        elif ocr_text_pages:
            citation_basis = "ocr-page"
        else:
            citation_basis = "source-page"
        document.page_count = page_count
        document.citation_basis = citation_basis
        artifact.path = None
        artifact.content_hash = None
        artifact.page_count = page_count
        artifact.status = "ready"
        artifact.error_code = None
        db.commit()
        return {
            "document_id": document.id,
            "kind": artifact.kind,
            "status": "ready",
            "pages": page_count,
            "text_pages": len(pages),
            "native_text_pages": len(native_text_pages),
            "ocr_attempted_pages": len(attempted_pages),
            "ocr_text_pages": len(ocr_text_pages),
            "unreadable_pages": sorted(
                set(range(1, page_count + 1))
                - {page_number for page_number, _text, _section in pages}
            ),
            "chunks": chunks,
            "average_confidence": (
                round(sum(confidences) / len(confidences), 4)
                if confidences
                else None
            ),
        }
    except Exception as exc:
        db.rollback()
        artifact = _artifact(db, document, "ocr_text")
        artifact.status = "failed"
        artifact.error_code = str(exc)[:80]
        db.commit()
        return {
            "document_id": document.id,
            "kind": artifact.kind,
            "status": "failed",
            "error": artifact.error_code,
        }


def derive_image_ocr(db: Session, document: Document) -> dict:
    artifact = _artifact(db, document, "ocr_text")
    try:
        source = _source(db, document)
        pages, citation_basis, page_count = parse_image_ocr(source)
        chunks = _replace_chunks(db, document, pages)
        document.page_count = page_count
        document.citation_basis = citation_basis
        artifact.path = None
        artifact.content_hash = None
        artifact.page_count = page_count
        artifact.status = "ready"
        artifact.error_code = None
        db.commit()
        return {
            "document_id": document.id,
            "kind": artifact.kind,
            "status": "ready",
            "pages": page_count,
            "text_pages": len(pages),
            "chunks": chunks,
            "citation_basis": citation_basis,
        }
    except Exception as exc:
        db.rollback()
        artifact = _artifact(db, document, "ocr_text")
        artifact.status = "failed"
        artifact.error_code = str(exc)[:80]
        db.commit()
        return {
            "document_id": document.id,
            "kind": artifact.kind,
            "status": "failed",
            "error": artifact.error_code,
        }


def derive_pending(
    db: Session,
    *,
    retry_failed: bool = True,
) -> list[dict]:
    documents = db.scalars(select(Document)).all()
    results: list[dict] = []
    for document in documents:
        artifact_status = {
            artifact.kind: artifact.status for artifact in document.artifacts
        }
        source_suffix = (
            Path(document.file_blob.source_path).suffix.lower()
            if document.file_blob
            else ""
        )
        def should_attempt(kind: str) -> bool:
            status = artifact_status.get(kind)
            return status != "ready" and (retry_failed or status != "failed")

        if (
            source_suffix in {".doc", ".docm", ".docx"}
            and document.citation_basis != "reference-pdf"
            and should_attempt("reference_pdf")
        ):
            results.append(derive_docx_reference(db, document))
        elif (
            source_suffix == ".pptx"
            and should_attempt("reference_pdf")
        ):
            results.append(derive_pptx_reference(db, document))
        elif (
            source_suffix == ".pdf"
            and document.page_count > 0
            and should_attempt("ocr_text")
        ):
            results.append(derive_pdf_ocr(db, document))
        elif (
            source_suffix in IMAGE_SUFFIXES
            and should_attempt("ocr_text")
        ):
            results.append(derive_image_ocr(db, document))
    return results
