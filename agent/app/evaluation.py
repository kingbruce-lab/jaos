from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .models import Chunk, Document, SourceHealth, User
from .retrieval import CONFIDENTIALITY_RANK, is_authorized, search
from .source_integrity import source_is_available


TECHNICAL_CASE_TARGET = 150
BUSINESS_GOLD_TARGET = 150
RETRIEVAL_CASE_TARGET = 120
REFUSAL_CASE_TARGET = 15
PERMISSION_CASE_TARGET = 15
EVALUATION_KNOWLEDGE_STATUSES = {
    "current",
    "approved",
    "superseded",
    "archived",
}
BUSINESS_GOLD_WRITE_LOCK = Lock()
BUSINESS_GOLD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,119}$")
BUSINESS_GOLD_ROLES = {
    "founder",
    "knowledge_admin",
    "department_owner",
    "planner",
    "employee",
}
BUSINESS_GOLD_POSITIVE_TARGET = 120
BUSINESS_GOLD_REFUSAL_TARGET = 15
BUSINESS_GOLD_PERMISSION_TARGET = 15
BUSINESS_GOLD_TEXT_LIST_LIMIT = 20

THRESHOLDS = {
    "page_citation_accuracy": 0.85,
    "refusal_accuracy": 0.80,
    "permission_leak_count": 0,
    "retrieval_p95_ms": 1000.0,
}

CONCURRENCY_PROFILES = (
    {
        "name": "founder",
        "role": "founder",
        "ceiling": "L4",
        "query": "KPL",
        "scope": "history",
    },
    {
        "name": "knowledge_admin",
        "role": "knowledge_admin",
        "ceiling": "L3",
        "query": "电竞培训",
        "scope": "history",
    },
    {
        "name": "department_owner",
        "role": "department_owner",
        "ceiling": "L3",
        "query": "训练营",
        "scope": "history",
    },
    {
        "name": "planner",
        "role": "planner",
        "ceiling": "L2",
        "query": "课程",
        "scope": "history",
    },
    {
        "name": "employee",
        "role": "employee",
        "ceiling": "L1",
        "query": "最新公司介绍",
        "scope": "current",
    },
)

REFUSAL_PROBES = (
    "火星联赛2035冠军编号ZXQ9999",
    "木星电竞馆2041租赁合同编号JUPITER41",
    "海王星战队2039选手名单NEPTUNE39",
    "月球训练营2045课程代码LUNAR45",
    "土星赛事2037总决赛成绩SATURN37",
    "金星青训营2043预算VENUS43",
    "水星场馆2047运营报告MERCURY47",
    "银河杯2050合作协议GALAXY50",
    "北极星战队2044冠军记录POLAR44",
    "深空电竞学院2048招生简章SPACE48",
    "火星基地2042场馆地址MARS42",
    "星云联赛2046执行方案NEBULA46",
    "彗星杯2038结案报告COMET38",
    "天王星训练营2049讲师名单URANUS49",
    "仙女座赛事2051报价ANDROMEDA51",
)


def _probe_user(*, ceiling: str, role: str) -> User:
    return User(
        id=f"evaluation-{role}-{ceiling.lower()}",
        username=f"evaluation-{role}",
        display_name="系统评测身份",
        password_hash="not-a-login-account",
        role=role,
        confidentiality_ceiling=ceiling,
        departments_json='["training"]',
        active=True,
    )


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _query_candidates(text: str) -> list[str]:
    normalized = _normalize_text(text)
    segments = [
        _normalize_text(item)
        for item in re.split(r"[\n。；;！？!?]+", text)
        if 8 <= len(_normalize_text(item)) <= 80
    ]
    windows: list[str] = []
    for start in range(0, max(0, len(normalized) - 15), 12):
        candidate = normalized[start:start + 36].strip(" ,，。；;：:")
        if len(candidate) >= 12:
            windows.append(candidate)
    return list(dict.fromkeys([*segments, *windows]))


def _build_retrieval_cases(chunks: list[Chunk]) -> list[dict]:
    normalized_texts = {
        chunk.id: _normalize_text(chunk.text)
        for chunk in chunks
        if _normalize_text(chunk.text)
    }
    cases: list[dict] = []
    used_queries: set[str] = set()
    for chunk in chunks:
        per_chunk = 0
        for candidate in _query_candidates(chunk.text):
            normalized = _normalize_text(candidate)
            if normalized in used_queries:
                continue
            occurrences = sum(
                1 for text in normalized_texts.values() if normalized in text
            )
            if occurrences != 1:
                continue
            used_queries.add(normalized)
            cases.append(
                {
                    "id": f"citation-{len(cases) + 1:03d}",
                    "kind": "page_citation",
                    "query": normalized,
                    "expected_document_id": chunk.document.id,
                    "expected_page": chunk.page,
                    "confidentiality": chunk.document.confidentiality,
                }
            )
            per_chunk += 1
            if len(cases) >= RETRIEVAL_CASE_TARGET:
                return cases[:RETRIEVAL_CASE_TARGET]
            if per_chunk >= 3:
                break
        if len(cases) >= RETRIEVAL_CASE_TARGET:
            break
    return cases


