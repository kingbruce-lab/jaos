import pytest

from app.cost_centers import (
    cost_center_catalog, extract_cost_center_code,
    normalize_cost_center_code, registered_cost_center_code,
)
from app.project_system import _normalize_project_no


def test_2025_code_is_registered_separately_from_2026():
    assert cost_center_catalog(2025) == [{"code": "CC2501", "label": "25年数据", "group": "历史数据"}]
    assert len(cost_center_catalog()) == 33
    assert len(cost_center_catalog(2026)) == 32
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
