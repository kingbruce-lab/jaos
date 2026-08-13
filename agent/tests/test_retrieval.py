from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import retrieval
from app.models import (
    AuditLog,
    Base,
    Chunk,
    ChunkEmbedding,
    Document,
    FileBlob,
    Project,
    User,
)
from app.generation import GenerationResult, GenerationServiceError
from app.retrieval import choose_scope, query_terms, search


def test_administrative_and_personnel_business_search_is_capped_at_l3() -> None:
    administrative = User(
        username="administrative",
        display_name="行政",
        password_hash="x",
        role="knowledge_admin",
        organization_role="administrative",
        confidentiality_ceiling="L5",
    )
    personnel = User(
        username="personnel",
        display_name="人事",
        password_hash="x",
        role="employee",
        organization_role="personnel",
        confidentiality_ceiling="L4",
    )

    assert retrieval._authorized_levels(administrative) == ("L1", "L2", "L3")
    assert retrieval._authorized_levels(personnel) == ("L1", "L2", "L3")
    assert retrieval._authorized_levels(
        administrative,
        include_contracts=True,
    ) == ("L1", "L2", "L3", "L4", "L5")


def seeded_db(source_path: str) -> tuple[Session, User, User]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    founder = User(
        username="founder",
        display_name="创始人",
        password_hash="x",
        role="founder",
        confidentiality_ceiling="L4",
    )
    employee = User(
        username="employee",
        display_name="员工",
        password_hash="x",
        role="employee",
        confidentiality_ceiling="L2",
    )
    project = Project(
        name="高校电竞培训测试项目",
        year=2026,
        confidentiality="L3",
        knowledge_status="approved",
    )
    source = Path(source_path)
    payload = source.read_bytes() if source.is_file() else b"test"
    content_hash = hashlib.sha256(payload).hexdigest().upper()
    blob = FileBlob(
        content_hash=content_hash,
        size_bytes=len(payload),
        source_path=source_path,
    )
    document = Document(
        project=project,
        content_hash=blob.content_hash,
        title="高校电竞培训测试方案.pdf",
        confidentiality="L3",
        knowledge_status="approved",
        page_count=3,
    )
    chunk = Chunk(
        document=document,
        page=2,
        chunk_index=0,
        text="本项目面向高校学生开展电竞课程与实训。",
    )
    db.add_all([founder, employee, project, blob, document, chunk])
    db.commit()
    return db, founder, employee


def test_query_classifier_uses_current_for_company_facts() -> None:
    assert choose_scope("最新公司介绍", "auto") == ("current", "current-fact-hint")
    assert choose_scope("过去做过哪些高校项目", "auto")[0] == "history"


def test_chinese_query_generates_bigrams() -> None:
    terms = query_terms("高校电竞培训")
    assert "高校电竞培训" in terms
    assert "电竞" in terms