def _percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    return round(ordered[index], 2)


def _concurrency_probe(
    session_factory: Callable[[], Session],
    profile: dict,
) -> dict:
    started = time.perf_counter()
    with session_factory() as db:
        result = search(
            db,
            user=_probe_user(
                ceiling=profile["ceiling"],
                role=profile["role"],
            ),
            query=profile["query"],
            requested_scope=profile["scope"],
            requested_retrieval="exact",
            limit=8,
            audit=False,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000
    side_channel_leak = (
        profile["role"] not in {"founder", "knowledge_admin"}
        and (
            result["denied_count"] != 0
            or result["unavailable_count"] != 0
        )
    )
    return {
        "profile": profile["name"],
        "elapsed_ms": elapsed_ms,
        "result_count": len(result["results"]),
        "side_channel_leak": side_channel_leak,
    }


def run_concurrency_evaluation(
    session_factory: Callable[[], Session],
    *,
    output_dir: Path | None = None,
    rounds: int = 10,
) -> dict:
    safe_rounds = max(1, min(rounds, 50))
    latencies: list[float] = []
    errors: list[dict] = []
    side_channel_leak_count = 0
    profile_counts = {profile["name"]: 0 for profile in CONCURRENCY_PROFILES}
    for round_index in range(1, safe_rounds + 1):
        with ThreadPoolExecutor(
            max_workers=len(CONCURRENCY_PROFILES)
        ) as executor:
            futures = {
                executor.submit(
                    _concurrency_probe,
                    session_factory,
                    profile,
                ): profile
                for profile in CONCURRENCY_PROFILES
            }
            for future in as_completed(futures):
                profile = futures[future]
                try:
                    item = future.result()
                except Exception as exc:
                    errors.append(
                        {
                            "round": round_index,
                            "profile": profile["name"],
                            "reason": type(exc).__name__,
                        }
                    )
                    continue
                latencies.append(item["elapsed_ms"])
                profile_counts[item["profile"]] += 1
                side_channel_leak_count += int(item["side_channel_leak"])

    request_target = safe_rounds * len(CONCURRENCY_PROFILES)
    request_count = len(latencies)
    p95_ms = _percentile_95(latencies)
    passed = (
        request_count == request_target
        and not errors
        and side_channel_leak_count == 0
        and p95_ms < THRESHOLDS["retrieval_p95_ms"]
    )
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "concurrent_users": len(CONCURRENCY_PROFILES),
        "rounds": safe_rounds,
        "request_target": request_target,
        "request_count": request_count,
        "error_count": len(errors),
        "side_channel_leak_count": side_channel_leak_count,
        "p95_ms": p95_ms,
        "mean_ms": (
            round(statistics.fmean(latencies), 2) if latencies else 0.0
        ),
        "threshold_ms": THRESHOLDS["retrieval_p95_ms"],
        "profile_counts": profile_counts,
        "errors": errors[:25],
        "notice": (
            "使用五个合成权限身份并发读取，不创建员工账号，"
            "不修改资料或权限。"
        ),
    }
    report_dir = (output_dir or settings.evaluation_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    temporary = report_dir / "concurrency-latest.json.tmp"
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, report_dir / "concurrency-latest.json")
    return report


def load_latest_concurrency(
    evaluation_dir: Path | None = None,
) -> dict | None:
    path = (evaluation_dir or settings.evaluation_dir) / "concurrency-latest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if payload.get("schema_version") != 1:
        return None
    return payload


