from __future__ import annotations

import concurrent.futures
import hashlib
import json
import math
from typing import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .models import (
    AuditLog,
    Chunk,
    ChunkEmbedding,
    Document,
    SourceHealth,
)
from .source_integrity import source_is_available


CONFIDENTIALITY_RANK = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}


class EmbeddingServiceError(RuntimeError):
    pass


def embedding_text(chunk: Chunk) -> str:
    """Add stable document context without changing displayed source text."""
    context = [f"文件：{chunk.document.title}"]
    if chunk.section:
        context.append(f"章节：{chunk.section}")
    context.append(chunk.text)
    return "\n".join(context)


def request_embeddings(
    texts: list[str],
    *,
    client: httpx.Client | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    if not settings.gateway_api_key:
        raise EmbeddingServiceError("gateway_key_missing")
    owned_client = client is None
    http_client = client or httpx.Client(timeout=httpx.Timeout(45.0))
    try:
        response = http_client.post(
            f"{settings.gateway_base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.gateway_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.embedding_model,
                "input": texts,
            },
        )
        if response.status_code >= 400:
            raise EmbeddingServiceError(
                f"gateway_http_{response.status_code}"
            )
        payload = response.json()
        rows = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [row.get("embedding") for row in rows]
        if len(vectors) != len(texts):
            raise EmbeddingServiceError("embedding_count_mismatch")
        dimensions = {len(vector) for vector in vectors if isinstance(vector, list)}
        if len(dimensions) != 1 or 0 in dimensions:
            raise EmbeddingServiceError("embedding_dimensions_invalid")
        if any(
            not math.isfinite(float(value))
            for vector in vectors
            for value in vector
        ):
            raise EmbeddingServiceError("embedding_contains_non_finite_value")
        return [[float(value) for value in vector] for vector in vectors]
    except httpx.HTTPError as exc:
        raise EmbeddingServiceError("gateway_unreachable") from exc
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EmbeddingServiceError("gateway_response_invalid") from exc
    finally:
        if owned_client:
            http_client.close()


def embedding_allowed(document: Document) -> bool:
    document_rank = CONFIDENTIALITY_RANK.get(document.confidentiality, 99)
    project_rank = CONFIDENTIALITY_RANK.get(document.project.confidentiality, 99)
    required_rank = max(document_rank, project_rank)
    if required_rank >= CONFIDENTIALITY_RANK["L4"]:
        return False
    if required_rank == CONFIDENTIALITY_RANK["L3"]:
        return settings.embedding_l3_enabled
    return required_rank <= CONFIDENTIALITY_RANK["L2"]


def index_pending_embeddings(
    db: Session,
    *,
    force: bool = False,
    requester: Callable[[list[str]], list[list[float]]] = request_embeddings,
) -> dict:
    if not settings.embedding_enabled:
        return {
            "status": "disabled",
            "model": settings.embedding_model,
            "indexed": 0,
            "skipped_confidential": 0,
            "skipped_source_missing": 0,
        }
    if not settings.gateway_api_key:
        return {
            "status": "blocked",
            "reason": "gateway_key_missing",
            "model": settings.embedding_model,
            "indexed": 0,
        }

    chunks = db.scalars(
        select(Chunk).options(
            joinedload(Chunk.document).joinedload(Document.project),
            joinedload(Chunk.document).joinedload(Document.file_blob),
        )
    ).all()
    existing_rows = db.scalars(
        select(ChunkEmbedding).where(
            ChunkEmbedding.model_name == settings.embedding_model
        )
    ).all()
    existing = {row.chunk_id: row for row in existing_rows}
    source_health = {
        row.content_hash: row
        for row in db.scalars(select(SourceHealth)).all()
    }
    candidates: list[tuple[Chunk, str, str]] = []
    policy_allowed_chunk_ids: set[str] = set()
    skipped_confidential = 0
    skipped_source_missing = 0
    unchanged = 0
    for chunk in chunks:
        document = chunk.document
        if (
            not source_is_available(
                document.file_blob,
                source_health.get(document.content_hash),
            )
        ):
            skipped_source_missing += 1
            continue
        if not embedding_allowed(document):
            skipped_confidential += 1
            continue
        policy_allowed_chunk_ids.add(chunk.id)
        vector_text = embedding_text(chunk)
        text_hash = hashlib.sha256(vector_text.encode("utf-8")).hexdigest()
        current = existing.get(chunk.id)
        if current and current.text_hash == text_hash and not force:
            unchanged += 1
            continue
        candidates.append((chunk, text_hash, vector_text))

    purged = 0
    for row in existing_rows:
        if row.chunk_id not in policy_allowed_chunk_ids:
            db.delete(row)
            existing.pop(row.chunk_id, None)
            purged += 1
    if purged:
        db.commit()

    indexed = 0
    outbound_characters = 0
    batch_size = settings.embedding_batch_size
    concurrency = settings.embedding_concurrency
    try:
        window_size = batch_size * concurrency
        for window_start in range(0, len(candidates), window_size):
            window = candidates[window_start:window_start + window_size]
            batches = [
                window[offset:offset + batch_size]
                for offset in range(0, len(window), batch_size)
            ]

            def embed_batch(batch):
                texts = [
                    vector_text
                    for _chunk, _text_hash, vector_text in batch
                ]
                return requester(texts)

            if len(batches) == 1:
                vector_batches = [embed_batch(batches[0])]
            else:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(concurrency, len(batches))
                ) as executor:
                    vector_batches = list(executor.map(embed_batch, batches))

            for batch, vectors in zip(batches, vector_batches, strict=True):
                outbound_characters += sum(
                    len(vector_text)
                    for _chunk, _text_hash, vector_text in batch
                )
                if len(vectors) != len(batch):
                    raise EmbeddingServiceError("embedding_count_mismatch")
                for (chunk, text_hash, _vector_text), vector in zip(
                    batch,
                    vectors,
                    strict=True,
                ):
                    row = existing.get(chunk.id)
                    if row:
                        row.text_hash = text_hash
                        row.dimensions = len(vector)
                        row.embedding = vector
                    else:
                        row = ChunkEmbedding(
                            chunk_id=chunk.id,
                            model_name=settings.embedding_model,
                            dimensions=len(vector),
                            text_hash=text_hash,
                            embedding=vector,
                        )
                        db.add(row)
                        existing[chunk.id] = row
                    indexed += 1
                db.commit()
    except EmbeddingServiceError as exc:
        db.rollback()
        return {
            "status": "failed",
            "reason": str(exc),
            "model": settings.embedding_model,
            "indexed": indexed,
            "remaining": len(candidates) - indexed,
            "outbound_characters": outbound_characters,
        }

    db.add(
        AuditLog(
            user_id=None,
            action="embedding_index",
            details_json=json.dumps(
                {
                    "model": settings.embedding_model,
                    "indexed": indexed,
                    "unchanged": unchanged,
                    "skipped_confidential": skipped_confidential,
                    "skipped_source_missing": skipped_source_missing,
                    "purged_by_policy": purged,
                    "outbound_characters": outbound_characters,
                    "concurrency": concurrency,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return {
        "status": "ready",
        "model": settings.embedding_model,
        "indexed": indexed,
        "unchanged": unchanged,
        "skipped_confidential": skipped_confidential,
        "skipped_source_missing": skipped_source_missing,
        "purged_by_policy": purged,
        "outbound_characters": outbound_characters,
        "concurrency": concurrency,
    }