def test_founder_can_find_approved_history_with_page_citation(tmp_path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    result = search(
        db,
        user=founder,
        query="高校电竞培训",
        requested_scope="history",
    )
    assert len(result["results"]) == 1
    assert result["results"][0]["page"] == 2
    assert result["results"][0]["knowledge_status"] == "approved"
    assert "已确认的历史资料" in result["answer"]


def test_search_groups_multiple_matching_pages_from_the_same_document(
    tmp_path,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    document = db.scalar(select(Document))
    db.add_all([
        Chunk(
            document=document,
            page=1,
            chunk_index=1,
            text="高校电竞培训项目的课程背景。",
        ),
        Chunk(
            document=document,
            page=3,
            chunk_index=2,
            text="高校电竞培训项目的结项结果。",
        ),
    ])
    db.commit()

    result = search(
        db,
        user=founder,
        query="高校电竞培训",
        requested_scope="history",
        generate=False,
    )

    assert len(result["results"]) == 1
    assert set(result["results"][0]["matched_pages"]) == {1, 2, 3}
    assert {(item["document_id"], item["page"]) for item in result["citations"]} == {
        (document.id, 1),
        (document.id, 2),
        (document.id, 3),
    }
    assert "找到 1 条" in result["answer"]


def test_source_availability_is_checked_once_per_document(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    document = db.scalar(select(Document))
    db.add(
        Chunk(
            document=document,
            page=3,
            chunk_index=1,
            text="second matching page",
        )
    )
    db.commit()
    calls = 0
    original = retrieval.source_is_available

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(retrieval, "source_is_available", counted)
    result = search(
        db,
        user=founder,
        query="second matching page",
        requested_scope="history",
        requested_retrieval="exact",
        generate=False,
    )

    assert result["results"]
    assert calls == 1


def test_candidate_is_not_searchable_until_confirmed(tmp_path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    document = db.scalar(select(Document))
    document.knowledge_status = "candidate"
    db.commit()

    result = search(
        db,
        user=founder,
        query="高校电竞培训",
        requested_scope="history",
    )

    assert result["results"] == []
    assert result["answer"] == "资料中未找到"


def test_current_final_bonus_never_creates_an_unrelated_exact_result(tmp_path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    document = db.scalar(select(Document))
    document.knowledge_status = "current"
    document.is_final = True
    document.project.knowledge_status = "current"
    db.commit()

    result = search(
        db,
        user=founder,
        query="木星电竞馆2041租赁合同编号JUPITER41",
        requested_scope="current",
        requested_retrieval="exact",
        generate=False,
    )

    assert result["results"] == []
    assert result["answer"] == "资料中未找到"


def test_permission_filter_runs_before_results(tmp_path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, _founder, employee = seeded_db(str(source))
    result = search(
        db,
        user=employee,
        query="高校电竞培训",
        requested_scope="history",
    )
    assert result["results"] == []
    assert result["answer"] == "资料中未找到"
    assert result["denied_count"] == 0
    assert result["unavailable_count"] == 0


def test_unauthorized_chunks_never_enter_lexical_scoring(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, _founder, employee = seeded_db(str(source))

    def fail_if_scored(*_args, **_kwargs):
        raise AssertionError("unauthorized chunk reached lexical scoring")

    monkeypatch.setattr(retrieval, "_score", fail_if_scored)
    result = search(
        db,
        user=employee,
        query="高校电竞培训",
        requested_scope="history",
    )

    assert result["results"] == []
    assert result["denied_count"] == 0


def test_cross_category_chunks_are_visible_when_confidentiality_allows(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, _founder, employee = seeded_db(str(source))
    document = db.scalar(select(Document))
    document.confidentiality = "L2"
    document.project.confidentiality = "L2"
    document.project.domain = "team"
    employee.departments_json = '["training"]'
    db.commit()

    result = search(
        db,
        user=employee,
        query="高校电竞培训",
        requested_scope="history",
    )

    assert result["results"]
    assert result["results"][0]["domain"] == "team"


def test_missing_source_is_not_searchable(tmp_path) -> None:
    db, founder, _employee = seeded_db(str(tmp_path / "missing.pdf"))
    result = search(
        db,
        user=founder,
        query="高校电竞培训",
        requested_scope="history",
    )
    assert result["results"] == []
    assert result["answer"] == "资料中未找到"
    assert result["unavailable_count"] > 0


def test_hybrid_retrieval_can_find_semantic_only_match(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    chunk = db.scalar(select(Chunk))
    db.add(
        ChunkEmbedding(
            chunk_id=chunk.id,
            model_name="embedding-test",
            dimensions=2,
            text_hash="D" * 64,
            embedding=[1.0, 0.0],
        )
    )
    db.commit()
    monkeypatch.setattr(
        retrieval,
        "settings",
        SimpleNamespace(
            embedding_enabled=True,
            gateway_api_key="test-only",
            embedding_model="embedding-test",
        ),
    )
    monkeypatch.setattr(
        retrieval,
        "request_embeddings",
        lambda _texts: [[1.0, 0.0]],
    )

    result = search(
        db,
        user=founder,
        query="career-growth",
        requested_scope="history",
        requested_retrieval="hybrid",
    )

    assert result["retrieval_mode"] == "hybrid"
    assert len(result["results"]) == 1
    assert result["results"][0]["score_breakdown"]["lexical"] == 0
    assert result["results"][0]["score_breakdown"]["semantic"] == 1.0


def test_legacy_l4_embedding_is_never_used(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    document = db.scalar(select(Document))
    document.confidentiality = "L4"
    document.project.confidentiality = "L4"
    chunk = db.scalar(select(Chunk))
    db.add(
        ChunkEmbedding(
            chunk_id=chunk.id,
            model_name="embedding-test",
            dimensions=2,
            text_hash="E" * 64,
            embedding=[1.0, 0.0],
        )
    )
    db.commit()
    monkeypatch.setattr(
        retrieval,
        "settings",
        SimpleNamespace(
            embedding_enabled=True,
            gateway_api_key="test-only",
            embedding_model="embedding-test",
        ),
    )
    monkeypatch.setattr(
        retrieval,
        "request_embeddings",
        lambda _texts: [[1.0, 0.0]],
    )

    result = search(
        db,
        user=founder,
        query="semantic-only",
        requested_scope="history",
        requested_retrieval="semantic",
    )

    assert result["results"] == []


def test_semantic_failure_degrades_to_exact_without_losing_citations(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    chunk = db.scalar(select(Chunk))
    db.add(
        ChunkEmbedding(
            chunk_id=chunk.id,
            model_name="embedding-test",
            dimensions=2,
            text_hash="G" * 64,
            embedding=[1.0, 0.0],
        )
    )
    db.commit()
    monkeypatch.setattr(
        retrieval,
        "settings",
        SimpleNamespace(
            embedding_enabled=True,
            gateway_api_key="test-only",
            embedding_model="embedding-test",
        ),
    )

    def unavailable(_texts):
        raise retrieval.EmbeddingServiceError("gateway_unreachable")

    monkeypatch.setattr(retrieval, "request_embeddings", unavailable)
    result = search(
        db,
        user=founder,
        query="高校 课程 实训",
        requested_scope="history",
        requested_retrieval="hybrid",
    )

    assert result["retrieval_mode"] == "exact"
    assert result["retrieval_degraded"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["page"] == 2


def test_llm_generation_uses_authorized_evidence_and_is_audited(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    document = db.scalar(select(Document))
    document.confidentiality = "L2"
    document.project.confidentiality = "L2"
    document.knowledge_status = "current"
    document.project.knowledge_status = "current"
    db.commit()
    captured = {}

    monkeypatch.setattr(
        retrieval,
        "settings",
        SimpleNamespace(
            embedding_enabled=False,
            gateway_api_key="test-only",
            embedding_model="embedding-test",
            llm_enabled=True,
        ),
    )

    def generated(query, items, *, founder):
        captured["query"] = query
        captured["items"] = items
        captured["founder"] = founder
        return GenerationResult(
            answer="项目面向高校学生开展电竞课程与实训 [S1]。",
            model="grok-test",
            fallback_used=False,
            evidence_document_ids=[document.id],
            outbound_characters=42,
        )

    monkeypatch.setattr(retrieval, "generate_grounded_answer", generated)
    result = search(
        db,
        user=founder,
        query="高校电竞培训",
        requested_scope="current",
    )
    generation_audit = db.scalar(
        select(AuditLog).where(AuditLog.action == "llm_generation")
    )

    assert result["generation_mode"] == "llm"
    assert result["generation_model"] == "grok-test"
    assert result["generation_degraded"] is False
    assert result["answer"].endswith("[S1]。")
    assert captured["founder"] is True
    assert captured["items"][0].document_id == document.id
    assert generation_audit is not None
    assert json.loads(generation_audit.document_ids_json) == [document.id]
    assert "高校电竞培训" not in generation_audit.details_json


def test_llm_failure_keeps_local_results_and_marks_degraded(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    document = db.scalar(select(Document))
    document.confidentiality = "L2"
    document.project.confidentiality = "L2"
    db.commit()
    monkeypatch.setattr(
        retrieval,
        "settings",
        SimpleNamespace(
            embedding_enabled=False,
            gateway_api_key="test-only",
            embedding_model="embedding-test",
            llm_enabled=True,
        ),
    )

    def unavailable(*_args, **_kwargs):
        raise GenerationServiceError("gateway_unreachable")

    monkeypatch.setattr(retrieval, "generate_grounded_answer", unavailable)
    result = search(
        db,
        user=founder,
        query="高校电竞培训",
        requested_scope="history",
    )
    failure_audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "llm_generation_failed"
        )
    )

    assert result["generation_mode"] == "deterministic"
    assert result["generation_degraded"] is True
    assert len(result["results"]) == 1
    assert "已确认的历史资料" in result["answer"]
    assert failure_audit is not None


def test_l3_result_stays_local_without_founder_outbound_switch(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"test")
    db, founder, _employee = seeded_db(str(source))
    monkeypatch.setattr(
        retrieval,
        "settings",
        SimpleNamespace(
            embedding_enabled=False,
            gateway_api_key="test-only",
            embedding_model="embedding-test",
            llm_enabled=True,
            llm_l3_enabled=False,
        ),
    )

    def must_not_generate(*_args, **_kwargs):
        raise AssertionError("L3 evidence must stay local")

    monkeypatch.setattr(
        retrieval,
        "generate_grounded_answer",
        must_not_generate,
    )
    result = search(
        db,
        user=founder,
        query="高校电竞培训",
        requested_scope="history",
    )
    skipped_audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "llm_generation_skipped"
        )
    )

    assert result["generation_mode"] == "local_only"
    assert result["generation_degraded"] is False
    assert len(result["results"]) == 1
    assert skipped_audit is not None
    assert json.loads(skipped_audit.document_ids_json) == []
def test_score_treats_spacing_and_punctuation_variants_as_exact_match() -> None:
    chunk = SimpleNamespace(
        text="14:55 2025.07.29 星期二 北京市 · JDG 英特尔电子竞技中心",
    )
    document = SimpleNamespace(
        title="现场照片",
        is_final=False,
        role="material",
        knowledge_status="approved",
    )
    project = SimpleNamespace(name="英雄联盟项目")

    score, _matched = retrieval._score(
        "14:55 2025.07.29星期二北京市·JDG英特尔电子竞技中心",
        retrieval.query_terms(
            "14:55 2025.07.29星期二北京市·JDG英特尔电子竞技中心"
        ),
        chunk,
        document,
        project,
    )

    assert score >= 80