def _normalize_business_case(payload: dict) -> dict:
    case_id = str(payload.get("id", "")).strip()
    if not BUSINESS_GOLD_ID_RE.fullmatch(case_id):
        raise ValueError("invalid_id")
    question = _normalize_text(str(payload.get("question", "")))
    if not 5 <= len(question) <= 1000:
        raise ValueError("invalid_question")
    category = str(payload.get("category", "business_fact")).strip()
    if not 1 <= len(category) <= 80:
        raise ValueError("invalid_category")
    scope = str(payload.get("scope", "auto"))
    if scope not in {"auto", "current", "history", "all"}:
        raise ValueError("invalid_scope")
    retrieval = str(payload.get("retrieval", "exact"))
    if retrieval not in {"auto", "exact", "semantic", "hybrid"}:
        raise ValueError("invalid_retrieval")
    try:
        limit = int(payload.get("limit", 8))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_limit") from exc
    if not 1 <= limit <= 20:
        raise ValueError("invalid_limit")

    actor_payload = payload.get("actor") or {}
    if not isinstance(actor_payload, dict):
        raise ValueError("invalid_actor")
    role = str(actor_payload.get("role", "founder"))
    ceiling = str(actor_payload.get("confidentiality_ceiling", "L4"))
    if role not in BUSINESS_GOLD_ROLES or ceiling not in CONFIDENTIALITY_RANK:
        raise ValueError("invalid_actor")

    expected_payload = payload.get("expected")
    if not isinstance(expected_payload, dict):
        raise ValueError("invalid_expected")
    document_id = expected_payload.get("document_id")
    expect_refusal = expected_payload.get("expect_refusal") is True
    expect_no_leak = expected_payload.get("expect_no_leak") is True
    modes = int(bool(document_id)) + int(expect_refusal) + int(expect_no_leak)
    if modes != 1:
        raise ValueError("invalid_expected_mode")
    expected: dict = {}
    if document_id:
        document_id = str(document_id).strip()
        if len(document_id) != 36:
            raise ValueError("invalid_document_id")
        expected["document_id"] = document_id
        page = expected_payload.get("page")
        if page is not None:
            try:
                page = int(page)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_page") from exc
            if page < 1:
                raise ValueError("invalid_page")
            expected["page"] = page
        reference_answer = _normalize_text(
            str(expected_payload.get("reference_answer", ""))
        )
        if len(reference_answer) > 4000:
            raise ValueError("invalid_reference_answer")
        expected["reference_answer"] = reference_answer
        for field in ("key_points", "forbidden_claims"):
            values = expected_payload.get(field) or []
            if not isinstance(values, list) or len(values) > BUSINESS_GOLD_TEXT_LIST_LIMIT:
                raise ValueError(f"invalid_{field}")
            normalized_values = list(dict.fromkeys(
                _normalize_text(str(value))
                for value in values
                if _normalize_text(str(value))
            ))
            if any(len(value) > 300 for value in normalized_values):
                raise ValueError(f"invalid_{field}")
            expected[field] = normalized_values
    elif expect_refusal:
        expected["expect_refusal"] = True
    else:
        expected["expect_no_leak"] = True

    normalized = {
        "id": case_id,
        "category": category,
        "question": question,
        "scope": scope,
        "retrieval": retrieval,
        "limit": limit,
        "actor": {
            "role": role,
            "confidentiality_ceiling": ceiling,
        },
        "expected": expected,
        "approved": payload.get("approved") is True,
    }
    if payload.get("origin") == "ai_candidate":
        normalized["origin"] = "ai_candidate"
    for field in (
        "created_at",
        "updated_at",
        "updated_by_user_id",
        "approved_at",
        "approved_by_user_id",
        "owner_note",
    ):
        value = payload.get(field)
        if value:
            normalized[field] = str(value)[:500]
    return normalized


def _read_business_registry(path: Path) -> tuple[list[dict], list[dict]]:
    if not path.is_file():
        return [], []
    cases: list[dict] = []
    errors: list[dict] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return [], [{"line": 0, "reason": "registry_unreadable"}]
    for line_number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("case_not_object")
            normalized = _normalize_business_case(payload)
            if normalized["id"] in seen:
                raise ValueError("duplicate_id")
        except (json.JSONDecodeError, ValueError) as exc:
            reason = (
                str(exc)
                if isinstance(exc, ValueError)
                else "invalid_json"
            )
            errors.append({"line": line_number, "reason": reason})
            continue
        seen.add(normalized["id"])
        cases.append(normalized)
    return cases, errors


def _write_business_registry(path: Path, cases: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":"))
            for item in cases
        )
        + ("\n" if cases else ""),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def business_gold_registry(
    evaluation_dir: Path | None = None,
) -> dict:
    path = (evaluation_dir or settings.evaluation_dir) / "business_questions.jsonl"
    cases, errors = _read_business_registry(path)
    approved = sum(item["approved"] is True for item in cases)
    quality_ready = sum(
        bool(item["expected"].get("reference_answer"))
        and bool(item["expected"].get("key_points"))
        for item in cases
        if item["expected"].get("document_id")
    )
    return {
        "target": BUSINESS_GOLD_TARGET,
        "total": len(cases),
        "approved": approved,
        "pending": len(cases) - approved,
        "invalid": len(errors),
        "quality_ready": quality_ready,
        "errors": errors[:25],
        "cases": cases,
    }


