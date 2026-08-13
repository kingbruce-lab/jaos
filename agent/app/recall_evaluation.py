from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .config import settings
from .evaluation import _probe_user
from .retrieval import search


RECALL_CUTOFFS = (1, 3, 5, 8)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    return round(ordered[index], 2)


def _rank(items: list[dict], document_id: str, page: int | None = None) -> int | None:
    for index, item in enumerate(items, start=1):
        if item.get("document_id") != document_id:
            continue
        if page is not None and item.get("page") != page:
            continue
        return index
    return None


def _load_candidate_cases(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    cases: list[dict] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("question"):
            cases.append(payload)
    return cases


def _aggregate_positive(rows: list[dict]) -> dict:
    total = len(rows)
    document_ranks = [row["document_rank"] for row in rows if row["document_rank"]]
    page_ranks = [row["page_rank"] for row in rows if row["page_rank"]]
    payload = {
        "case_count": total,
        "document_mrr": round(
            sum(1 / rank for rank in document_ranks) / total, 4
        ) if total else 0.0,
        "page_mrr": round(
            sum(1 / rank for rank in page_ranks) / total, 4
        ) if total else 0.0,
    }
    for cutoff in RECALL_CUTOFFS:
        payload[f"document_recall_at_{cutoff}"] = round(
            sum(1 for rank in document_ranks if rank <= cutoff) / total, 4
        ) if total else 0.0
        payload[f"page_recall_at_{cutoff}"] = round(
            sum(1 for rank in page_ranks if rank <= cutoff) / total, 4
        ) if total else 0.0
    return payload


def run_recall_quality_evaluation(
    db: Session,
    *,
    mode: str = "intended",
    max_cases: int = 150,
    limit: int = 8,
    label: str = "manual",
    output_dir: Path | None = None,
) -> dict:
    """Run the candidate business set as a source-recall benchmark.

    The 150 generated cases are deliberately labelled candidate probes rather
    than approved business gold. They measure source/page retrieval, refusal
    and permission isolation; they do not certify answer correctness.
    """

    if mode not in {"intended", "exact", "hybrid", "semantic"}:
        raise ValueError("invalid_recall_mode")
    report_dir = (output_dir or settings.evaluation_dir).resolve()
    cases = _load_candidate_cases(report_dir / "business_questions.jsonl")
    selected_cases = cases[: max(1, min(max_cases, 150))]
    rows: list[dict] = []
    latencies: list[float] = []

    for case in selected_cases:
        expected = case.get("expected") or {}
        actor = case.get("actor") or {}
        user = _probe_user(
            ceiling=str(actor.get("confidentiality_ceiling", "L4")),
            role=str(actor.get("role", "founder")),
        )
        requested_mode = (
            str(case.get("retrieval", "exact")) if mode == "intended" else mode
        )
        started = time.perf_counter()
        result = search(
            db,
            user=user,
            query=str(case["question"]),
            requested_scope=str(case.get("scope", "auto")),
            requested_retrieval=requested_mode,
            limit=limit,
            audit=False,
            generate=False,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        latencies.append(elapsed_ms)
        document_id = expected.get("document_id")
        page = expected.get("page")
        document_rank = (
            _rank(result["results"], str(document_id)) if document_id else None
        )
        page_rank = (
            _rank(result["citations"], str(document_id), int(page))
            if document_id and page is not None
            else None
        )
        if expected.get("expect_refusal") is True:
            passed = not result["results"]
            outcome = "refusal"
        elif expected.get("expect_no_leak") is True:
            restricted_document_returned = bool(
                document_id
                and any(
                    item.get("document_id") == document_id
                    for item in result["results"]
                )
            )
            passed = (
                not restricted_document_returned
                and result["denied_count"] == 0
                and result["unavailable_count"] == 0
            )
            outcome = "permission"
        else:
            passed = page_rank is not None and page_rank <= limit
            outcome = "positive"
        rows.append(
            {
                "id": str(case.get("id", "")),
                "category": str(case.get("category", "unknown")),
                "outcome": outcome,
                "query": str(case["question"]),
                "query_hash": hashlib.sha256(
                    str(case["question"]).encode("utf-8")
                ).hexdigest(),
                "requested_mode": requested_mode,
                "effective_mode": result["retrieval_mode"],
                "retrieval_degraded": result["retrieval_degraded"],
                "expected_document_id": document_id,
                "expected_page": page,
                "document_rank": document_rank,
                "page_rank": page_rank,
                "result_count": len(result["results"]),
                "denied_count": result["denied_count"],
                "unavailable_count": result["unavailable_count"],
                "elapsed_ms": elapsed_ms,
                "passed": passed,
            }
        )

    positive = [row for row in rows if row["outcome"] == "positive"]
    refusals = [row for row in rows if row["outcome"] == "refusal"]
    permissions = [row for row in rows if row["outcome"] == "permission"]
    by_category = {
        category: _aggregate_positive(
            [row for row in positive if row["category"] == category]
        )
        for category in sorted({row["category"] for row in positive})
    }
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "benchmark": "candidate_business_source_recall",
        "gold_status": "candidate_unapproved",
        "mode": mode,
        "limit": limit,
        "case_count": len(rows),
        "metrics": {
            **_aggregate_positive(positive),
            "refusal_accuracy": round(
                sum(row["passed"] for row in refusals) / len(refusals), 4
            ) if refusals else None,
            "permission_isolation_accuracy": round(
                sum(row["passed"] for row in permissions) / len(permissions), 4
            ) if permissions else None,
            "degraded_count": sum(row["retrieval_degraded"] for row in rows),
            "empty_result_count": sum(row["result_count"] == 0 for row in rows),
            "latency_mean_ms": round(statistics.fmean(latencies), 2)
            if latencies else 0.0,
            "latency_p95_ms": _p95(latencies),
        },
        "by_category": by_category,
        "failures": [
            {
                key: row[key]
                for key in (
                    "id",
                    "category",
                    "outcome",
                    "requested_mode",
                    "effective_mode",
                    "expected_document_id",
                    "expected_page",
                    "document_rank",
                    "page_rank",
                    "result_count",
                    "elapsed_ms",
                )
            }
            for row in rows
            if not row["passed"]
        ],
        "cases": rows,
        "notice": (
            "This benchmark uses unapproved candidate questions to measure "
            "source/page recall only; it is not business-answer acceptance."
        ),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(
        character for character in label if character.isalnum() or character in "-_"
    ) or "manual"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = report_dir / f"recall-{safe_label}-{timestamp}.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, destination)
    latest = report_dir / "recall-latest.json"
    latest_tmp = report_dir / "recall-latest.json.tmp"
    latest_tmp.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(latest_tmp, latest)
    return {**report, "report_path": str(destination)}
