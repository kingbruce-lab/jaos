"""Repair the 2026 B05/B06 project-code inversion.

Run from agent/: python repair_cost_centers_20260929.py
Apply after reviewing the preview: python repair_cost_centers_20260929.py --apply --journal /secure/path/repair.json
Bank source codes, amounts and memos are never rewritten.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import os

from sqlalchemy import create_engine, select, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from app.cost_centers import normalize_cost_center_code
# Map only the columns repaired here; no application startup or schema changes.
class RepairBase(DeclarativeBase):
    pass


class ManagedProject(RepairBase):
    __tablename__ = "managed_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_no: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(36))


class BankTransaction(RepairBase):
    __tablename__ = "bank_transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_reference: Mapped[str | None] = mapped_column(String(80))
    pm_project_id: Mapped[str | None] = mapped_column(String(36))
    entity_id: Mapped[str] = mapped_column(String(36))


EXPECTED = {"CC26B05": "后勤保障项目", "CC26B06": "三角洲国际战队培训"}


def repair(db, *, apply=False, entity_id=None):
    projects = db.scalars(select(ManagedProject).with_for_update()).all()
    relevant = [p for p in projects if normalize_cost_center_code(p.project_no) in EXPECTED
                and (entity_id is None or p.entity_id == entity_id)]
    renames = []
    for p in relevant:
        if p.name not in EXPECTED.values():
            raise ValueError(f"项目名称需要人工核对: {p.id} / {p.project_no} / {p.name}")
        wanted = next(code for code, name in EXPECTED.items() if name == p.name)
        if p.project_no != wanted:
            renames.append({"id": p.id, "before": p.project_no, "after": wanted})
    proposed = {p.id: p.project_no for p in projects}
    proposed.update({r["id"]: r["after"] for r in renames})
    if len(set(proposed.values())) != len(proposed):
        raise ValueError("修正后项目编码冲突，未作修改")
    targets = {proposed[p.id]: p for p in relevant if p.status != "deleted"}
    affected_ids = {p.id for p in relevant}
    links = []
    for t in db.scalars(select(BankTransaction).with_for_update()).all():
        if entity_id is not None and t.entity_id != entity_id:
            if t.pm_project_id in affected_ids:
                raise ValueError(f"流水 {t.id} 跨公司关联待修复项目，需要人工核对")
            continue
        code = normalize_cost_center_code(t.project_reference)
        if code not in EXPECTED and t.pm_project_id not in affected_ids:
            continue
        if code not in EXPECTED:
            raise ValueError(f"流水 {t.id} 的编码与关联项目冲突，需要人工核对")
        target = targets.get(code)
        if target and target.entity_id != t.entity_id:
            raise ValueError(f"流水 {t.id} 与目标项目公司不一致，需要人工核对")
        wanted_id = target.id if target else None
        if t.pm_project_id != wanted_id:
            links.append({"id": t.id, "code": code, "before": t.pm_project_id, "after": wanted_id})
    plan = {"project_codes": renames, "transaction_links": links}
    if apply:
        by_id = {p.id: p for p in projects}
        for r in renames:
            by_id[r["id"]].project_no = f"repair-{r['id'][:32]}"
        db.flush()
        for r in renames:
            by_id[r["id"]].project_no = r["after"]
        for r in links:
            db.get(BankTransaction, r["id"]).pm_project_id = r["after"]
        db.flush()
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--entity-id", help="Only repair this company's projects and transactions")
    args = parser.parse_args()
    if args.apply and not args.journal:
        parser.error("--apply requires --journal for the before/after audit record")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("Set DATABASE_URL explicitly to the database to inspect/repair")
    SessionLocal = sessionmaker(bind=create_engine(database_url), autoflush=False)
    with SessionLocal() as db:
        plan = repair(db, entity_id=args.entity_id)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        if args.apply:
            # Exclusive create: never overwrite an earlier migration journal.
            with args.journal.open("x", encoding="utf-8") as stream:
                json.dump({"status": "planned", **plan}, stream, ensure_ascii=False, indent=2)
            applied = repair(db, apply=True, entity_id=args.entity_id)
            if applied != plan:
                raise RuntimeError("数据已变化，事务回滚，请重新预览")
            db.commit()
            args.journal.write_text(
                json.dumps({"status": "committed", **plan}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            db.rollback()


if __name__ == "__main__":
    main()