def upsert_business_gold_drafts(
    cases: list[dict],
    *,
    user: User,
    evaluation_dir: Path | None = None,
) -> dict:
    path = (evaluation_dir or settings.evaluation_dir) / "business_questions.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    normalized_input = [_normalize_business_case(item) for item in cases]
    if len({item["id"] for item in normalized_input}) != len(normalized_input):
        raise ValueError("duplicate_id")
    with BUSINESS_GOLD_WRITE_LOCK:
        existing, errors = _read_business_registry(path)
        if errors:
            raise ValueError("registry_invalid")
        by_id = {item["id"]: item for item in existing}
        order = [item["id"] for item in existing]
        for item in normalized_input:
            previous = by_id.get(item["id"])
            item["approved"] = False
            item["created_at"] = (
                previous.get("created_at", now) if previous else now
            )
            item["updated_at"] = now
            item["updated_by_user_id"] = user.id
            for field in (
                "approved_at",
                "approved_by_user_id",
                "owner_note",
            ):
                item.pop(field, None)
            by_id[item["id"]] = item
            if item["id"] not in order:
                order.append(item["id"])
        _write_business_registry(path, [by_id[item_id] for item_id in order])
    return business_gold_registry(evaluation_dir)


def approve_business_gold_cases(
    db: Session,
    case_ids: list[str],
    *,
    user: User,
    owner_note: str,
    evaluation_dir: Path | None = None,
) -> dict:
    path = (evaluation_dir or settings.evaluation_dir) / "business_questions.jsonl"
    unique_ids = list(dict.fromkeys(case_ids))
    now = datetime.now(timezone.utc).isoformat()
    with BUSINESS_GOLD_WRITE_LOCK:
        cases, errors = _read_business_registry(path)
        if errors:
            raise ValueError("registry_invalid")
        by_id = {item["id"]: item for item in cases}
        if any(case_id not in by_id for case_id in unique_ids):
            raise ValueError("case_not_found")
        health_by_hash = {
            row.content_hash: row
            for row in db.scalars(select(SourceHealth)).all()
        }
        for case_id in unique_ids:
            case = by_id[case_id]
            expected = case["expected"]
            document_id = expected.get("document_id")
            if document_id:
                if (
                    not expected.get("reference_answer")
                    or not expected.get("key_points")
                ):
                    raise ValueError(f"answer_key_incomplete:{case_id}")
                document = db.get(Document, document_id)
                if (
                    document is None
                    or document.knowledge_status not in EVALUATION_KNOWLEDGE_STATUSES
                    or document.file_blob is None
                    or not source_is_available(
                        document.file_blob,
                        health_by_hash.get(document.content_hash),
                    )
                    or expected.get("page", 1) > max(document.page_count, 1)
                ):
                    raise ValueError(f"source_not_eligible:{case_id}")
            case["approved"] = True
            case["approved_at"] = now
            case["approved_by_user_id"] = user.id
            case["owner_note"] = owner_note[:500]
            case["updated_at"] = now
        _write_business_registry(path, cases)
    return business_gold_registry(evaluation_dir)


def _load_business_cases(path: Path) -> list[dict]:
    cases, _errors = _read_business_registry(path)
    return [item for item in cases if item["approved"] is True]


def _normalized_match_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()


def _suggest_key_points(text: str) -> list[str]:
    normalized = _normalize_text(text)
    numeric = re.findall(
        r"(?<!\w)\d+(?:\.\d+)?(?:%|万元|万|亿元|亿|人|场|家|项|天|年|月|日|届|个)?",
        normalized,
    )
    latin = re.findall(r"\b[A-Za-z][A-Za-z0-9.+-]{2,20}\b", normalized)
    suggestions = list(dict.fromkeys([*numeric, *latin]))[:3]
    if not suggestions:
        fragments = [
            _normalize_text(item)
            for item in re.split(r"[。；;！？!?，,]", normalized)
            if 6 <= len(_normalize_text(item)) <= 24
        ]
        suggestions = fragments[:2]
    if not suggestions and normalized:
        suggestions = [normalized[: min(18, len(normalized))]]
    return suggestions


def _candidate_id(kind: str, document_id: str, page: int) -> str:
    identity = f"{kind}:{document_id}:{page}".encode("utf-8")
    return f"auto-{kind}-{hashlib.sha256(identity).hexdigest()[:16]}"


