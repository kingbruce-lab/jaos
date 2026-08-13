import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.config import settings
from app.evaluation import (
    EVALUATION_KNOWLEDGE_STATUSES,
    _build_retrieval_cases,
    _probe_user,
)
from app.models import Chunk, Document, SourceHealth
from app.retrieval import search
from app.source_integrity import source_is_available


report_path = Path(settings.evaluation_dir) / "latest.json"
report = json.loads(report_path.read_text(encoding="utf-8"))
failed_ids = {
    str(item["id"])
    for item in report.get("failures", [])
    if item.get("kind") == "page_citation"
}
with SessionLocal() as db:
    rows = db.scalars(
        select(Chunk)
        .options(
            joinedload(Chunk.document).joinedload(Document.project),
            joinedload(Chunk.document).joinedload(Document.file_blob),
        )
        .order_by(Chunk.document_id, Chunk.page, Chunk.chunk_index)
    ).all()
    health_by_hash = {
        row.content_hash: row
        for row in db.scalars(select(SourceHealth)).all()
    }
    available = [
        chunk
        for chunk in rows
        if chunk.document.file_blob
        and source_is_available(
            chunk.document.file_blob,
            health_by_hash.get(chunk.document.content_hash),
        )
        and chunk.document.knowledge_status in EVALUATION_KNOWLEDGE_STATUSES
    ]
    cases = [
        case for case in _build_retrieval_cases(available)
        if case["id"] in failed_ids
    ]
    user = _probe_user(ceiling="L4", role="founder")
    diagnostics = []
    for case in cases:
        result = search(
            db,
            user=user,
            query=case["query"],
            requested_scope="history",
            requested_retrieval="exact",
            limit=8,
            audit=False,
            generate=False,
        )
        diagnostics.append({
            "id": case["id"],
            "query": case["query"],
            "expected_document_id": case["expected_document_id"],
            "expected_page": case["expected_page"],
            "citations": [
                {
                    "document_id": item["document_id"],
                    "page": item["page"],
                }
                for item in result["citations"]
            ],
        })

print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
