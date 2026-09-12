from __future__ import annotations

import unicodedata


BUSINESS_ENTITY_DEFINITIONS = (
    {
        "key": "jingao",
        "name": "京奥电竞（北京）科技有限公司",
        "display_name": "京奥电竞",
        "business_name": "总公司",
        "account_label": "北京银行成寿寺支行账户",
        "default_bank_name": "北京银行成寿寺支行",
        "is_headquarters": True,
    },
    {
        "key": "ace-leopard",
        "name": "王牌猎豹（JAG三角洲）",
        "display_name": "王牌猎豹",
        "business_name": "JAG三角洲",
        "account_label": "独立银行账户",
        "default_bank_name": "",
        "is_headquarters": False,
    },
    {
        "key": "power-leopard",
        "name": "劲腾豹跃（JAG王者）",
        "display_name": "劲腾豹跃",
        "business_name": "JAG王者",
        "account_label": "独立银行账户",
        "default_bank_name": "",
        "is_headquarters": False,
    },
    {
        "key": "xingyao",
        "name": "星曜电竞",
        "display_name": "星曜电竞",
        "business_name": "电竞教培",
        "account_label": "独立银行账户",
        "default_bank_name": "",
        "is_headquarters": False,
    },
)

BUSINESS_ENTITY_NAMES = {
    item["name"] for item in BUSINESS_ENTITY_DEFINITIONS
}
HEADQUARTERS_ENTITY_NAME = BUSINESS_ENTITY_DEFINITIONS[0]["name"]
LEGACY_HEADQUARTERS_ENTITY_NAMES = {"京奥电竞"}
BUSINESS_ENTITY_ALIASES = {
    **{
        unicodedata.normalize("NFKC", item["name"]).strip(): item["name"]
        for item in BUSINESS_ENTITY_DEFINITIONS
    },
    **{
        unicodedata.normalize("NFKC", item["display_name"]).strip(): item["name"]
        for item in BUSINESS_ENTITY_DEFINITIONS
    },
    "JAG三角洲": BUSINESS_ENTITY_DEFINITIONS[1]["name"],
    "JAG王者": BUSINESS_ENTITY_DEFINITIONS[2]["name"],
}
BUSINESS_ENTITY_BY_NAME = {
    item["name"]: item for item in BUSINESS_ENTITY_DEFINITIONS
}


def canonical_business_entity_name(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    return BUSINESS_ENTITY_ALIASES.get(normalized)
