from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import KnowledgeCategory


DEFAULT_CATEGORIES = (
    ("training", "电竞培训", 10),
    ("youth", "电竞青训", 20),
    ("team", "电竞战队", 30),
    ("tournament", "电竞赛事", 40),
    ("venue", "场馆运营", 50),
    ("company", "公司公共", 60),
)


def seed_default_categories(db: Session) -> None:
    existing = set(db.scalars(select(KnowledgeCategory.key)).all())
    changed = False
    for key, name, sort_order in DEFAULT_CATEGORIES:
        if key in existing:
            continue
        db.add(
            KnowledgeCategory(
                key=key,
                name=name,
                active=True,
                sort_order=sort_order,
            )
        )
        changed = True
    if changed:
        db.commit()

