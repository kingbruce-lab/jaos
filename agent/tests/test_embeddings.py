from __future__ import annotations

from types import SimpleNamespace

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from sqlalchemy.orm import Session

from app import embeddings
from app.embeddings import embedding_text
from app.models import (
    Base,
    Chunk,
    ChunkEmbedding,
    Document,
    FileBlob,
    Project,
)


def embedding_settings(**overrides):
    values = {
        "gateway_base_url": "https://gateway.example/v1",
        "gateway_api_key": "test-only",
        "embedding_model": "embedding-test",
        "embedding_enabled": True,
        "embedding_l3_enabled": False,
        "embedding_batch_size": 8,
        "embedding_concurrency": 4,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_gateway_embedding_shape_is_validated(monkeypatch) -> None:
    monkeypatch.setattr(embeddings, "settings", embedding_settings())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-only"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        vectors = embeddings.request_embeddings(["first", "second"], client=client)
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]


def test_production_embedding_table_uses_pgvector() -> None:
    statement = str(
        CreateTable(ChunkEmbedding.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    assert "VECTOR" in statement


def test_indexer_never_sends_l4_l5_and_defaults_l3_to_local_only(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(embeddings, "settings", embedding_settings())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    captured: list[list[str]] = []

    for index, level in enumerate(("L2", "L3", "L4", "L5"), start=1):
        source = tmp_path / f"{level}.pdf"
        source.write_bytes(b"source")
        project = Project(name=f"{level} project", confidentiality=level)
        blob = FileBlob(
            content_hash=str(index) * 64,
            size_bytes=6,
            source_path=str(source),
        )
        document = Document(
            project=project,
            file_blob=blob,
            content_hash=blob.content_hash,
            title=f"{level}.pdf",
            confidentiality=level,
        )
        db.add(
            Chunk(
                document=document,
                page=1,
                chunk_index=0,
                text=f"{level} private text",
            )
        )
    db.commit()
    for chunk in db.scalars(select(Chunk)).all():
        if chunk.document.confidentiality in {"L3", "L4", "L5"}:
            db.add(
                ChunkEmbedding(
                    chunk_id=chunk.id,
                    model_name="embedding-test",
                    dimensions=3,
                    text_hash="F" * 64,
                    embedding=[0.0, 1.0, 0.0],
                )
            )
    db.commit()

    def fake_requester(texts: list[str]) -> list[list[float]]:
        captured.append(texts)
        return [[1.0, 0.0, 0.0] for _text in texts]

    result = embeddings.index_pending_embeddings(db, requester=fake_requester)
    count = db.scalar(select(func.count(ChunkEmbedding.id)))

    assert result["status"] == "ready"
    assert result["indexed"] == 1
    assert result["skipped_confidential"] == 3
    assert result["purged_by_policy"] == 3
    assert captured == [["文件：L2.pdf\nL2 private text"]]
    assert count == 1


def test_embedding_text_includes_document_title_and_section() -> None:
    project = Project(name="training")
    document = Document(
        project=project,
        content_hash="A" * 64,
        title="培训方案.pptx",
    )
    chunk = Chunk(
        document=document,
        page=3,
        chunk_index=0,
        section="课程体系",
        text="建立分层课程与实训安排",
    )

    assert embedding_text(chunk) == (
        "文件：培训方案.pptx\n"
        "章节：课程体系\n"
        "建立分层课程与实训安排"
    )