def generate_business_gold_candidates(
    db: Session,
    *,
    user: User,
    target: int = BUSINESS_GOLD_TARGET,
    evaluation_dir: Path | None = None,
) -> dict:
    """Create source-grounded drafts. Nothing returned here is approved."""
    target = min(BUSINESS_GOLD_TARGET, max(1, int(target)))
    registry = business_gold_registry(evaluation_dir)
    replaceable_ids = {
        item["id"]
        for item in registry["cases"]
        if not item["approved"]
        and (
            item.get("origin") == "ai_candidate"
            or item["id"].startswith("auto-")
        )
    }
    if replaceable_ids:
        path = (evaluation_dir or settings.evaluation_dir) / "business_questions.jsonl"
        with BUSINESS_GOLD_WRITE_LOCK:
            retained = [
                item for item in registry["cases"]
                if item["id"] not in replaceable_ids
            ]
            _write_business_registry(path, retained)
        registry = business_gold_registry(evaluation_dir)
    existing_ids = {item["id"] for item in registry["cases"]}
    existing_questions = {
        _normalized_match_text(item["question"])
        for item in registry["cases"]
    }
    health_by_hash = {
        row.content_hash: row
        for row in db.scalars(select(SourceHealth)).all()
    }
    chunks = db.scalars(
        select(Chunk)
        .options(
            joinedload(Chunk.document).joinedload(Document.project),
            joinedload(Chunk.document).joinedload(Document.file_blob),
        )
        .join(Chunk.document)
        .where(Document.knowledge_status.in_(EVALUATION_KNOWLEDGE_STATUSES))
        .order_by(Document.knowledge_status, Document.ingested_at.desc(), Chunk.page)
    ).all()

    eligible: list[Chunk] = []
    permission_documents: dict[str, Document] = {}
    seen_pages: set[tuple[str, int]] = set()
    for chunk in chunks:
        document = chunk.document
        if not is_authorized(user, document, document.project):
            continue
        if not source_is_available(
            document.file_blob,
            health_by_hash.get(document.content_hash),
        ):
            continue
        if document.confidentiality == "L3":
            permission_documents.setdefault(document.id, document)
            continue
        if document.confidentiality not in {"L1", "L2"}:
            continue
        if not _normalize_text(chunk.text) or (document.id, chunk.page) in seen_pages:
            continue
        seen_pages.add((document.id, chunk.page))
        eligible.append(chunk)

    positive_target = min(BUSINESS_GOLD_POSITIVE_TARGET, target)
    candidates: list[dict] = []
    used_positive_pages: set[tuple[str, int]] = set()

    def diverse_chunks(pool: list[Chunk], limit: int, per_project: int) -> list[Chunk]:
        grouped: dict[str, list[Chunk]] = {}
        for item in pool:
            grouped.setdefault(item.document.project.id, []).append(item)
        selected: list[Chunk] = []
        per_project_counts: dict[str, int] = {}
        while len(selected) < limit:
            progressed = False
            for project_id in sorted(grouped):
                if per_project_counts.get(project_id, 0) >= per_project:
                    continue
                while grouped[project_id]:
                    item = grouped[project_id].pop(0)
                    key = (item.document.id, item.page)
                    if key not in used_positive_pages:
                        break
                else:
                    continue
                selected.append(item)
                used_positive_pages.add(key)
                per_project_counts[project_id] = per_project_counts.get(project_id, 0) + 1
                progressed = True
                if len(selected) >= limit:
                    break
            if not progressed:
                break
        return selected

    def append_positive(chunk: Chunk, category: str) -> None:
        document = chunk.document
        project = document.project
        scope = "current" if document.knowledge_status == "current" else "history"
        if category == "company_fact":
            question = (
                f"根据当前正式资料，京奥电竞在《{document.title}》第{chunk.page}页"
                "说明了哪些公司事实？"
            )
        elif category == "historical_result":
            question = (
                f"历史项目“{project.name}”在《{document.title}》第{chunk.page}页"
                "记录了哪些项目结果或复盘信息？"
            )
        elif category == "reusable_experience":
            question = (
                f"参考历史项目“{project.name}”，《{document.title}》第{chunk.page}页"
                "有哪些可复用的做法或知识？"
            )
        elif category == "historical_execution":
            question = (
                f"历史项目“{project.name}”在《{document.title}》第{chunk.page}页"
                "记录了哪些执行安排、流程或现场要求？"
            )
        elif category == "material_locator":
            question = (
                f"为制作与“{project.name}”相关的材料，请定位《{document.title}》"
                f"第{chunk.page}页，并概括这份素材可以支持什么内容。"
            )
        else:
            question = (
                f"历史项目“{project.name}”的《{document.title}》第{chunk.page}页"
                "包含哪些方案或执行要点？"
            )
        case_id = _candidate_id(category, document.id, chunk.page)
        if case_id in existing_ids or _normalized_match_text(question) in existing_questions:
            return
        answer = _normalize_text(chunk.text)[:1800]
        candidates.append({
            "id": case_id,
            "origin": "ai_candidate",
            "category": category,
            "question": question,
            "scope": scope,
            "retrieval": "hybrid",
            "limit": 8,
            "actor": {"role": "founder", "confidentiality_ceiling": "L4"},
            "expected": {
                "document_id": document.id,
                "page": chunk.page,
                "reference_answer": answer,
                "key_points": _suggest_key_points(answer),
                "forbidden_claims": (
                    ["这是京奥电竞当前最新情况"] if scope == "history" else []
                ),
            },
        })
        existing_ids.add(case_id)
        existing_questions.add(_normalized_match_text(question))

    quota_plan = (
        ("company_fact", 25, {"company_profile"}, 30),
        ("historical_case", 40, {"proposal", "brief"}, 3),
        ("reusable_experience", 20, {"proposal", "brief"}, 2),
        ("historical_execution", 20, {"execution"}, 10),
        ("material_locator", 15, {"asset"}, 2),
    )
    for category, quota, roles, per_project in quota_plan:
        remaining = positive_target - len(candidates)
        if remaining <= 0:
            break
        pool = [item for item in eligible if item.document.role in roles]
        for chunk in diverse_chunks(pool, min(quota, remaining), per_project):
            append_positive(chunk, category)

    # Sparse pilot corpora may not contain every role yet. Fill only from
    # additional real pages and report a shortfall if even those are exhausted.
    if len(candidates) < positive_target:
        fallback_categories = {
            "company_profile": "company_fact",
            "execution": "historical_execution",
            "closing_report": "historical_result",
            "proposal": "historical_case",
            "brief": "historical_case",
            "asset": "material_locator",
        }
        for chunk in diverse_chunks(
            eligible,
            positive_target - len(candidates),
            6,
        ):
            append_positive(
                chunk,
                fallback_categories.get(chunk.document.role, "material_locator"),
            )

    refusal_target = min(BUSINESS_GOLD_REFUSAL_TARGET, max(0, target - len(candidates)))
    for index in range(refusal_target):
        token = f"JINGAO-NOT-FOUND-{index + 1:03d}-2099"
        case_id = f"auto-refusal-{index + 1:03d}"
        if case_id in existing_ids:
            continue
        candidates.append({
            "id": case_id,
            "origin": "ai_candidate",
            "category": "refusal",
            "question": f"请查询不存在的项目资料编号 {token} 并说明项目结果。",
            "scope": "all",
            "retrieval": "exact",
            "limit": 8,
            "actor": {"role": "founder", "confidentiality_ceiling": "L4"},
            "expected": {"expect_refusal": True},
        })
        existing_ids.add(case_id)

    permission_target = min(
        BUSINESS_GOLD_PERMISSION_TARGET,
        max(0, target - len(candidates)),
    )
    for document in list(permission_documents.values())[:permission_target]:
        case_id = f"auto-permission-{document.id[:16]}"
        if case_id in existing_ids:
            continue
        candidates.append({
            "id": case_id,
            "origin": "ai_candidate",
            "category": "permission_boundary",
            "question": f"请提供业务敏感资料《{document.title}》中的详细内容。",
            "scope": "all",
            "retrieval": "exact",
            "limit": 8,
            "actor": {"role": "employee", "confidentiality_ceiling": "L1"},
            "expected": {"expect_no_leak": True},
        })
        existing_ids.add(case_id)

    candidates = candidates[:target]
    if candidates:
        updated = upsert_business_gold_drafts(
            candidates,
            user=user,
            evaluation_dir=evaluation_dir,
        )
    else:
        updated = registry
    counts: dict[str, int] = {}
    for case in candidates:
        counts[case["category"]] = counts.get(case["category"], 0) + 1
    return {
        **updated,
        "generation": {
            "requested": target,
            "created": len(candidates),
            "shortfall": max(0, target - len(candidates)),
            "counts": counts,
            "eligible_positive_pages": len(eligible),
            "eligible_permission_documents": len(permission_documents),
        },
    }


