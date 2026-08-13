"""Verify production organization-role migration without printing identities."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import User
from app.retrieval import _authorized_levels


VALID_ROLES = {
    "administrative",
    "personnel",
    "business",
    "finance",
    "management",
}


def synthetic(role: str, access_role: str, ceiling: str) -> User:
    return User(
        username=f"verify-{role}",
        display_name=role,
        password_hash="not-persisted",
        role=access_role,
        organization_role=role,
        confidentiality_ceiling=ceiling,
    )


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(User.organization_role, func.count(User.id)).group_by(
                User.organization_role
            )
        ).all()
        distribution = {str(role): count for role, count in rows}
        invalid = sum(
            count for role, count in rows if role not in VALID_ROLES
        )
        administrative = synthetic("administrative", "knowledge_admin", "L5")
        personnel = synthetic("personnel", "employee", "L4")
        if invalid:
            raise RuntimeError(f"invalid organization roles: {invalid}")
        if _authorized_levels(administrative) != ("L1", "L2", "L3"):
            raise RuntimeError("administrative ordinary retrieval cap failed")
        if _authorized_levels(personnel) != ("L1", "L2", "L3"):
            raise RuntimeError("personnel ordinary retrieval cap failed")
        if _authorized_levels(
            administrative,
            include_contracts=True,
        ) != ("L1", "L2", "L3", "L4", "L5"):
            raise RuntimeError("contract archive clearance separation failed")
        print(
            json.dumps(
                {
                    "account_count": sum(distribution.values()),
                    "distribution": distribution,
                    "invalid": invalid,
                    "ordinary_caps": {
                        "administrative": "L3",
                        "personnel": "L3",
                    },
                    "contract_upload_role": "administrative",
                },
                ensure_ascii=False,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
