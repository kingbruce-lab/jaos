from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from .schemas import ProposalBrief


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
PROPOSAL_TEMPLATE = ASSET_DIR / "jingao-proposal-template.pptx"
TOKEN_PATTERN = re.compile(rb"\{\{[A-Z0-9_]+\}\}")


class ProposalPptxError(RuntimeError):
    pass


def _short(value: str | None, limit: int, fallback: str = "待确认") -> str:
    normalized = " ".join((value or "").split())
    if not normalized:
        return fallback
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def _case_label(item: dict, limit: int = 48) -> str:
    title = _short(item.get("title"), 32, "候选资料")
    page = item.get("page")
    value = f"候选｜{title}"
    if page:
        value += f" · 第{page}页"
    return _short(value, limit)


def _source_line(evidence: list[dict]) -> str:
    if not evidence:
        return "来源：JAOS 知识库提案结构；资料中未找到可引用历史案例"
    labels = [_case_label(item, 34) for item in evidence[:2]]
    return _short(f"来源：JAOS 知识库提案结构；{'；'.join(labels)}", 108)


def _notes_source(brief: ProposalBrief, evidence: list[dict]) -> str:
    brief_source = f"用户提交 Brief（本次生成）：{_short(brief.title, 80)}"
    if not evidence:
        return f"{brief_source}\n资料中未找到可引用历史案例。"
    citations = []
    for item in evidence[:5]:
        citations.append(
            f"{_short(item.get('title'), 80, '候选资料')}｜"
            f"版本状态：{item.get('knowledge_status', 'candidate')}｜"
            f"页码：{item.get('page', '待核验')}"
        )
    return f"{brief_source}\n候选参考：{'；'.join(citations)}"


