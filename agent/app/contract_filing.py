from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class ContractFolderSuggestion:
    folder: str
    confidence: str
    matched_keywords: tuple[str, ...]


CONTRACT_FOLDER_RULES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "administrative": (
        ("租赁与物业", ("租赁", "房屋", "办公室", "写字楼", "场地", "物业", "水电", "装修")),
        ("采购与供应商", ("采购", "供应商", "供货", "设备", "物料", "办公用品", "采购订单")),
        ("行政服务", ("行政服务", "代理服务", "咨询服务", "印刷", "物流", "快递", "保洁", "餐饮")),
        ("资质证照", ("许可证", "资质", "证照", "商标", "著作权", "知识产权")),
    ),
    "personnel": (
        ("劳动用工", ("劳动合同", "劳动关系", "员工", "入职", "用工", "聘用")),
        ("劳务与兼职", ("劳务", "兼职", "顾问", "外包人员")),
        ("保密与竞业", ("保密", "竞业", "商业秘密", "知识产权归属")),
        ("实习与校企", ("实习", "实习生", "校企", "就业")),
        ("薪酬与福利", ("薪酬", "工资", "奖金", "社保", "公积金", "福利")),
    ),
    "business": (
        ("赛事与活动", ("赛事", "比赛", "联赛", "活动", "执行服务", "赛程", "电竞节")),
        ("培训与青训", ("培训", "青训", "训练营", "课程", "教育", "教学", "选秀")),
        ("战队与选手", ("战队", "俱乐部", "选手", "教练", "经纪", "签约选手")),
        ("品牌与商务", ("品牌", "广告", "赞助", "商务", "推广", "营销", "宣传", "直播")),
        ("技术与平台", ("软件", "技术开发", "系统开发", "平台", "小程序", "网站", "信息技术")),
        ("项目合作", ("项目合作", "合作协议", "框架协议", "战略合作", "服务合同", "委托服务")),
    ),
    "executive_office": (
        ("股权与投融资", ("股权", "股份", "增资", "投资", "融资", "并购", "估值")),
        ("公司治理", ("董事会", "股东会", "公司治理", "章程", "表决权", "实际控制人")),
        ("重大合作", ("重大合作", "独家", "排他", "战略协议", "重大项目")),
        ("高管与核心人员", ("高管", "核心人员", "创始人", "总经理", "董事", "高级管理人员")),
        ("涉密事项", ("最高机密", "绝密", "涉密", "保密协议", "商业秘密")),
    ),
}


FALLBACK_FOLDERS = {
    "administrative": "待人工整理",
    "personnel": "待人工整理",
    "business": "待人工整理",
    "executive_office": "待人工整理",
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"\s+", "", value)


def suggest_contract_folder(
    category_key: str,
    *,
    title: str,
    text: str,
) -> ContractFolderSuggestion:
    """Classify sensitive contracts locally without calling any cloud model."""
    title_text = _normalize(title)
    body_text = _normalize(text[:30000])
    scored: list[tuple[int, int, str, tuple[str, ...]]] = []
    for order, (folder, keywords) in enumerate(CONTRACT_FOLDER_RULES.get(category_key, ())):
        matched: list[str] = []
        score = 0
        for keyword in keywords:
            normalized = _normalize(keyword)
            if normalized and normalized in title_text:
                score += 5
                matched.append(keyword)
            elif normalized and normalized in body_text:
                score += 1
                matched.append(keyword)
        if score:
            scored.append((score, -order, folder, tuple(dict.fromkeys(matched))))
    if not scored:
        return ContractFolderSuggestion(
            folder=FALLBACK_FOLDERS.get(category_key, "待人工整理"),
            confidence="low",
            matched_keywords=(),
        )
    score, _order, folder, matched = max(scored)
    confidence = "high" if score >= 6 or len(matched) >= 2 else "medium"
    return ContractFolderSuggestion(
        folder=folder,
        confidence=confidence,
        matched_keywords=matched[:5],
    )
