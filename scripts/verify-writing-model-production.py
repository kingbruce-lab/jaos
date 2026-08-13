"""Call the production writing model with synthetic L1 evidence only."""

from __future__ import annotations

import json

from app.generation import GenerationEvidence, generate_grounded_draft


def main() -> None:
    result = generate_grounded_draft(
        "写一份两段式内部项目方案示例，包含项目目标和实施安排",
        [
            GenerationEvidence(
                document_id="synthetic-l1",
                title="自动化测试资料",
                version="test",
                page=1,
                status="current",
                confidentiality="L1",
                excerpt="测试项目目标是验证方案生成链路，实施分为准备和验收两个阶段。",
            )
        ],
        founder=False,
    )
    print(
        json.dumps(
            {
                "model": result.model,
                "fallback_used": result.fallback_used,
                "answer_characters": len(result.answer),
                "has_heading": result.answer.lstrip().startswith("#"),
                "has_citation": "[S1]" in result.answer,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