def proposal_replacements(
    brief: ProposalBrief,
    evidence: list[dict],
    missing: list[str],
) -> dict[str, str]:
    source = _source_line(evidence)
    notes = _notes_source(brief, evidence)
    deliverables = _short(brief.deliverables, 64)
    audience = _short(brief.audience, 64)
    objective = _short(brief.objective, 80)
    duration = _short(brief.duration, 30)
    customer = _short(brief.client, 40, "客户待确认")
    geography = _short(brief.geography, 30)
    budget = _short(brief.budget, 30)
    missing_items = [f"• {item}：待补充" for item in missing[:4]]
    missing_items.extend(["—"] * (4 - len(missing_items)))
    case_items = [_case_label(item) for item in evidence[:4]]
    if not case_items:
        case_items = ["资料中未找到可引用历史案例"]
    case_items.extend(["—"] * (4 - len(case_items)))

    values = {
        "COVER_EYEBROW": "JINGAO ESPORTS · PROPOSAL DRAFT",
        "COVER_TITLE": _short(brief.title, 48),
        "COVER_SUBTITLE": f"京奥电竞 × {customer}",
        "COVER_META": f"电竞培训提案初稿｜{date.today().isoformat()}｜内部可编辑",
        "S1_NOTES": notes,
        "S2_TITLE": "先对齐需求，再进入方案设计",
        "S2_INTRO": "以下内容仅复述本次 Brief；未填写项保持“待确认”。",
        "S2_LINE1": f"项目目标｜{objective}",
        "S2_LINE2": f"目标受众｜{audience}",
        "S2_LINE3": f"实施范围｜{geography} · 周期 {duration}",
        "S2_LINE4": f"预算边界｜{budget}",
        "S2_LINE5": f"预期交付｜{deliverables}",
        "S2_SOURCE": "来源：本次提交 Brief（全部字段待业务确认）",
        "S2_NOTES": f"用户提交 Brief（本次生成）：{_short(brief.title, 80)}",
        "S3_TITLE": "目标体系必须能够被验收",
        "S3_HEAD1": "业务目标",
        "S3_BODY1": objective,
        "S3_HEAD2": "参与者目标",
        "S3_BODY2": f"面向 {audience}，具体能力变化与起点待确认。",
        "S3_HEAD3": "验收目标",
        "S3_BODY3": f"以 {deliverables} 为基础，补充数量、质量和时限口径。",
        "S3_SOURCE": "来源：本次 Brief；指标数值需双方确认后填写",
        "S3_NOTES": f"用户提交 Brief（本次生成）：目标={objective}；受众={audience}；交付={deliverables}",
        "S4_TITLE": "用四个阶段完成从需求到成果的闭环",
        "S4_HEAD1": "诊断",
        "S4_BODY1": "确认目标、对象与关键约束",
        "S4_HEAD2": "学习",
        "S4_BODY2": "配置知识模块与专项训练",
        "S4_HEAD3": "实训",
        "S4_BODY3": "用任务场景形成可展示成果",
        "S4_HEAD4": "评估",
        "S4_BODY4": "记录过程、验收结果并复盘",
        "S4_CONCLUSION": "每一阶段都留下可追溯材料，为结案与后续迭代服务。",
        "S4_SOURCE": source,
        "S4_NOTES": notes,
        "S5_TITLE": "课程与活动围绕成果逐层展开",
        "S5_HEAD1": "基础认知",
        "S5_BODY1": "统一概念、规则与行业理解，具体深度根据受众基础调整。",
        "S5_HEAD2": "专项训练",
        "S5_BODY2": "围绕项目目标配置主题模块，课程名称与课时待确认。",
        "S5_HEAD3": "情境实训",
        "S5_BODY3": "通过模拟任务、分组协作和现场演练形成阶段成果。",
        "S5_HEAD4": "复盘提升",
        "S5_BODY4": "记录过程数据、问题与改进建议，沉淀到结案报告。",
        "S5_OUTPUT": f"预期成果：{deliverables}",
        "S5_SOURCE": source,
        "S5_NOTES": notes,
        "S6_TITLE": "执行节奏按四个里程碑推进",
        "S6_HEAD1": "需求冻结",
        "S6_TIME1": "阶段 1",
        "S6_BODY1": "确认范围、负责人、时间、预算与验收口径。",
        "S6_HEAD2": "内容准备",
        "S6_TIME2": "阶段 2",
        "S6_BODY2": "完成课程、师资、场地、物料与学员组织。",
        "S6_HEAD3": "现场交付",
        "S6_TIME3": "阶段 3",
        "S6_BODY3": "按计划实施并记录出勤、过程表现和阶段成果。",
        "S6_HEAD4": "验收结案",
        "S6_TIME4": "阶段 4",
        "S6_BODY4": "汇总结果、问题和复盘，提交可追溯结案材料。",
        "S6_COORDINATION": f"建议总周期：{duration}；具体日期、人员和场地在启动会上冻结。",
        "S6_SOURCE": source,
        "S6_NOTES": notes,
        "S7_TITLE": "结案不只交材料，还要留下可复用经验",
        "S7_HEAD1": "过程记录",
        "S7_BODY1": "出勤、课程、任务、现场照片与异常处理记录。",
        "S7_HEAD2": "成果验收",
        "S7_BODY2": f"围绕“{deliverables}”确认数量、质量和交付时间。",
        "S7_HEAD3": "效果评估",
        "S7_BODY3": "结合前后测、作品、反馈或业务指标，选择适用口径。",
        "S7_HEAD4": "项目复盘",
        "S7_BODY4": "形成结案报告、经验教训和下次可复用模块。",
        "S7_SOURCE": source,
        "S7_NOTES": notes,
        "S8_TITLE": "确认关键边界后，即可进入正式提案",
        "S8_MISSING1": missing_items[0],
        "S8_MISSING2": missing_items[1],
        "S8_MISSING3": missing_items[2],
        "S8_MISSING4": missing_items[3],
        "S8_CASE1": case_items[0],
        "S8_CASE2": case_items[1],
        "S8_CASE3": case_items[2],
        "S8_CASE4": case_items[3],
        "S8_CLOSE": "下一步：补齐待确认信息，由业务负责人审核事实与引用后形成对外版本。",
        "S8_SOURCE": source,
        "S8_NOTES": notes,
    }
    return {f"{{{{{key}}}}}": value for key, value in values.items()}


def render_proposal_pptx(
    brief: ProposalBrief,
    evidence: list[dict],
    missing: list[str],
    template_path: Path = PROPOSAL_TEMPLATE,
) -> bytes:
    if not template_path.is_file():
        raise ProposalPptxError("proposal_template_missing")
    replacements = proposal_replacements(brief, evidence, missing)
    output = io.BytesIO()
    found: set[str] = set()
    try:
        with zipfile.ZipFile(template_path, "r") as source:
            with zipfile.ZipFile(
                output,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as target:
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename.endswith((".xml", ".rels")):
                        text = data.decode("utf-8")
                        for token, value in replacements.items():
                            if token in text:
                                found.add(token)
                                text = text.replace(token, escape(value))
                        data = text.encode("utf-8")
                    target.writestr(item, data)
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise ProposalPptxError("proposal_template_invalid") from exc
    missing_tokens = sorted(set(replacements) - found)
    if missing_tokens:
        raise ProposalPptxError(
            f"proposal_template_tokens_missing:{','.join(missing_tokens)}"
        )
    payload = output.getvalue()
    if TOKEN_PATTERN.search(payload):
        raise ProposalPptxError("proposal_template_has_unresolved_tokens")
    return payload
