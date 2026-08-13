from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import Connection, select, text, update
from sqlalchemy.orm import Session

from .models import ManagedProject, ProjectNumberSequence


SHANGHAI_ZONE = ZoneInfo("Asia/Shanghai")
PROJECT_NUMBER_LIMIT = 100
PROJECT_NUMBER_RE = re.compile(
    r"^JADJ-Cc(?P<year>\d{2})(?P<sequence>0[1-9]|[1-9]\d|100)$"
)


def project_number_year(now: datetime | None = None) -> int:
    """Return the two-digit project segment year in the company's timezone."""

    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(SHANGHAI_ZONE).year


def format_project_number(year: int, sequence: int) -> str:
    if not 1 <= sequence <= PROJECT_NUMBER_LIMIT:
        raise ValueError("project sequence must be between 1 and 100")
    suffix = "100" if sequence == PROJECT_NUMBER_LIMIT else f"{sequence:02d}"
    return f"JADJ-Cc{year % 100:02d}{suffix}"


def allocate_project_number(db: Session, *, year: int | None = None) -> str:
    """Allocate one project number transactionally.

    PostgreSQL uses one atomic UPSERT/RETURNING statement, so concurrent
    project creations cannot receive the same number.  The counter update is
    part of the caller's transaction and rolls back if project creation fails.
    """

    segment_year = year or project_number_year()
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        sequence = db.execute(
            text(
                """
                INSERT INTO project_number_sequences (year, last_value)
                VALUES (:year, 1)
                ON CONFLICT (year) DO UPDATE
                SET last_value = project_number_sequences.last_value + 1
                WHERE project_number_sequences.last_value < :limit
                RETURNING last_value
                """
            ),
            {"year": segment_year, "limit": PROJECT_NUMBER_LIMIT},
        ).scalar_one_or_none()
    else:
        # SQLite is used by the isolated test suite.  The production path
        # above is the concurrency-safe allocator used on the NAS.
        counter = db.get(ProjectNumberSequence, segment_year)
        if counter is None:
            counter = ProjectNumberSequence(year=segment_year, last_value=1)
            db.add(counter)
            db.flush()
            sequence = 1
        elif counter.last_value < PROJECT_NUMBER_LIMIT:
            counter.last_value += 1
            db.flush()
            sequence = counter.last_value
        else:
            sequence = None

    if sequence is None:
        raise HTTPException(
            status_code=409,
            detail=f"{segment_year} 年项目编号已达到 100 个上限，请联系系统管理员",
        )
    return format_project_number(segment_year, int(sequence))


def migrate_existing_project_numbers(connection: Connection) -> int:
    """Idempotently renumber legacy projects by creation time and stable id.

    Deleted projects remain in the sequence so an audited number is never
    reused.  A temporary unique value is assigned first to avoid collisions
    when legacy and new-format numbers coexist during deployment.
    """

    rows = connection.execute(
        select(
            ManagedProject.id,
            ManagedProject.project_no,
            ManagedProject.created_at,
        ).order_by(ManagedProject.created_at.asc(), ManagedProject.id.asc())
    ).mappings().all()

    # Once the one-time migration has completed, preserve issued numbers
    # exactly. This also prevents a later restart from renumbering projects
    # whose transactions happened to commit in a different order.
    parsed_numbers = [PROJECT_NUMBER_RE.fullmatch(row["project_no"] or "") for row in rows]
    if all(parsed_numbers):
        maxima: dict[int, int] = defaultdict(int)
        for match in parsed_numbers:
            assert match is not None
            year = 2000 + int(match.group("year"))
            maxima[year] = max(maxima[year], int(match.group("sequence")))
        for year, last_value in maxima.items():
            _set_sequence(connection, year=year, last_value=last_value)
        return 0

    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        created_at = row["created_at"]
        if created_at is None:
            # ORM defaults normally make this impossible.  Keep the migration
            # deterministic for any hand-created legacy row.
            year = 2000
        else:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            year = created_at.astimezone(SHANGHAI_ZONE).year
        grouped[year].append(dict(row))

    desired: dict[str, str] = {}
    for year, items in grouped.items():
        if len(items) > PROJECT_NUMBER_LIMIT:
            raise RuntimeError(
                f"cannot migrate {len(items)} projects created in {year}: "
                f"the JADJ-Cc numbering segment is limited to {PROJECT_NUMBER_LIMIT}"
            )
        for sequence, row in enumerate(items, start=1):
            desired[row["id"]] = format_project_number(year, sequence)

    changed = [row for row in rows if row["project_no"] != desired[row["id"]]]
    if changed:
        for row in changed:
            connection.execute(
                update(ManagedProject)
                .where(ManagedProject.id == row["id"])
                .values(project_no=f"~{row['id']}")
            )
        for row in changed:
            connection.execute(
                update(ManagedProject)
                .where(ManagedProject.id == row["id"])
                .values(project_no=desired[row["id"]])
            )

    for year, items in grouped.items():
        _set_sequence(connection, year=year, last_value=len(items))
    return len(changed)


def _set_sequence(connection: Connection, *, year: int, last_value: int) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                """
                INSERT INTO project_number_sequences (year, last_value)
                VALUES (:year, :last_value)
                ON CONFLICT (year) DO UPDATE
                SET last_value = GREATEST(
                    project_number_sequences.last_value,
                    EXCLUDED.last_value
                )
                """
            ),
            {"year": year, "last_value": last_value},
        )
        return
    existing = connection.execute(
        select(ProjectNumberSequence.last_value).where(
            ProjectNumberSequence.year == year
        )
    ).scalar_one_or_none()
    if existing is None:
        connection.execute(
            ProjectNumberSequence.__table__.insert().values(
                year=year, last_value=last_value
            )
        )
    elif existing < last_value:
        connection.execute(
            update(ProjectNumberSequence)
            .where(ProjectNumberSequence.year == year)
            .values(last_value=last_value)
        )
