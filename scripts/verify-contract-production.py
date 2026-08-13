from __future__ import annotations

import json

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select

from app.auth import create_session, revoke_session
from app.config import settings
from app.contracts import CONTRACT_CATEGORIES, CONTRACT_DOMAINS, ensure_contract_layout
from app.database import SessionLocal
from app.main import _can_upload_contracts, _contract_category_for_user
from app.models import Chunk, ChunkEmbedding, Document, Project, User


def verify_role_matrix() -> dict[str, list[str]]:
    expected = {
        "administrative": ["administrative", "business"],
        "personnel": ["personnel"],
        "business": [],
        "finance": [],
        "management": list(CONTRACT_CATEGORIES),
    }
    actual: dict[str, list[str]] = {}
    for organization_role, expected_categories in expected.items():
        actor = User(
            username=f"verify-{organization_role}",
            display_name="生产权限验收",
            password_hash="not-used",
            role="employee",
            organization_role=organization_role,
            confidentiality_ceiling="L5",
            active=True,
        )
        allowed: list[str] = []
        for category in CONTRACT_CATEGORIES:
            try:
                _contract_category_for_user(actor, category)
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
            else:
                allowed.append(category)
        if allowed != expected_categories:
            raise RuntimeError(
                f"contract_role_matrix_mismatch:{organization_role}:{allowed}"
            )
        actual[organization_role] = allowed
        expected_upload = organization_role in {"administrative", "management"}
        if _can_upload_contracts(actor) is not expected_upload:
            raise RuntimeError(
                f"contract_upload_matrix_mismatch:{organization_role}"
            )

    management_l4 = User(
        username="verify-management-l4",
        display_name="生产权限验收",
        password_hash="not-used",
        role="founder",
        organization_role="management",
        confidentiality_ceiling="L4",
        active=True,
    )
    if _can_upload_contracts(management_l4):
        raise RuntimeError("contract_upload_matrix_mismatch:management_l4")
    return actual


def main() -> None:
    role_matrix = verify_role_matrix()
    with SessionLocal() as db:
        founder = db.scalar(select(User).where(User.role == "founder"))
        if founder is None or founder.confidentiality_ceiling != "L5":
            raise RuntimeError("founder_l5_policy_not_applied")
        token, _expires_at = create_session(db, founder)
        try:
            client = httpx.Client(
                base_url="http://127.0.0.1:8000",
                headers={"authorization": f"Bearer {token}"},
                timeout=20,
            )
            categories_response = client.get("/v1/contracts/categories")
            categories_response.raise_for_status()
            categories = categories_response.json()
            if {item["key"] for item in categories} != set(CONTRACT_CATEGORIES):
                raise RuntimeError("contract_category_visibility_incomplete")

            list_statuses = {}
            for category in CONTRACT_CATEGORIES:
                response = client.get(
                    "/v1/contracts",
                    params={"category": category},
                )
                response.raise_for_status()
                list_statuses[category] = response.status_code

            search_response = client.post(
                "/v1/contracts/search",
                json={
                    "category": "executive_office",
                    "query": "生产验收不存在合同",
                    "limit": 3,
                },
            )
            search_response.raise_for_status()
            search_payload = search_response.json()
            if search_payload.get("local_only") is not True:
                raise RuntimeError("contract_search_not_local_only")

            contract_embeddings = db.scalar(
                select(func.count(ChunkEmbedding.id))
                .join(ChunkEmbedding.chunk)
                .join(Chunk.document)
                .join(Document.project)
                .where(Project.domain.in_(CONTRACT_DOMAINS))
            ) or 0
            high_embeddings = db.scalar(
                select(func.count(ChunkEmbedding.id))
                .join(ChunkEmbedding.chunk)
                .join(Chunk.document)
                .where(Document.confidentiality.in_(("L4", "L5")))
            ) or 0
            if contract_embeddings or high_embeddings:
                raise RuntimeError("high_confidentiality_embedding_detected")

            layout = ensure_contract_layout(settings.knowledge_root)
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "founder_ceiling": founder.confidentiality_ceiling,
                        "category_count": len(categories),
                        "list_statuses": list_statuses,
                        "search_local_only": True,
                        "search_result_count": len(search_payload["results"]),
                        "contract_embeddings": contract_embeddings,
                        "high_embeddings": high_embeddings,
                        "directories_ready": all(path.is_dir() for path in layout.values()),
                        "role_matrix": role_matrix,
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            revoke_session(db, token)


if __name__ == "__main__":
    main()