def _run_business_cases(db: Session, cases: list[dict]) -> tuple[int, list[dict]]:
    passed_count = 0
    failures: list[dict] = []
    for case in cases:
        source_passed: bool | None = None
        missing_key_points: list[str] = []
        forbidden_hits: list[str] = []
        actor = case.get("actor") or {}
        user = _probe_user(
            ceiling=str(actor.get("confidentiality_ceiling", "L4")),
            role=str(actor.get("role", "founder")),
        )
        result = search(
            db,
            user=user,
            query=str(case["question"]),
            requested_scope=str(case.get("scope", "auto")),
            requested_retrieval=str(case.get("retrieval", "exact")),
            limit=min(20, max(1, int(case.get("limit", 8)))),
            audit=False,
        )
        expected = case["expected"]
        if expected.get("expect_refusal") is True:
            passed = (
                not result["results"]
                and result["answer"] == "资料中未找到"
            )
        elif expected.get("expect_no_leak") is True:
            passed = (
                not result["results"]
                and result["denied_count"] == 0
                and result["unavailable_count"] == 0
            )
        else:
            document_id = expected.get("document_id")
            page = expected.get("page")
            citations = result["citations"]
            source_passed = any(
                (not document_id or item["document_id"] == document_id)
                and (page is None or item["page"] == page)
                for item in citations
            )
            answer_text = _normalized_match_text(str(result.get("answer", "")))
            missing_key_points = [
                item for item in expected.get("key_points", [])
                if _normalized_match_text(item) not in answer_text
            ]
            forbidden_hits = [
                item for item in expected.get("forbidden_claims", [])
                if _normalized_match_text(item)
                and _normalized_match_text(item) in answer_text
            ]
            passed = source_passed and not missing_key_points and not forbidden_hits
        if passed:
            passed_count += 1
        else:
            failures.append(
                {
                    "id": str(case["id"]),
                    "kind": str(case.get("category", "business_gold")),
                    "reason": "business_expectation_not_met",
                    "source_matched": source_passed,
                    "missing_key_points": missing_key_points,
                    "forbidden_claims_found": forbidden_hits,
                }
            )
    return passed_count, failures


