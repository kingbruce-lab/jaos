from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app import generation
from app.generation import (
    GenerationEvidence,
    GenerationServiceError,
    generate_grounded_answer,
    generate_grounded_draft,
    request_chat_completion,
)


def generation_settings(**overrides):
    values = {
        "gateway_base_url": "https://gateway.example/v1",
        "gateway_api_key": "test-only",
        "llm_enabled": True,
        "llm_l3_enabled": False,
        "primary_model": "grok-test",
        "fallback_model": "deepseek-test",
        "llm_timeout_seconds": 10,
        "llm_max_context_characters": 4000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def evidence(level: str = "L2") -> GenerationEvidence:
    return GenerationEvidence(
        document_id=f"document-{level}",
        title=f"{level} 测试资料",
        version="v1.0",
        page=2,
        status="current",
        confidentiality=level,
        excerpt="本项目面向高校学生开展电竞课程与实训。",
    )


def test_chat_completion_uses_openai_compatible_gateway(monkeypatch) -> None:
    monkeypatch.setattr(generation, "settings", generation_settings())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-only"
        body = request.read().decode("utf-8")
        assert '"model":"grok-test"' in body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "项目包含电竞课程与实训 [S1]。"
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        answer = request_chat_completion(
            "grok-test",
            [{"role": "user", "content": "test"}],
            client=client,
        )
    assert answer == "项目包含电竞课程与实训 [S1]。"


def test_primary_failure_falls_back_and_preserves_citations(monkeypatch) -> None:
    monkeypatch.setattr(generation, "settings", generation_settings())
    called: list[str] = []

    def requester(model: str, messages: list[dict[str, str]]) -> str:
        called.append(model)
        assert "不可信数据" in messages[0]["content"]
        assert "本项目面向高校学生" in messages[1]["content"]
        if model == "grok-test":
            raise GenerationServiceError("gateway_http_429")
        return "项目面向高校学生开展电竞课程与实训。[S1]"

    result = generate_grounded_answer(
        "项目做了什么？",
        [evidence()],
        founder=False,
        requester=requester,
    )
    assert called == ["grok-test", "deepseek-test"]
    assert result.model == "deepseek-test"
    assert result.fallback_used is True
    assert result.answer.endswith("[S1]")
    assert result.evidence_document_ids == ["document-L2"]


def test_l4_l5_never_leave_and_l3_requires_founder_switch(monkeypatch) -> None:
    monkeypatch.setattr(generation, "settings", generation_settings())
    called = False

    def requester(_model: str, _messages: list[dict[str, str]]) -> str:
        nonlocal called
        called = True
        return "不应调用 [S1]。"

    with pytest.raises(GenerationServiceError, match="no_outbound_evidence"):
        generate_grounded_answer(
            "敏感问题",
            [evidence("L3"), evidence("L4"), evidence("L5")],
            founder=True,
            requester=requester,
        )
    assert called is False

    monkeypatch.setattr(
        generation,
        "settings",
        generation_settings(llm_l3_enabled=True),
    )
    result = generate_grounded_answer(
        "L3 问题",
        [evidence("L3"), evidence("L4"), evidence("L5")],
        founder=True,
        requester=requester,
    )
    assert result.evidence_document_ids == ["document-L3"]
    assert "L4" not in result.evidence_document_ids
    assert "L5" not in result.evidence_document_ids


def test_uncited_or_unknown_citation_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(generation, "settings", generation_settings())

    def requester(_model: str, _messages: list[dict[str, str]]) -> str:
        return "这是没有来源的事实。另一个错误引用 [S9]。"

    with pytest.raises(GenerationServiceError):
        generate_grounded_answer(
            "测试",
            [evidence()],
            founder=False,
            requester=requester,
        )


def test_freeform_writing_falls_back_without_fixed_template(monkeypatch) -> None:
    monkeypatch.setattr(generation, "settings", generation_settings())
    called: list[str] = []

    def requester(model: str, messages: list[dict[str, str]]) -> str:
        called.append(model)
        assert "不要套用固定提案模板" in messages[0]["content"]
        assert "写一份校企合作总结" in messages[1]["content"]
        if model == "grok-test":
            raise GenerationServiceError("gateway_http_429")
        return "# 校企合作总结\n\n项目开展了电竞课程与实训。[S1]"

    result = generate_grounded_draft(
        "写一份校企合作总结",
        [evidence()],
        founder=False,
        requester=requester,
    )

    assert called == ["grok-test", "deepseek-test"]
    assert result.fallback_used is True
    assert result.model == "deepseek-test"
    assert "[S1]" in result.answer


def test_transient_gateway_failure_retries_after_primary_and_fallback(
    monkeypatch,
) -> None:
    monkeypatch.setattr(generation, "settings", generation_settings())
    monkeypatch.setattr(generation.time, "sleep", lambda _seconds: None)
    called: list[str] = []

    def requester(model: str, _messages: list[dict[str, str]]) -> str:
        called.append(model)
        if len(called) <= 2:
            raise GenerationServiceError("gateway_unreachable")
        return "# 青训方案\n\n## 项目依据\n参考已确认的内部项目经验形成训练路径。[S1]"

    result = generate_grounded_draft(
        "写一份青训项目方案",
        [evidence()],
        founder=False,
        requester=requester,
    )

    assert called == ["grok-test", "deepseek-test", "grok-test"]
    assert result.model == "grok-test"
    assert result.fallback_used is False
    assert "[S1]" in result.answer


def test_model_timeouts_do_not_repeat_a_full_second_round(monkeypatch) -> None:
    monkeypatch.setattr(generation, "settings", generation_settings())
    called: list[str] = []

    def requester(model: str, _messages: list[dict[str, str]]) -> str:
        called.append(model)
        raise GenerationServiceError("gateway_timeout")

    with pytest.raises(GenerationServiceError, match="gateway_timeout"):
        generate_grounded_draft(
            "写一份青训项目方案",
            [evidence()],
            founder=False,
            requester=requester,
        )

    assert called == ["grok-test", "deepseek-test"]


def test_l3_writing_requires_explicit_founder_authorization(monkeypatch) -> None:
    monkeypatch.setattr(
        generation,
        "settings",
        generation_settings(llm_l3_enabled=True),
    )
    called = False

    def requester(_model: str, _messages: list[dict[str, str]]) -> str:
        nonlocal called
        called = True
        return "# 青训方案\n\n## 项目依据\n参考过往青训项目经验。[S1]"

    with pytest.raises(GenerationServiceError, match="no_outbound_evidence"):
        generate_grounded_draft(
            "写一份青训方案",
            [evidence("L3")],
            founder=True,
            allow_l3=False,
            requester=requester,
        )
    assert called is False

    result = generate_grounded_draft(
        "写一份青训方案",
        [evidence("L3")],
        founder=True,
        allow_l3=True,
        requester=requester,
    )
    assert result.evidence_document_ids == ["document-L3"]
