from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import Document


@dataclass(frozen=True)
class ConfidentialitySuggestion:
    level: str
    confidence: str
    reason: str
    requires_manual_review: bool = False

    def payload(self) -> dict:
        return asdict(self)


L4_TERMS = (
    "身份证", "护照", "银行卡", "银行账户", "工资表", "薪酬", "绩效考核",
    "人事评价", "员工档案", "劳动合同", "体检报告", "征信", "户口",
    "密码", "密钥", "私钥", "未成年人档案",
)

L3_TERMS = (
    "合同", "协议", "报价", "预算", "成本", "采购", "招标", "投标",
    "发票", "付款", "收款", "结算", "验收单", "人员名单", "人员登记",
    "报名表", "签到表", "通讯录", "手机号", "风险点", "风险预案",
    "应急预案", "账号清单", "财务", "利润", "分成", "保密",
)

PUBLIC_TITLE_TERMS = (
    "海报", "宣传", "新闻稿", "新闻报道", "公众号", "官宣", "直播",
    "活动照片", "比赛照片", "合影", "颁奖", "获奖", "成绩发布",
    "公开课", "招生简章", "招募海报", "赛程", "赛事规则", "参赛指南",
)

PII_PATTERNS = (
    re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?:银行卡|银行账号|开户行).{0,24}\d{8,}"),
)

FINANCIAL_PATTERNS = (
    re.compile(r"(?:报价|预算|成本|结算|付款|收款)\s*[:：]?\s*[￥¥]?\s*\d"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:万元|万|元)\s*(?:预算|报价|成本|费用)"),
)


def _matched_term(value: str, terms: tuple[str, ...]) -> str | None:
    return next((term for term in terms if term in value), None)


def classify_confidentiality(
    *,
    title: str,
    project_name: str,
    role: str,
    text: str = "",
    source_suffix: str = "",
) -> ConfidentialitySuggestion:
    """Conservative local classifier; no document content leaves the NAS."""
    heading = f"{title} {project_name}".lower()
    evidence = f"{heading}\n{text[:8000]}".lower()

    l4_term = _matched_term(evidence, L4_TERMS)
    if l4_term:
        return ConfidentialitySuggestion(
            level="L4",
            confidence="high",
            reason=f"检测到核心敏感信息特征：{l4_term}",
            requires_manual_review=True,
        )

    if any(pattern.search(evidence) for pattern in PII_PATTERNS):
        return ConfidentialitySuggestion(
            level="L3",
            confidence="high",
            reason="检测到身份证号、手机号或银行账号等个人信息特征",
        )

    l3_term = _matched_term(heading, L3_TERMS)
    if l3_term:
        return ConfidentialitySuggestion(
            level="L3",
            confidence="high",
            reason=f"文件名或项目名包含业务敏感特征：{l3_term}",
        )

    if any(pattern.search(evidence) for pattern in FINANCIAL_PATTERNS):
        return ConfidentialitySuggestion(
            level="L3",
            confidence="high",
            reason="正文包含明确的报价、预算、成本或结算金额",
        )

    if role == "closing_report":
        return ConfidentialitySuggestion(
            level="L3",
            confidence="medium",
            reason="结案与验收资料默认按业务敏感资料处理",
        )

    if role == "company_profile":
        return ConfidentialitySuggestion(
            level="L1",
            confidence="high",
            reason="已登记的公司介绍属于公司公共资料",
        )

    public_term = _matched_term(heading, PUBLIC_TITLE_TERMS)
    if public_term:
        return ConfidentialitySuggestion(
            level="L1",
            confidence="medium",
            reason=f"文件名显示为对外公开或宣传素材：{public_term}",
        )

    if role == "asset":
        media = source_suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov",
            ".m4v", ".mp3", ".m4a", ".wav", ".flac", ".ai",
        }
        return ConfidentialitySuggestion(
            level="L2",
            confidence="medium" if media else "low",
            reason="普通项目素材默认归为业务普通资料",
        )

    if role in {"proposal", "execution", "brief"}:
        return ConfidentialitySuggestion(
            level="L2",
            confidence="medium",
            reason="未命中敏感特征的普通方案或执行文档",
        )

    return ConfidentialitySuggestion(
        level="L3",
        confidence="low",
        reason="资料类型无法可靠判断，保守保留为业务敏感资料",
        requires_manual_review=True,
    )


def suggest_document_confidentiality(
    document: Document,
) -> ConfidentialitySuggestion:
    text = "\n".join(
        chunk.text
        for chunk in sorted(document.chunks, key=lambda item: item.chunk_index)
        if chunk.text
    )[:8000]
    suffix = (
        Path(document.file_blob.source_path).suffix.lower()
        if document.file_blob
        else ""
    )
    return classify_confidentiality(
        title=document.title,
        project_name=document.project.name,
        role=document.role,
        text=text,
        source_suffix=suffix,
    )
