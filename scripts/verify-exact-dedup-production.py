"""Verify exact-duplicate cleanup without printing document contents."""

from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, Document


def family(role: str) -> str:
    return "contract" if role == "contract" else "knowledge"


def main() -> None:
    db = SessionLocal()
    try:
        active = db.scalars(
            select(Document).where(
                Document.knowledge_status.in_(["candidate", "approved", "current"])
            )
        ).all()
        grouped: dict[tuple[str, str, str], list[Document]] = defaultdict(list)
        for document in active:
            grouped[
                (
                    document.content_hash,
                    family(document.role),
                    document.confidentiality,
                )
            ].append(document)
        remaining_active_duplicate_groups = sum(
            1
            for group in grouped.values()
            if len(group) > 1
        )
        latest_audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "exact_duplicates_filtered")
            .order_by(AuditLog.created_at.desc())
        )
        audit_details = (
            json.loads(latest_audit.details_json)
            if latest_audit is not None
            else {}
        )
        title_rows = db.scalars(
            select(Document).where(
                Document.title.in_(
                    [
                        "2026京奥电竞公司介绍.pdf",
                        "2025中国电竞节超级冠军杯-报价V1.xlsx",
                    ]
                )
            )
        ).all()
        title_statuses: dict[str, dict[str, int]] = defaultdict(dict)
        for row in title_rows:
            counts = title_statuses[row.title]
            counts[row.knowledge_status] = counts.get(row.knowledge_status, 0) + 1
        print(
            json.dumps(
                {
                    "filtered_in_latest_cleanup": audit_details.get(
                        "duplicate_count",
                        0,
                    ),
                    "remaining_active_duplicate_groups": (
                        remaining_active_duplicate_groups
                    ),
                    "candidate_documents": sum(
                        1
                        for item in active
                        if item.knowledge_status == "candidate"
                    ),
                    "target_title_statuses": title_statuses,
                    "source_files_deleted": audit_details.get(
                        "source_files_deleted",
                        False,
                    ),
                },
                ensure_ascii=False,
            )
        )
        if remaining_active_duplicate_groups:
            raise RuntimeError("active duplicate groups remain")
    finally:
        db.close()


if __name__ == "__main__":
    main()
