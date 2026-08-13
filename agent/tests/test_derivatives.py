from __future__ import annotations

import hashlib

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import derivatives
from app.derivatives import derive_pdf_ocr, derive_pending
from app.models import Base, Chunk, Document, FileBlob, Project


def make_image_only_pdf(path) -> None:
    import pymupdf

    source = pymupdf.open()
    source_page = source.new_page(width=900, height=420)
    source_page.insert_text(
        (70, 150),
        "JINGAO ESPORTS OCR TEST 2026",
        fontsize=42,
        color=(0, 0, 0),
    )
    source_page.insert_text(
        (70, 230),
        "TRAINING KNOWLEDGE BASE",
        fontsize=34,
        color=(0, 0, 0),
    )
    image = source_page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)

    scanned = pymupdf.open()
    scanned_page = scanned.new_page(width=900, height=420)
    scanned_page.insert_image(scanned_page.rect, stream=image.tobytes("png"))
    scanned.save(path)


def make_hybrid_pdf(path) -> None:
    import pymupdf

    source = pymupdf.open()
    native_page = source.new_page(width=900, height=420)
    native_page.insert_text(
        (70, 170),
        "NATIVE JINGAO PROJECT HISTORY 2026",
        fontsize=36,
        color=(0, 0, 0),
    )

    image_source = pymupdf.open()
    image_page = image_source.new_page(width=900, height=420)
    image_page.insert_text(
        (70, 170),
        "SCANNED TRAINING RESULT 2026",
        fontsize=38,
        color=(0, 0, 0),
    )
    image = image_page.get_pixmap(
        matrix=pymupdf.Matrix(2, 2),
        alpha=False,
    )
    scanned_page = source.new_page(width=900, height=420)
    scanned_page.insert_image(
        scanned_page.rect,
        stream=image.tobytes("png"),
    )
    source.save(path)


def add_pdf_document(db: Session, source, *, title: str) -> Document:
    payload = source.read_bytes()
    blob = FileBlob(
        content_hash=hashlib.sha256(payload).hexdigest().upper(),
        size_bytes=len(payload),
        source_path=str(source),
    )
    document = Document(
        project=Project(name=f"{title} pipeline test", year=2026),
        file_blob=blob,
        content_hash=blob.content_hash,
        title=title,
        page_count=1,
    )
    db.add(document)
    db.commit()
    return document


def test_image_only_pdf_is_locally_ocr_indexed(tmp_path) -> None:
    source = tmp_path / "scan.pdf"
    make_image_only_pdf(source)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    document = add_pdf_document(db, source, title="scan.pdf")

    result = derive_pdf_ocr(db, document)
    chunks = db.scalars(
        select(Chunk).where(Chunk.document_id == document.id)
    ).all()
    combined_text = " ".join(chunk.text for chunk in chunks).upper()

    assert result["status"] == "ready"
    assert result["pages"] == 1
    assert result["text_pages"] == 1
    assert result["native_text_pages"] == 0
    assert result["ocr_attempted_pages"] == 1
    assert result["ocr_text_pages"] == 1
    assert result["unreadable_pages"] == []
    assert result["chunks"] >= 1
    assert document.citation_basis == "ocr-page"
    assert "JINGAO" in combined_text


def test_hybrid_pdf_preserves_native_text_and_ocrs_missing_page(tmp_path) -> None:
    source = tmp_path / "hybrid.pdf"
    make_hybrid_pdf(source)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    document = add_pdf_document(db, source, title="hybrid.pdf")
    document.page_count = 2
    db.add(
        Chunk(
            document_id=document.id,
            page=1,
            chunk_index=0,
            text="NATIVE JINGAO PROJECT HISTORY 2026",
        )
    )
    db.commit()

    first = derive_pending(db, retry_failed=False)
    second = derive_pending(db, retry_failed=False)
    chunks = db.scalars(
        select(Chunk)
        .where(Chunk.document_id == document.id)
        .order_by(Chunk.page)
    ).all()
    text_by_page = {
        page: " ".join(chunk.text for chunk in chunks if chunk.page == page).upper()
        for page in {chunk.page for chunk in chunks}
    }

    assert len(first) == 1
    assert first[0]["status"] == "ready"
    assert first[0]["native_text_pages"] == 1
    assert first[0]["ocr_attempted_pages"] == 1
    assert first[0]["ocr_text_pages"] == 1
    assert first[0]["unreadable_pages"] == []
    assert second == []
    assert document.citation_basis == "hybrid-page"
    assert "NATIVE JINGAO" in text_by_page[1]
    assert "SCANNED TRAINING" in text_by_page[2]


def test_image_ocr_runs_in_derivative_worker_after_fast_registration(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "event-photo.png"
    source.write_bytes(b"synthetic-image")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    document = add_pdf_document(db, source, title="event-photo.png")
    document.citation_basis = "asset-metadata"
    db.commit()
    monkeypatch.setattr(
        derivatives,
        "parse_image_ocr",
        lambda _source: (
            [(1, "京奥电竞活动现场背景板", None)],
            "ocr-page",
            1,
        ),
    )

    first = derive_pending(db, retry_failed=False)
    second = derive_pending(db, retry_failed=False)
    chunks = db.scalars(
        select(Chunk).where(Chunk.document_id == document.id)
    ).all()

    assert first == [
        {
            "document_id": document.id,
            "kind": "ocr_text",
            "status": "ready",
            "pages": 1,
            "text_pages": 1,
            "chunks": 1,
            "citation_basis": "ocr-page",
        }
    ]
    assert second == []
    assert document.citation_basis == "ocr-page"
    assert [chunk.text for chunk in chunks] == ["京奥电竞活动现场背景板"]
