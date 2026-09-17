from __future__ import annotations

import re
import unicodedata


# The current company cost-centre registry.  The pattern intentionally also
# accepts future years/sequence values so a yearly code refresh does not need
# a database migration; this mapping supplies the current user-facing labels.
COST_CENTER_LABELS: dict[str, str] = {
    "CC26A01": "薪资社保",
    "CC26A02": "税费及财务费用",
    "CC26A03": "差旅",
    "CC26A04": "现金科目",
    "CC26A05": "总部招待",
    "CC26A06": "总部酒水",
    "CC26A07": "总部办公费用",
    "CC26A08": "总部车辆费用",
    "CC26A09": "总部装修费用",
    "CC26A10": "出借款",
    "CC26A11": "短信验证",
    "CC26B01": "KPL青训",
    "CC26B02": "KPL上海大培训",
    "CC26B03": "王者国家队集训",
    "CC26B04": "LPL青训",
    "CC26B05": "三角洲国际战队培训",
    "CC26B06": "后勤保障项目",
    "CC26B07": "德玛西亚杯",
    "CC26B08": "杭州童雅",
    "CC26B09": "上海业务",
    "CC26C01": "智子费用",
    "CC26C02": "商演项目",
    "CC26C03": "备用金",
    "CC26C04": "西安回款",
    "CC26C05": "国外战队奖金",
}

COST_CENTER_GROUP_LABELS = {
    "A": "总部费用",
    "B": "业务项目",
    "C": "其他项目",
}


def cost_center_catalog(year: int | None = None) -> list[dict[str, str]]:
    """Return the registered cost centres, optionally scoped to one year."""

    year_key = f"{year % 100:02d}" if year is not None else None
    return [
        {
            "code": code,
            "label": label,
            "group": COST_CENTER_GROUP_LABELS.get(code[4], "其他项目"),
        }
        for code, label in COST_CENTER_LABELS.items()
        if year_key is None or code[2:4] == year_key
    ]


def registered_cost_center_code(value: str | None) -> str | None:
    """Return the canonical code only when it exists in the company registry."""

    code = normalize_cost_center_code(value)
    return code if code in COST_CENTER_LABELS else None

COST_CENTER_CODE_RE = re.compile(r"^CC\d{2}[A-C]\d{2}$")
_FLEXIBLE_COST_CENTER_RE = re.compile(
    r"^CC[\s_-]?(\d{2})[\s_-]?([A-C])[\s_-]?(\d{2})$",
    re.IGNORECASE,
)
_EMBEDDED_COST_CENTER_RE = re.compile(
    r"(?<![A-Za-z0-9])CC[\s_-]?(\d{2})[\s_-]?([A-C])[\s_-]?(\d{2})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def normalize_cost_center_code(value: str | None) -> str | None:
    """Return a canonical ``CCYYANN`` code, or ``None`` when invalid."""

    text = unicodedata.normalize("NFKC", value or "").strip()
    match = _FLEXIBLE_COST_CENTER_RE.fullmatch(text)
    if not match:
        return None
    return f"CC{match.group(1)}{match.group(2).upper()}{match.group(3)}"


def extract_cost_center_code(value: str | None) -> str | None:
    """Find the first canonical cost-centre code inside bank-provided text."""

    text = unicodedata.normalize("NFKC", value or "")
    match = _EMBEDDED_COST_CENTER_RE.search(text)
    if not match:
        return None
    return f"CC{match.group(1)}{match.group(2).upper()}{match.group(3)}"
