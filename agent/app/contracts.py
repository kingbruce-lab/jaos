from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CONTRACT_ARCHIVE_FOLDER = "合同档案库"
CONTRACT_UPLOAD_SUFFIXES = {".pdf", ".doc", ".docm", ".docx"}


@dataclass(frozen=True)
class ContractCategory:
    key: str
    name: str
    domain: str
    confidentiality: str


CONTRACT_CATEGORIES: dict[str, ContractCategory] = {
    "administrative": ContractCategory(
        "administrative", "行政合同", "contract_administrative", "L4"
    ),
    "personnel": ContractCategory(
        "personnel", "人事合同", "contract_personnel", "L4"
    ),
    "business": ContractCategory(
        "business", "业务合同", "contract_business", "L4"
    ),
    "executive_office": ContractCategory(
        "executive_office", "总办合同", "contract_executive_office", "L5"
    ),
}
CONTRACT_DOMAINS = tuple(item.domain for item in CONTRACT_CATEGORIES.values())
CONTRACT_CATEGORIES_BY_DOMAIN = {
    item.domain: item for item in CONTRACT_CATEGORIES.values()
}

# Stable folders that must remain available even before a first document is filed.
# In particular, L5 contracts must never be moved outside the executive-office
# security root just because an administrator wants to treat them as internal
# materials.
CONTRACT_DEFAULT_FOLDERS: dict[str, tuple[str, ...]] = {
    "executive_office": ("内部资料（密）",),
}


def ensure_contract_layout(knowledge_root: Path) -> dict[str, Path]:
    root = knowledge_root.resolve()
    archive = (root / CONTRACT_ARCHIVE_FOLDER).resolve()
    archive.relative_to(root)
    result: dict[str, Path] = {}
    for key, category in CONTRACT_CATEGORIES.items():
        target = (archive / category.name / category.confidentiality).resolve()
        target.relative_to(archive)
        target.mkdir(parents=True, exist_ok=True)
        for folder in CONTRACT_DEFAULT_FOLDERS.get(key, ()):
            default_folder = (target / folder).resolve()
            default_folder.relative_to(target)
            default_folder.mkdir(parents=True, exist_ok=True)
        result[key] = target
    return result


def is_contract_archive_path(relative_path: Path) -> bool:
    return bool(
        relative_path.parts
        and relative_path.parts[0].casefold() == CONTRACT_ARCHIVE_FOLDER.casefold()
    )


def contract_category_for_path(relative_path: Path) -> ContractCategory | None:
    if not is_contract_archive_path(relative_path):
        return None
    if len(relative_path.parts) < 4:
        raise ValueError("合同档案必须放在 合同档案库/合同分类/密级/文件名")
    category_name = relative_path.parts[1].casefold()
    category = next(
        (
            item
            for item in CONTRACT_CATEGORIES.values()
            if item.name.casefold() == category_name
        ),
        None,
    )
    if category is None:
        raise ValueError("未知合同分类")
    if relative_path.parts[2].upper() != category.confidentiality:
        raise ValueError(
            f"{category.name}必须存放在{category.confidentiality}目录"
        )
    return category