def run_technical_evaluation(
    db: Session,
    *,
    output_dir: Path | None = None,
) -> dict:
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
    retrieval_cases = _build_retrieval_cases(available)
    founder = _probe_user(ceiling="L4", role="founder")
    employee = _probe_user(ceiling="L2", role="employee")

    latencies: list[float] = []
    failures: list[dict] = []
    retrieval_passed = 0
    for case in retrieval_cases:
        started = time.perf_counter()
        result = search(
            db,
            user=founder,
            query=case["query"],
            requested_scope="history",
            requested_retrieval="exact",
            limit=5,
            audit=False,
        )
        latencies.append((time.perf_counter() - started) * 1000)
        citation_keys = {
            (item["document_id"], item["page"])
            for item in result["citations"]
        }
        expected = (
            case["expected_document_id"],
            case["expected_page"],
        )
        if expected in citation_keys:
            retrieval_passed += 1
        else:
            failures.append(
                {
                    "id": case["id"],
                    "kind": case["kind"],
                    "reason": "expected_page_not_retrieved",
                }
            )

    refusal_passed = 0
    for index, query in enumerate(REFUSAL_PROBES, start=1):
        result = search(
            db,
            user=founder,
            query=query,
            requested_scope="current",
            requested_retrieval="exact",
            limit=5,
            audit=False,
        )
        if not result["results"] and result["answer"] == "资料中未找到":
            refusal_passed += 1
        else:
            failures.append(
                {
                    "id": f"refusal-{index:03d}",
                    "kind": "refusal",
                    "reason": "unsupported_answer_not_refused",
                }
            )

    restricted_cases = [
        case
        for case in retrieval_cases
        if CONFIDENTIALITY_RANK.get(case["confidentiality"], 99)
        > CONFIDENTIALITY_RANK["L2"]
    ][:PERMISSION_CASE_TARGET]
    permission_passed = 0
    for index, case in enumerate(restricted_cases, start=1):
        result = search(
            db,
            user=employee,
            query=case["query"],
            requested_scope="history",
            requested_retrieval="exact",
            limit=5,
            audit=False,
        )
        passed = (
            not result["results"]
            and result["answer"] == "资料中未找到"
            and result["denied_count"] == 0
            and result["unavailable_count"] == 0
        )
        if passed:
            permission_passed += 1
        else:
            failures.append(
                {
                    "id": f"permission-{index:03d}",
                    "kind": "permission",
                    "reason": "unauthorized_result_or_side_channel",
                }
            )

    retrieval_total = len(retrieval_cases)
    refusal_total = len(REFUSAL_PROBES)
    permission_total = len(restricted_cases)
    case_total = retrieval_total + refusal_total + permission_total
    page_accuracy = (
        retrieval_passed / retrieval_total if retrieval_total else 0.0
    )
    refusal_accuracy = (
        refusal_passed / refusal_total if refusal_total else 0.0
    )
    permission_leak_count = permission_total - permission_passed
    p95_ms = _percentile_95(latencies)
    enough_cases = (
        retrieval_total == RETRIEVAL_CASE_TARGET
        and refusal_total == REFUSAL_CASE_TARGET
        and permission_total == PERMISSION_CASE_TARGET
        and case_total == TECHNICAL_CASE_TARGET
    )
    gates = {
        "case_coverage": enough_cases,
        "page_citation_accuracy": (
            page_accuracy >= THRESHOLDS["page_citation_accuracy"]
        ),
        "refusal_accuracy": (
            refusal_accuracy >= THRESHOLDS["refusal_accuracy"]
        ),
        "permission_isolation": (
            permission_leak_count == THRESHOLDS["permission_leak_count"]
        ),
        "retrieval_latency": p95_ms < THRESHOLDS["retrieval_p95_ms"],
    }
    technical_status = (
        "passed"
        if all(gates.values())
        else "incomplete"
        if not enough_cases
        else "failed"
    )

    report_dir = (output_dir or settings.evaluation_dir).resolve()
    business_gold_path = report_dir / "business_questions.jsonl"
    business_cases = _load_business_cases(business_gold_path)
    business_gold_total = len(business_cases)
    business_passed_count, business_failures = _run_business_cases(
        db,
        business_cases,
    )
    positive_business_cases = [
        item for item in business_cases
        if item["expected"].get("document_id")
    ]
    positive_business_failures = [
        item for item in business_failures
        if item.get("source_matched") is not None
    ]
    source_passed_count = len(positive_business_cases) - sum(
        item.get("source_matched") is False
        for item in positive_business_failures
    )
    answer_passed_count = len(positive_business_cases) - sum(
        bool(item.get("missing_key_points"))
        or bool(item.get("forbidden_claims_found"))
        for item in positive_business_failures
    )
    business_accuracy = (
        business_passed_count / business_gold_total
        if business_gold_total
        else None
    )
    if business_gold_total < BUSINESS_GOLD_TARGET:
        business_gold_status = "pending"
    elif business_passed_count == business_gold_total:
        business_gold_status = "passed"
    else:
        business_gold_status = "failed"
    failures.extend(business_failures)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "technical_status": technical_status,
        "technical_case_target": TECHNICAL_CASE_TARGET,
        "technical_case_count": case_total,
        "business_gold_target": BUSINESS_GOLD_TARGET,
        "business_gold_total": business_gold_total,
        "business_gold_passed_count": business_passed_count,
        "business_gold_status": business_gold_status,
        "metrics": {
            "page_citation_accuracy": round(page_accuracy, 4),
            "refusal_accuracy": round(refusal_accuracy, 4),
            "permission_leak_count": permission_leak_count,
            "retrieval_p95_ms": p95_ms,
            "retrieval_mean_ms": (
                round(statistics.fmean(latencies), 2) if latencies else 0.0
            ),
            "business_gold_accuracy": (
                round(business_accuracy, 4)
                if business_accuracy is not None
                else None
            ),
            "business_source_accuracy": (
                round(source_passed_count / len(positive_business_cases), 4)
                if positive_business_cases else None
            ),
            "business_answer_accuracy": (
                round(answer_passed_count / len(positive_business_cases), 4)
                if positive_business_cases else None
            ),
        },
        "case_counts": {
            "page_citation": retrieval_total,
            "refusal": refusal_total,
            "permission": permission_total,
        },
        "passed_counts": {
            "page_citation": retrieval_passed,
            "refusal": refusal_passed,
            "permission": permission_passed,
        },
        "thresholds": THRESHOLDS,
        "gates": gates,
        "source_snapshot": {
            "available_documents": len(
                {chunk.document.id for chunk in available}
            ),
            "available_chunks": len(available),
        },
        "failures": failures[:50],
        "notice": (
            "技术探针只验证检索、引用、拒答和权限隔离；"
            "不替代由业务负责人标注的公司事实与案例金标。"
        ),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    temporary = report_dir / "latest.json.tmp"
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, report_dir / "latest.json")
    return report


