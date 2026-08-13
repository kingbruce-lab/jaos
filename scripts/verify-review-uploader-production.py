"""Verify review uploader attribution without printing employee identities."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.database import SessionLocal
from app.main import _review_uploader_payloads
from app.models import Document


def main() -> None:
    db = SessionLocal()
    try:
        document_ids = list(
            db.scalars(
                select(Document.id).where(
                    Document.knowledge_status.in_(["candidate", "approved"])
                )
            ).all()
        )
        payloads = _review_uploader_payloads(db, document_ids)
        invalid = [
            document_id
            for document_id in document_ids
            if not payloads.get(document_id, {}).get("uploader_name")
            or payloads.get(document_id, {}).get("upload_source")
            not in {"web", "nas"}
        ]
        if invalid:
            raise RuntimeError(f"invalid uploader payloads: {len(invalid)}")
        print(
            json.dumps(
                {
                    "review_documents": len(document_ids),
                    "web_uploads": sum(
                        1
                        for item in payloads.values()
                        if item["upload_source"] == "web"
                    ),
                    "nas_direct_uploads": sum(
                        1
                        for item in payloads.values()
                        if item["upload_source"] == "nas"
                    ),
                    "invalid": len(invalid),
                },
                ensure_ascii=False,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
