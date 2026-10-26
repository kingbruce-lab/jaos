import pytest
import re
from pathlib import Path

from app.cost_centers import (
    cost_center_catalog, extract_cost_center_code,
    normalize_cost_center_code, registered_cost_center_code,
)
from app.project_system import _normalize_project_no


def test_2025_code_is_registered_separately_from_2026():
    assert cost_center_catalog(2025) == [{"code": "CC2501", "label": "25年数据", "group": "历史数据"}]
    assert len(cost_center_catalog()) == 37
    assert len(cost_center_catalog(2026)) == 36
    assert _normalize_project_no("Cc2501") == "CC2501"


@pytest.mark.parametrize("value", ["Cc2501", "cc2501", " CC2501 ", "ＣＣ２５０１", "cc-25-01"])
def test_legacy_bank_code_accepts_case_and_format_variations(value):
    assert registered_cost_center_code(value) == "CC2501"
    assert extract_cost_center_code(f"历史编码：{value}，收款") == "CC2501"


def test_legacy_exception_does_not_accept_unregistered_numeric_codes():
    for code in ("CC2502", "CC25010", "CC2619"):
        assert normalize_cost_center_code(code) is None
        assert extract_cost_center_code(code) is None
    assert registered_cost_center_code("CC26B05") == "CC26B05"


def test_latest_company_table_matches_project_and_finance_options():
    expected = {
        "CC26A00": "资本金", "CC26A01": "薪资社保", "CC26A02": "税费及财务费用",
        "CC26A03": "携程充值", "CC26A04": "现金科目", "CC26A05": "总部招待",
        "CC26A06": "总部酒水", "CC26A07": "总部办公费用", "CC26A08": "总部车辆费用",
        "CC26A09": "总部装修费用", "CC26A10": "出借款", "CC26A11": "备用金", "CC26A12": "对冲",
        "CC26B01": "KPL青训北京", "CC26B02": "KPL上海大培训", "CC26B03": "王者国家队集训",
        "CC26B04": "LPL青训", "CC26B05": "后勤保障项目", "CC26B06": "三角洲国际战队培训",
        "CC26B07": "德玛西亚杯", "CC26B08": "上海战队", "CC26B09": "星耀培训",
        "CC26B10": "KPL青训杭州", "CC26B11": "陪玩业务", "CC26B12": "Ai大会",
        "CC26B13": "E-TOWN超级冠军杯", "CC26C01": "智子费用", "CC26C02": "商演项目",
        "CC26C03": "未命名（预留）", "CC26C04": "西安回款", "CC26C05": "未命名（预留）",
        "CC26C06": "JAG项目", "CC26C07": "PD青训费用", "CC26C08": "叶总费用",
        "CC26C09": "繁星费用", "CC26C10": "卓总费用",
    }
    assert {item["code"]: item["label"] for item in cost_center_catalog(2026)} == expected
    page = (Path(__file__).resolve().parents[2] / "app" / "page.tsx").read_text(encoding="utf-8")
    options = page.split("const COST_CENTER_OPTIONS = [", 1)[1].split("] as const;", 1)[0]
    assert dict(re.findall(r'\["(CC[^\"]+)", "([^\"]+)"\]', options)) == {"CC2501": "25年数据", **expected}
    for code in ("Cc26A12", "Cc26B11", "Cc26B12", "Cc26B13", "Cc26C03", "Cc26C05"):
        assert registered_cost_center_code(code) == code.upper()
        assert _normalize_project_no(code) == code.upper()