def load_latest_evaluation(
    evaluation_dir: Path | None = None,
) -> dict | None:
    path = (evaluation_dir or settings.evaluation_dir) / "latest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("schema_version") != 1:
        return None
    return payload


def evaluation_component(
    evaluation_dir: Path | None = None,
) -> dict:
    report = load_latest_evaluation(evaluation_dir)
    concurrency = load_latest_concurrency(evaluation_dir)
    if not report:
        return {
            "status": "warning",
            "message": "尚未运行技术评测",
            "technical_status": "not_run",
            "technical_case_count": 0,
            "business_gold_total": 0,
            "concurrency_status": (
                concurrency.get("status") if concurrency else "not_run"
            ),
            "concurrency_p95_ms": (
                concurrency.get("p95_ms") if concurrency else None
            ),
            "generated_at": None,
        }
    technical_passed = report.get("technical_status") == "passed"
    business_ready = report.get("business_gold_status") == "passed"
    if technical_passed and business_ready:
        state = "ok"
        message = "技术基线与业务金标题库均已就绪"
    elif (
        technical_passed
        and report.get("business_gold_status") == "failed"
    ):
        state = "warning"
        message = "技术基线通过，业务金标存在失败题"
    elif technical_passed:
        state = "warning"
        message = "技术基线通过，业务金标题库待补充"
    else:
        state = "critical" if report.get("technical_status") == "failed" else "warning"
        message = "技术评测未达到首期门槛"
    return {
        "status": state,
        "message": message,
        "technical_status": report.get("technical_status"),
        "technical_case_count": report.get("technical_case_count", 0),
        "business_gold_total": report.get("business_gold_total", 0),
        "business_gold_status": report.get("business_gold_status", "pending"),
        "concurrency_status": (
            concurrency.get("status") if concurrency else "not_run"
        ),
        "concurrency_p95_ms": (
            concurrency.get("p95_ms") if concurrency else None
        ),
        "concurrency_request_count": (
            concurrency.get("request_count", 0) if concurrency else 0
        ),
        "concurrency_error_count": (
            concurrency.get("error_count", 0) if concurrency else 0
        ),
        "generated_at": report.get("generated_at"),
        "metrics": report.get("metrics", {}),
        "gates": report.get("gates", {}),
    }
