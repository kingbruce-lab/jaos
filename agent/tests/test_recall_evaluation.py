from __future__ import annotations

import json

from app import recall_evaluation


def test_candidate_recall_report_records_ranked_metrics(tmp_path, monkeypatch) -> None:
    cases = [
        {
            "id": "positive-1",
            "category": "historical_case",
            "question": "historical case question",
            "scope": "history",
            "retrieval": "hybrid",
            "actor": {"role": "founder", "confidentiality_ceiling": "L4"},
            "expected": {"document_id": "doc-1", "page": 3},
            "approved": False,
        },
        {
            "id": "refusal-1",
            "category": "refusal",
            "question": "not found question",
            "scope": "all",
            "retrieval": "exact",
            "expected": {"expect_refusal": True},
            "approved": False,
        },
        {
            "id": "permission-1",
            "category": "permission_boundary",
            "question": "restricted question",
            "scope": "all",
            "retrieval": "exact",
            "actor": {"role": "employee", "confidentiality_ceiling": "L1"},
            "expected": {
                "expect_no_leak": True,
                "document_id": "restricted-doc",
            },
            "approved": False,
        },
    ]
    (tmp_path / "business_questions.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in cases),
        encoding="utf-8",
    )

    def fake_search(_db, *, query, requested_retrieval, **_kwargs):
        if query == "historical case question":
            return {
                "results": [
                    {"document_id": "other"},
                    {"document_id": "doc-1"},
                ],
                "citations": [
                    {"document_id": "other", "page": 1},
                    {"document_id": "doc-1", "page": 3},
                ],
                "retrieval_mode": requested_retrieval,
                "retrieval_degraded": False,
                "denied_count": 0,
                "unavailable_count": 0,
            }
        if query == "restricted question":
            return {
                "results": [{"document_id": "authorized-doc"}],
                "citations": [],
                "retrieval_mode": requested_retrieval,
                "retrieval_degraded": False,
                "denied_count": 0,
                "unavailable_count": 0,
            }
        return {
            "results": [],
            "citations": [],
            "retrieval_mode": requested_retrieval,
            "retrieval_degraded": False,
            "denied_count": 0,
            "unavailable_count": 0,
        }

    monkeypatch.setattr(recall_evaluation, "search", fake_search)
    report = recall_evaluation.run_recall_quality_evaluation(
        object(),
        output_dir=tmp_path,
        label="test",
    )

    assert report["gold_status"] == "candidate_unapproved"
    assert report["metrics"]["document_recall_at_1"] == 0.0
    assert report["metrics"]["document_recall_at_3"] == 1.0
    assert report["metrics"]["page_recall_at_3"] == 1.0
    assert report["metrics"]["refusal_accuracy"] == 1.0
    assert report["metrics"]["permission_isolation_accuracy"] == 1.0
    assert (tmp_path / "recall-latest.json").is_file()
