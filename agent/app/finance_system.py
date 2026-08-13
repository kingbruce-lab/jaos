from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import secrets
import unicodedata
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from openpyxl import load_workbook
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user
from .business_entities import (
    BUSINESS_ENTITY_DEFINITIONS,
    BUSINESS_ENTITY_NAMES,
    HEADQUARTERS_ENTITY_NAME,
    LEGACY_HEADQUARTERS_ENTITY_NAMES,
)
from .config import settings
from .database import get_db
from .models import (
    AuditLog,
    BankStatementBatch,
    BankTransaction,
    BusinessEntity,
    CashEntry,
    FinancialAccount,
    ManagedProject,
    User,
)
from .retrieval import CONFIDENTIALITY_RANK


router = APIRouter(prefix="/v1/finance", tags=["finance"])

EXECUTIVE_USERNAMES = {"found", "founder", "jaanliyuan"}
SUPPORTED_STATEMENTS = {".xlsx", ".csv"}
SHANGHAI_ZONE = ZoneInfo("Asia/Shanghai")
FINANCE_ENTITY_DEFINITIONS = BUSINESS_ENTITY_DEFINITIONS
FINANCE_ENTITY_NAMES = BUSINESS_ENTITY_NAMES

# A large payment is not inherently abnormal: the Top 10 panels already
# explain amount concentration.  Behaviour alerts instead compare a party
# with its own confirmed history using these deliberately conservative,
# auditable thresholds.
BEHAVIOUR_SPIKE_MIN_HISTORY = 3
BEHAVIOUR_SPIKE_MULTIPLIER = Decimal("3")
BEHAVIOUR_SPIKE_MIN_DIFFERENCE = Decimal("10000")

OA_PLANNED_ALERT_RULES = (
    {"code": "oa_expense_without_approval", "name": "无审批支出"},
    {"code": "oa_payee_mismatch", "name": "实际收款方与审批收款方不一致"},
    {"code": "oa_amount_exceeded", "name": "实际付款金额超过审批金额"},
    {"code": "oa_duplicate_payment", "name": "同一审批单重复付款"},
    {
        "code": "project_budget_overrun",
        "name": "项目预算超支",
        "dependency": "项目管理系统联动",
    },
)


class FinanceTransactionUpdate(BaseModel):
    transacted_at: datetime | None = None
    counterparty: str | None = Field(default=None, max_length=240)
    summary: str | None = Field(default=None, max_length=2000)
    category: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=1000)
    pm_project_id: str | None = Field(default=None, max_length=36)


class InternalTransferReview(BaseModel):
    decision: Literal["confirm", "reject", "reset"]
    target_entity_id: str | None = Field(default=None, max_length=36)
    note: str | None = Field(default=None, max_length=500)


class CashEntryCreate(BaseModel):
    entity_id: str | None = Field(default=None, max_length=36)
    company_name: str = Field(min_length=1, max_length=240)
    cash_account: str = Field(default="公司现金", min_length=1, max_length=120)
    transaction_date: date
    direction: str = Field(pattern="^(opening|income|expense)$")
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    category: str = Field(default="其他", min_length=1, max_length=80)
    note: str = Field(min_length=1, max_length=1000)
    pm_project_id: str | None = Field(default=None, max_length=36)


def _finance_view_allowed(user: User) -> bool:
    ceiling = CONFIDENTIALITY_RANK.get(user.confidentiality_ceiling, 0)
    return bool(
        user.active
        and (
            (user.organization_role == "finance" and ceiling >= 4)
            or (user.organization_role == "management" and ceiling >= 5)
        )
    )


def _finance_edit_allowed(user: User) -> bool:
    return bool(
        user.active
        and user.organization_role == "finance"
        and CONFIDENTIALITY_RANK.get(user.confidentiality_ceiling, 0) >= 4
    )


def _cash_edit_allowed(user: User) -> bool:
    return _finance_edit_allowed(user) or bool(
        user.active
        and user.organization_role == "management"
        and user.confidentiality_ceiling == "L5"
        and user.username.casefold() in EXECUTIVE_USERNAMES
    )


def _require_finance_view(user: User) -> None:
    if not _finance_view_allowed(user):
        raise HTTPException(status_code=403, detail="无权访问财务分析系统")


def _require_finance_edit(user: User) -> None:
    if not _finance_edit_allowed(user):
        raise HTTPException(status_code=403, detail="仅财务角色可以维护银行流水")


def _safe_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip(" .")
    return (cleaned[:120] or fallback)


def _mask_account(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    if len(compact) <= 8:
        return "****" + compact[-4:]
    return compact[:4] + "****" + compact[-4:]


def _entity(db: Session, name: str, user: User) -> BusinessEntity:
    normalized = name.strip()
    entity = db.scalar(select(BusinessEntity).where(BusinessEntity.name == normalized))
    if entity is None:
        entity = BusinessEntity(name=normalized, created_by_user_id=user.id)
        db.add(entity)
        db.flush()
    return entity


def _entity_by_id(db: Session, entity_id: str) -> BusinessEntity:
    entity = db.get(BusinessEntity, entity_id)
    if entity is None or not entity.active or entity.name not in FINANCE_ENTITY_NAMES:
        raise HTTPException(status_code=422, detail="财务公司主体不存在或未启用")
    return entity


def _account(
    db: Session,
    entity: BusinessEntity,
    bank_name: str,
    account_name: str,
    account_number: str,
) -> FinancialAccount:
    normalized = re.sub(r"\s+", "", account_number)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()
    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.entity_id == entity.id,
            FinancialAccount.bank_name == bank_name.strip(),
            FinancialAccount.account_number_hash == digest,
        )
    )
    if account is None:
        account = FinancialAccount(
            entity_id=entity.id,
            bank_name=bank_name.strip(),
            account_name=account_name.strip() or None,
            account_number_masked=_mask_account(normalized),
            account_number_hash=digest,
        )
        db.add(account)
        db.flush()
    return account


def _normalize_header(value: object) -> str:
    return re.sub(r"[\s\n\r（）()人民币RMB/CNY：:]", "", str(value or "")).casefold()


HEADER_ALIASES = {
    "date": {"交易日期", "交易时间", "记账日期", "入账日期", "交易日", "日期", "tradedate", "transactiondate"},
    "time": {"交易时刻", "交易时间点", "时间", "tradetime", "transactiontime"},
    "income": {"贷方发生额", "收入金额", "收入", "转入金额", "收方金额", "creditamount", "credit"},
    "expense": {"借方发生额", "支出金额", "支出", "转出金额", "付方金额", "debitamount", "debit"},
    "amount": {"交易金额", "发生额", "金额", "transactionamount", "amount"},
    "direction": {"收付标志", "借贷标志", "交易方向", "资金方向", "收入支出", "direction"},
    "balance": {"交易后余额", "账户余额", "余额", "balance", "availablebalance"},
    "counterparty": {"对手方", "对方户名", "对方名称", "对手名称", "counterparty", "counterpartyname"},
    "counterparty_fallback": {"收款人", "付款人"},
    "counterparty_account": {"对手方账号", "对方账号", "对方账户", "counterpartyaccount"},
    "counterparty_account_fallback": {"收款账号", "付款账号"},
    "purpose": {"用途", "交易用途", "purpose"},
    "remark": {"备注", "附言", "remark"},
    "summary": {"摘要", "交易摘要", "summary"},
    "serial": {"流水号", "交易流水号", "银行流水号", "凭证号", "交易序号", "serial", "transactionid"},
}


def _field_for_header(value: object) -> str | None:
    normalized = _normalize_header(value)
    for field, aliases in HEADER_ALIASES.items():
        if normalized in {_normalize_header(item) for item in aliases}:
            return field
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None or str(value).strip() in {"", "-", "--"}:
        return None
    text = str(value).strip().replace(",", "").replace("￥", "").replace("¥", "")
    text = re.sub(r"\s*(元|CNY|RMB)\s*$", "", text, flags=re.IGNORECASE)
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        result = Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return -result if negative else result


def _datetime(value: object, time_value: object = None) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time.min)
    else:
        text = str(value or "").strip()
        result = None
        for pattern in (
            "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d",
        ):
            try:
                result = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
        if result is None:
            return None
    if time_value and result.time() == time.min:
        time_text = str(time_value).strip()
        for pattern in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(time_text, pattern).time()
                result = datetime.combine(result.date(), parsed_time)
                break
            except ValueError:
                continue
    if result.tzinfo is None:
        result = result.replace(tzinfo=SHANGHAI_ZONE)
    return result.astimezone(timezone.utc)


def _business_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(SHANGHAI_ZONE).date()


def _transaction_order_key(item: BankTransaction) -> tuple:
    """Sort PostgreSQL-aware and SQLite-naive timestamps consistently."""

    value = item.transacted_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value, item.bank_serial or "", item.id


def _normalise_counterparty(value: str | None) -> str:
    """Return a comparison key without changing the displayed bank value."""
    text = unicodedata.normalize("NFKC", (value or "")).casefold().strip()
    return "".join(character for character in text if character.isalnum())


def _internal_entity_aliases() -> set[str]:
    # Do not infer an internal transfer from its bank summary: Beijing Bank
    # uses “本系统转账” as a transfer method even for genuine outside parties.
    # Only an exact normalised match to one of the three configured entities
    # (legal name or display name) is safe to exclude.
    aliases: set[str] = set()
    for definition in FINANCE_ENTITY_DEFINITIONS:
        for field in ("name", "display_name"):
            normalised = _normalise_counterparty(str(definition[field]))
            if normalised:
                aliases.add(normalised)
    return aliases


def _internal_alias_targets() -> dict[str, str]:
    """Map deterministic group aliases to their canonical legal entity name.

    Only full configured names and approved display names are automatic.  A
    substring or a similar-looking name is deliberately left for finance to
    review; false exclusion is more harmful than a missed internal transfer.
    """
    targets: dict[str, str] = {}
    for definition in FINANCE_ENTITY_DEFINITIONS:
        for field in ("name", "display_name"):
            normalised = _normalise_counterparty(str(definition[field]))
            if normalised:
                targets[normalised] = str(definition["name"])
    return targets


def _hash_account_number(value: str | None) -> str | None:
    normalized = re.sub(r"\s+", "", value or "")
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()


def _exact_internal_transfer_match(
    db: Session,
    item: BankTransaction,
) -> tuple[str | None, str | None, str | None]:
    """Return target entity id, source and canonical name for an exact match."""
    if item.counterparty_account_hash:
        target_account = db.scalar(
            select(FinancialAccount).where(
                FinancialAccount.account_number_hash == item.counterparty_account_hash
            )
        )
        if target_account is not None:
            target = db.get(BusinessEntity, target_account.entity_id)
            if target is not None and target.name in FINANCE_ENTITY_NAMES:
                source = (
                    "exact_same_entity_account"
                    if target.id == item.entity_id
                    else "exact_cross_entity_account"
                )
                return target.id, source, target.name

    counterparty_key = _normalise_counterparty(item.counterparty)
    canonical_name = _internal_alias_targets().get(counterparty_key)
    if canonical_name:
        target = db.scalar(
            select(BusinessEntity).where(BusinessEntity.name == canonical_name)
        )
        if target is None:
            # The configured name is exact but there is no canonical entity to
            # attach yet; surface it as a candidate instead of auto-excluding.
            return None, None, None
        source = (
            "exact_same_entity_alias"
            if target.id == item.entity_id
            else "exact_cross_entity_alias"
        )
        return target.id, source, canonical_name
    return None, None, None


def _internal_transfer_candidate(
    db: Session,
    item: BankTransaction,
) -> tuple[bool, str | None, str | None]:
    """Find conservative, review-only candidates without classifying them."""
    if item.internal_transfer_status != "unreviewed":
        return False, None, None
    normalised = _normalise_counterparty(item.counterparty)
    if normalised:
        for alias, canonical_name in _internal_alias_targets().items():
            # Require a meaningful common full substring.  This catches a
            # legal-name suffix variation while avoiding short-name guesses.
            if min(len(normalised), len(alias)) >= 4 and (
                normalised in alias or alias in normalised
            ):
                return True, "similar_group_entity_name", canonical_name
    if item.counterparty_account_masked:
        account = db.scalar(
            select(FinancialAccount).where(
                FinancialAccount.account_number_masked
                == item.counterparty_account_masked
            )
        )
        if account is not None:
            entity = db.get(BusinessEntity, account.entity_id)
            if entity is not None and entity.name in FINANCE_ENTITY_NAMES:
                return True, "masked_group_account_match", entity.name
    return False, None, None


def _refresh_auto_internal_transfers(
    db: Session,
    transactions: list[BankTransaction],
) -> int:
    """Idempotently classify exact matches, preserving every manual decision."""
    changed = 0
    for item in transactions:
        if item.internal_transfer_status in {"manual_confirmed", "not_internal"}:
            continue
        target_id, source, _target_name = _exact_internal_transfer_match(db, item)
        next_status = "auto_confirmed" if source else "unreviewed"
        if (
            item.internal_transfer_status != next_status
            or item.internal_transfer_source != source
            or item.internal_transfer_counterparty_entity_id != target_id
        ):
            item.internal_transfer_status = next_status
            item.internal_transfer_source = source
            item.internal_transfer_counterparty_entity_id = target_id
            item.internal_transfer_reviewed_by_user_id = None
            item.internal_transfer_reviewed_at = None
            changed += 1
    return changed


def _is_internal_transfer(item: BankTransaction) -> bool:
    return item.internal_transfer_status in {"auto_confirmed", "manual_confirmed"}


def _internal_transfer_payload(db: Session, item: BankTransaction) -> dict:
    is_candidate, candidate_reason, candidate_target_name = (
        _internal_transfer_candidate(db, item)
    )
    target = (
        db.get(BusinessEntity, item.internal_transfer_counterparty_entity_id)
        if item.internal_transfer_counterparty_entity_id
        else None
    )
    candidate_target = (
        db.scalar(
            select(BusinessEntity).where(
                BusinessEntity.name == candidate_target_name
            )
        )
        if candidate_target_name
        else None
    )
    source_entity = db.get(BusinessEntity, item.entity_id)
    amount = item.income if item.income > 0 else item.expense
    display_status = (
        "confirmed"
        if _is_internal_transfer(item)
        else "rejected"
        if item.internal_transfer_status == "not_internal"
        else "candidate"
        if is_candidate
        else "unreviewed"
    )
    return {
        "id": item.id,
        "transaction_id": item.id,
        "entity_id": item.entity_id,
        "source_entity_id": item.entity_id,
        "company": source_entity.name if source_entity else "",
        "transacted_at": item.transacted_at,
        "income": item.income,
        "expense": item.expense,
        "counterparty": item.counterparty,
        "counterparty_account": item.counterparty_account_masked,
        "summary": item.summary,
        "category": item.category,
        "status": item.status,
        "internal_transfer_status": item.internal_transfer_status,
        "internal_transfer_source": item.internal_transfer_source,
        "target_entity_id": (
            item.internal_transfer_counterparty_entity_id
            or (candidate_target.id if candidate_target else None)
        ),
        "target_entity_name": target.name if target else candidate_target_name,
        "is_candidate": is_candidate,
        "candidate_reason": candidate_reason,
        "reviewed_by_user_id": item.internal_transfer_reviewed_by_user_id,
        "reviewed_at": item.internal_transfer_reviewed_at,
        # Stable UI aliases; the evidence fields above remain available.
        "transaction_date": _business_date(item.transacted_at),
        "source_entity_name": source_entity.name if source_entity else "",
        "amount": amount,
        "direction": "income" if item.income > 0 else "expense",
        "decision_status": display_status,
        "review_status": display_status,
        "reason": item.internal_transfer_source or candidate_reason,
    }


def _decimal_median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _top_counterparties(
    transactions: list[BankTransaction],
) -> tuple[list[dict], list[dict]]:
    """Aggregate income and expense by displayed counterparty.

    The function intentionally receives an already scoped transaction list so
    callers cannot accidentally mix companies or include pending imports.
    """
    income_by_counterparty: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"amount": Decimal("0"), "transaction_count": 0}
    )
    expense_by_counterparty: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"amount": Decimal("0"), "transaction_count": 0}
    )
    for item in transactions:
        counterparty = (item.counterparty or "").strip() or "未识别对方"
        if item.income > 0:
            income_by_counterparty[counterparty]["amount"] += item.income
            income_by_counterparty[counterparty]["transaction_count"] += 1
        if item.expense > 0:
            expense_by_counterparty[counterparty]["amount"] += item.expense
            expense_by_counterparty[counterparty]["transaction_count"] += 1

    def ranked(values: dict[str, dict[str, Decimal | int]]) -> list[dict]:
        return [
            {
                "name": name,
                "amount": summary["amount"],
                "transaction_count": summary["transaction_count"],
            }
            for name, summary in sorted(
                values.items(),
                key=lambda row: (Decimal(str(row[1]["amount"])), row[0]),
                reverse=True,
            )[:10]
        ]

    return ranked(income_by_counterparty), ranked(expense_by_counterparty)


def _counterparty_concentration(
    transactions: list[BankTransaction],
    direction: Literal["income", "expense"],
    limit: int = 3,
) -> dict:
    """Return a normalised Top-N share for one direction."""
    buckets: dict[str, dict[str, Decimal | int | str]] = {}
    total = Decimal("0")
    for item in transactions:
        amount = item.income if direction == "income" else item.expense
        if amount <= 0:
            continue
        display_name = (item.counterparty or "").strip() or "未识别对方"
        key = _normalise_counterparty(display_name) or "__unknown__"
        bucket = buckets.setdefault(
            key,
            {"name": display_name, "amount": Decimal("0"), "transaction_count": 0},
        )
        bucket["amount"] = Decimal(str(bucket["amount"])) + amount
        bucket["transaction_count"] = int(bucket["transaction_count"]) + 1
        total += amount
    ordered = sorted(
        buckets.values(),
        key=lambda row: (Decimal(str(row["amount"])), str(row["name"])),
        reverse=True,
    )[:limit]
    amount = sum((Decimal(str(row["amount"])) for row in ordered), Decimal("0"))
    parties = [
        {
            "name": row["name"],
            "amount": row["amount"],
            "transaction_count": row["transaction_count"],
            "ratio": (
                (Decimal(str(row["amount"])) / total).quantize(Decimal("0.0001"))
                if total > 0
                else Decimal("0")
            ),
        }
        for row in ordered
    ]
    return {
        "amount": amount,
        "total": total,
        "ratio": (
            (amount / total).quantize(Decimal("0.0001"))
            if total > 0
            else Decimal("0")
        ),
        "parties": parties,
    }


def _daily_aggregate_balances(
    transactions: list[BankTransaction],
    period_start: date,
    period_end: date,
) -> tuple[list[dict], int]:
    """Carry each account's last reported balance over a calendar-date range."""
    rows = sorted(
        (item for item in transactions if item.balance is not None),
        key=_transaction_order_key,
    )
    account_ids = {item.account_id for item in rows}
    balances: dict[str, Decimal] = {}
    by_date: dict[date, list[BankTransaction]] = defaultdict(list)
    for item in rows:
        business_day = _business_date(item.transacted_at)
        if business_day < period_start:
            balances[item.account_id] = Decimal(item.balance)
        elif business_day <= period_end:
            by_date[business_day].append(item)

    daily: list[dict] = []
    current_day = period_start
    while current_day <= period_end:
        for item in by_date.get(current_day, []):
            balances[item.account_id] = Decimal(item.balance)
        if balances:
            daily.append({
                "date": current_day,
                "balance": sum(balances.values(), Decimal("0")),
                "covered_account_count": len(balances),
            })
        current_day += timedelta(days=1)
    return daily, len(account_ids)


def _finance_health(
    *,
    transactions: list[BankTransaction],
    operating_transactions: list[BankTransaction],
    period_start: date,
    period_end: date,
    include_internal_transfers: bool,
) -> dict:
    """Build deterministic, confirmed-only finance-health indicators."""
    in_period = [
        item for item in operating_transactions
        if period_start <= _business_date(item.transacted_at) <= period_end
    ]
    raw_in_period = [
        item for item in transactions
        if period_start <= _business_date(item.transacted_at) <= period_end
    ]
    data_as_of = max(
        (_business_date(item.transacted_at) for item in transactions),
        default=None,
    )

    daily_balances, account_count = _daily_aggregate_balances(
        transactions, period_start, period_end
    )
    fully_covered_days = [
        row for row in daily_balances
        if row["covered_account_count"] == account_count
    ]
    total_period_days = (period_end - period_start).days + 1
    coverage_start = (
        fully_covered_days[0]["date"] if fully_covered_days else None
    )
    minimum_row = min(
        fully_covered_days,
        key=lambda row: (Decimal(str(row["balance"])), row["date"]),
        default=None,
    )

    daily_net: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in in_period:
        daily_net[_business_date(item.transacted_at)] += item.income - item.expense
    worst_day = min(daily_net.items(), key=lambda row: (row[1], row[0]), default=None)
    if worst_day is None or worst_day[1] >= 0:
        maximum_daily_net_outflow = {
            "amount": Decimal("0"), "date": None, "net": Decimal("0")
        }
    else:
        maximum_daily_net_outflow = {
            "amount": -worst_day[1], "date": worst_day[0], "net": worst_day[1]
        }

    # Four complete ISO weeks (Monday-Sunday) ending on or before period_end.
    last_sunday = period_end - timedelta(days=(period_end.weekday() + 1) % 7)
    four_week_start = last_sunday - timedelta(days=27)
    natural_weeks = []
    for index in range(4):
        week_start = four_week_start + timedelta(days=index * 7)
        week_end = week_start + timedelta(days=6)
        week_rows = [
            item for item in operating_transactions
            if week_start <= _business_date(item.transacted_at) <= week_end
        ]
        week_income = sum((item.income for item in week_rows), Decimal("0"))
        week_expense = sum((item.expense for item in week_rows), Decimal("0"))
        natural_weeks.append({
            "period_start": week_start,
            "period_end": week_end,
            "income": week_income,
            "expense": week_expense,
            "net": week_income - week_expense,
        })
    average_weekly_net = (
        sum((Decimal(str(row["net"])) for row in natural_weeks), Decimal("0"))
        / Decimal("4")
    ).quantize(Decimal("0.01"))

    unclassified_names = {"", "待确认", "未分类", "待分类"}
    unclassified_rows = [
        item for item in in_period
        if (item.category or "").strip() in unclassified_names
    ]
    unclassified_income = sum(
        (item.income for item in unclassified_rows), Decimal("0")
    )
    unclassified_expense = sum(
        (item.expense for item in unclassified_rows), Decimal("0")
    )
    internal_rows = [item for item in raw_in_period if _is_internal_transfer(item)]
    internal_income = sum((item.income for item in internal_rows), Decimal("0"))
    internal_expense = sum((item.expense for item in internal_rows), Decimal("0"))

    return {
        "period_start": period_start,
        "period_end": period_end,
        "scope": (
            "including_internal_transfers"
            if include_internal_transfers
            else "excluding_internal_transfers"
        ),
        "confirmed_only": True,
        "data_as_of": data_as_of,
        "freshness_days": (
            max((date.today() - data_as_of).days, 0) if data_as_of else None
        ),
        "minimum_balance": {
            "amount": Decimal(str(minimum_row["balance"])) if minimum_row else None,
            "date": minimum_row["date"] if minimum_row else None,
            "account_count": account_count,
            "covered_account_count": (
                minimum_row["covered_account_count"] if minimum_row else 0
            ),
            "coverage_start": coverage_start,
            "covered_days": len(fully_covered_days),
            "total_days": total_period_days,
            "coverage_complete": (
                account_count > 0
                and len(fully_covered_days) == total_period_days
            ),
        },
        "maximum_daily_net_outflow": maximum_daily_net_outflow,
        "average_weekly_net_inflow_4w": {
            "amount": average_weekly_net,
            "period_start": four_week_start,
            "period_end": last_sunday,
            "weeks": natural_weeks,
        },
        "top3_income_concentration": _counterparty_concentration(
            in_period, "income"
        ),
        "top3_expense_concentration": _counterparty_concentration(
            in_period, "expense"
        ),
        "unclassified": {
            "amount": unclassified_income + unclassified_expense,
            "count": len(unclassified_rows),
            "income": unclassified_income,
            "expense": unclassified_expense,
        },
        "internal_transfers": {
            "gross_amount": internal_income + internal_expense,
            "count": len(internal_rows),
            "income": internal_income,
            "expense": internal_expense,
            "auto_count": sum(
                item.internal_transfer_status == "auto_confirmed"
                for item in internal_rows
            ),
            "manual_count": sum(
                item.internal_transfer_status == "manual_confirmed"
                for item in internal_rows
            ),
        },
    }


def _transaction_alerts(
    transactions: list[BankTransaction],
    period_start: date,
    period_end: date,
) -> list[dict]:
    """Run the v2 transaction rules for one self-contained reporting window.

    `transactions` must contain confirmed rows for one company.  First-seen
    baselines stop at the start of the requested window; within the window the
    first occurrence is alerted once.  Behaviour history starts with earlier
    rows and expands chronologically as the period is evaluated.
    """
    in_period = [
        item
        for item in transactions
        if period_start <= _business_date(item.transacted_at) <= period_end
    ]

    suspected_duplicate_groups: dict[tuple, list[str]] = defaultdict(list)
    for item in transactions:
        counterparty = _normalise_counterparty(item.counterparty)
        if not counterparty or (item.income <= 0 and item.expense <= 0):
            continue
        suspected_duplicate_groups[
            (
                item.entity_id,
                item.account_id,
                _business_date(item.transacted_at),
                counterparty,
                item.income,
                item.expense,
            )
        ].append(item.id)
    suspected_duplicate_ids = {
        transaction_id
        for group in suspected_duplicate_groups.values()
        if len(group) > 1
        for transaction_id in group
    }

    transactions_by_statement: dict[tuple[str, str], list[BankTransaction]] = defaultdict(list)
    for item in transactions:
        transactions_by_statement[(item.account_id, item.batch_id)].append(item)
    broken_balance_ids: set[str] = set()
    for statement_rows in transactions_by_statement.values():
        ordered = sorted(
            statement_rows,
            key=_transaction_order_key,
        )
        previous: BankTransaction | None = None
        for item in ordered:
            if (
                previous is not None
                and previous.balance is not None
                and item.balance is not None
            ):
                expected_balance = previous.balance + item.income - item.expense
                if abs(item.balance - expected_balance) > Decimal("0.01"):
                    broken_balance_ids.add(item.id)
            previous = item

    internal_aliases = _internal_entity_aliases()
    known_before_period = {
        (item.entity_id, _normalise_counterparty(item.counterparty))
        for item in transactions
        if (
            _business_date(item.transacted_at) < period_start
            and _normalise_counterparty(item.counterparty)
        )
    }
    seen_in_period: set[tuple[str, str]] = set()

    amount_history: dict[tuple[str, str, str], list[Decimal]] = defaultdict(list)
    for historical in sorted(
        (
            item
            for item in transactions
            if _business_date(item.transacted_at) < period_start
        ),
        key=_transaction_order_key,
    ):
        normalised = _normalise_counterparty(historical.counterparty)
        if not normalised or normalised in internal_aliases:
            continue
        if historical.income > 0:
            amount_history[(historical.entity_id, normalised, "income")].append(
                historical.income
            )
        if historical.expense > 0:
            amount_history[(historical.entity_id, normalised, "expense")].append(
                historical.expense
            )

    severity_rank = {"low": 1, "medium": 2, "high": 3}
    alert_type_rank = {
        "data_integrity": 0,
        "suspected_duplicate": 1,
        "behaviour_change": 2,
        "new_counterparty": 3,
        "data_quality": 4,
    }
    anomaly_rows: list[dict] = []
    for item in sorted(
        in_period,
        key=_transaction_order_key,
    ):
        rules: list[tuple[str, str, str, str]] = []

        def add_rule(code: str, reason: str, severity: str, alert_type: str) -> None:
            rules.append((code, reason, severity, alert_type))

        if item.income < 0 or item.expense < 0:
            add_rule(
                "negative_amount", "收入或支出出现负数", "high", "data_integrity"
            )
        if item.income > 0 and item.expense > 0:
            add_rule(
                "dual_direction_amount",
                "同一笔流水同时存在收入和支出",
                "high",
                "data_integrity",
            )
        elif item.income == 0 and item.expense == 0:
            add_rule(
                "zero_amount", "收入和支出金额均为零", "high", "data_integrity"
            )
        if item.id in broken_balance_ids:
            add_rule(
                "balance_discontinuity",
                "余额不连续：与上一笔收支计算不符",
                "high",
                "data_integrity",
            )
        if item.id in suspected_duplicate_ids:
            add_rule(
                "suspected_duplicate",
                "疑似重复：同日、同对方、同金额",
                "medium",
                "suspected_duplicate",
            )

        counterparty_key = _normalise_counterparty(item.counterparty)
        counterparty_identity = (item.entity_id, counterparty_key)
        is_internal = bool(counterparty_key and counterparty_key in internal_aliases)
        if counterparty_key and not is_internal:
            if (
                counterparty_identity not in known_before_period
                and counterparty_identity not in seen_in_period
            ):
                if item.expense > 0:
                    add_rule(
                        "first_seen_expense_counterparty",
                        "首次出现的收款方",
                        "medium",
                        "new_counterparty",
                    )
                elif item.income > 0:
                    add_rule(
                        "first_seen_income_counterparty",
                        "首次出现的付款方",
                        "low",
                        "new_counterparty",
                    )
            seen_in_period.add(counterparty_identity)

            for direction, current_amount in (
                ("expense", item.expense),
                ("income", item.income),
            ):
                history_key = (item.entity_id, counterparty_key, direction)
                earlier_amounts = amount_history[history_key]
                if (
                    current_amount > 0
                    and len(earlier_amounts) >= BEHAVIOUR_SPIKE_MIN_HISTORY
                ):
                    baseline = _decimal_median(earlier_amounts)
                    if (
                        current_amount > baseline * BEHAVIOUR_SPIKE_MULTIPLIER
                        and current_amount - baseline > BEHAVIOUR_SPIKE_MIN_DIFFERENCE
                    ):
                        direction_name = "支出" if direction == "expense" else "收入"
                        add_rule(
                            f"{direction}_amount_spike",
                            (
                                f"历史{direction_name}金额突增：本笔 {current_amount:,.2f} 元，"
                                f"此前 {len(earlier_amounts)} 笔中位数为 {baseline:,.2f} 元"
                            ),
                            "medium",
                            "behaviour_change",
                        )
                if current_amount > 0:
                    earlier_amounts.append(current_amount)

        if not (item.counterparty or "").strip():
            add_rule(
                "missing_counterparty", "对方单位缺失", "medium", "data_quality"
            )
        if not (item.summary or "").strip():
            add_rule("missing_summary", "摘要缺失", "low", "data_quality")

        if rules:
            severity = max(rules, key=lambda rule: severity_rank[rule[2]])[2]
            alert_type = min(rules, key=lambda rule: alert_type_rank[rule[3]])[3]
            amount = max(item.income, item.expense)
            anomaly_rows.append(
                {
                    "id": item.id,
                    "batch_id": item.batch_id,
                    "transaction_date": _business_date(item.transacted_at),
                    "counterparty": (item.counterparty or "").strip()
                    or "未识别对方",
                    "summary": (item.summary or "").strip() or "无摘要",
                    "income": item.income,
                    "expense": item.expense,
                    "amount": amount,
                    "status": item.status,
                    "severity": severity,
                    "alert_type": alert_type,
                    "rule_codes": [rule[0] for rule in rules],
                    "reasons": [rule[1] for rule in rules],
                }
            )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    anomaly_rows.sort(
        key=lambda item: (
            severity_order[item["severity"]],
            -Decimal(str(item["amount"])),
            str(item["transaction_date"]),
        )
    )
    return anomaly_rows


def _combined_summary(*values: object) -> str | None:
    parts: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text or text in {"-", "--"} or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return " · ".join(parts) or None


def _csv_rows(payload: bytes) -> list[list[object]]:
    decoded = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            decoded = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValueError("CSV编码无法识别，请另存为UTF-8或Excel格式")
    return [list(row) for row in csv.reader(io.StringIO(decoded))]


def _xlsx_rows(payload: bytes) -> list[list[object]]:
    workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    try:
        if not workbook.worksheets:
            return []
        return [list(row) for row in workbook.worksheets[0].iter_rows(values_only=True)]
    finally:
        workbook.close()


def parse_statement(payload: bytes, suffix: str) -> tuple[list[dict], int]:
    rows = _xlsx_rows(payload) if suffix == ".xlsx" else _csv_rows(payload)
    header_index = None
    columns: dict[str, int] = {}
    for index, row in enumerate(rows[:30]):
        candidate = {
            field: column_index
            for column_index, value in enumerate(row)
            if (field := _field_for_header(value))
        }
        if "date" in candidate and (
            {"income", "expense"}.intersection(candidate)
            or "amount" in candidate
        ):
            header_index = index
            columns = candidate
            break
    if header_index is None:
        raise ValueError("未找到交易日期和收支金额表头")

    parsed: list[dict] = []
    errors = 0
    for row in rows[header_index + 1:]:
        if not any(value not in (None, "") for value in row):
            continue

        def value(field: str):
            column = columns.get(field)
            return row[column] if column is not None and column < len(row) else None

        transacted_at = _datetime(value("date"), value("time"))
        income = _decimal(value("income")) or Decimal("0")
        expense = _decimal(value("expense")) or Decimal("0")
        if not income and not expense:
            amount = _decimal(value("amount"))
            direction = str(value("direction") or "").strip().casefold()
            if amount is not None:
                if any(mark in direction for mark in ("收", "贷", "入", "credit", "c")):
                    income = abs(amount)
                elif any(mark in direction for mark in ("付", "借", "支", "出", "debit", "d")):
                    expense = abs(amount)
                elif amount < 0:
                    expense = abs(amount)
                elif amount > 0:
                    income = amount
        if transacted_at is None or (income == 0 and expense == 0):
            errors += 1
            continue
        parsed.append({
            "transacted_at": transacted_at,
            "income": income,
            "expense": expense,
            "balance": _decimal(value("balance")),
            "counterparty": str(
                value("counterparty") or value("counterparty_fallback") or ""
            ).strip() or None,
            "counterparty_account": str(
                value("counterparty_account") or value("counterparty_account_fallback") or ""
            ).strip() or None,
            "summary": _combined_summary(
                value("purpose"), value("remark"), value("summary")
            ),
            "serial": str(value("serial") or "").strip() or None,
        })
    if not parsed:
        raise ValueError("没有解析到有效流水，请检查银行导出格式")
    return parsed, errors


def _transaction_fingerprint(account_id: str, row: dict) -> str:
    if row.get("serial"):
        return hashlib.sha256(
            f"{account_id}|serial|{row['serial']}".encode("utf-8")
        ).hexdigest().upper()
    values = [
        account_id,
        row["transacted_at"].isoformat(),
        str(row["income"]),
        str(row["expense"]),
        str(row["balance"] or ""),
        row["counterparty"] or "",
        row["serial"] or "",
        row["summary"] or "",
    ]
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest().upper()


def _batch_payload(batch: BankStatementBatch, db: Session) -> dict:
    entity = db.get(BusinessEntity, batch.entity_id)
    account = db.get(FinancialAccount, batch.account_id)
    uploader = db.get(User, batch.uploaded_by_user_id)
    return {
        "id": batch.id,
        "entity_id": batch.entity_id,
        "company": entity.name if entity else "",
        "bank_name": account.bank_name if account else "",
        "account": account.account_number_masked if account else "",
        "filename": batch.original_filename,
        "period_start": batch.period_start,
        "period_end": batch.period_end,
        "status": batch.status,
        "row_count": batch.row_count,
        "duplicate_count": batch.duplicate_count,
        "error_count": batch.error_count,
        "uploader": uploader.display_name if uploader else "",
        "created_at": batch.created_at,
    }


def _migrate_legacy_finance_data(
    db: Session,
    headquarters: BusinessEntity,
) -> bool:
    """Move legacy headquarters references to the canonical legal entity."""
    changed = False

    # Off-book cash existed before the three-company ledger was introduced.
    # Under the current rule every cash entry belongs to Jingao headquarters.
    legacy_cash_entries = db.scalars(
        select(CashEntry).where(CashEntry.entity_id != headquarters.id)
    ).all()
    for entry in legacy_cash_entries:
        entry.entity_id = headquarters.id
        changed = True

    legacy_entities = db.scalars(
        select(BusinessEntity).where(
            BusinessEntity.name.in_(LEGACY_HEADQUARTERS_ENTITY_NAMES)
        )
    ).all()
    for legacy_entity in legacy_entities:
        if legacy_entity.id == headquarters.id:
            continue
        legacy_accounts = db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.entity_id == legacy_entity.id
            )
        ).all()
        for legacy_account in legacy_accounts:
            target_account = db.scalar(
                select(FinancialAccount).where(
                    FinancialAccount.entity_id == headquarters.id,
                    FinancialAccount.bank_name == legacy_account.bank_name,
                    FinancialAccount.account_number_hash
                    == legacy_account.account_number_hash,
                )
            )
            legacy_batches = db.scalars(
                select(BankStatementBatch).where(
                    BankStatementBatch.account_id == legacy_account.id
                )
            ).all()
            if target_account is None:
                legacy_account.entity_id = headquarters.id
                for batch in legacy_batches:
                    batch.entity_id = headquarters.id
                    transactions = db.scalars(
                        select(BankTransaction).where(
                            BankTransaction.batch_id == batch.id
                        )
                    ).all()
                    for transaction in transactions:
                        transaction.entity_id = headquarters.id
                changed = True
                continue

            # If the same bank account was already registered under the
            # canonical entity, merge batches and discard only exact
            # transaction fingerprints.  This prevents uniqueness conflicts
            # without losing distinct historical rows.
            for legacy_batch in legacy_batches:
                target_batch = db.scalar(
                    select(BankStatementBatch).where(
                        BankStatementBatch.account_id == target_account.id,
                        BankStatementBatch.file_hash == legacy_batch.file_hash,
                    )
                )
                transactions = db.scalars(
                    select(BankTransaction).where(
                        BankTransaction.batch_id == legacy_batch.id
                    )
                ).all()
                for transaction in transactions:
                    duplicate = db.scalar(
                        select(BankTransaction).where(
                            BankTransaction.account_id == target_account.id,
                            BankTransaction.fingerprint == transaction.fingerprint,
                        )
                    )
                    if duplicate is not None:
                        db.delete(transaction)
                        continue
                    transaction.entity_id = headquarters.id
                    transaction.account_id = target_account.id
                    if target_batch is not None:
                        transaction.batch_id = target_batch.id
                db.flush()
                if target_batch is not None:
                    db.delete(legacy_batch)
                else:
                    legacy_batch.entity_id = headquarters.id
                    legacy_batch.account_id = target_account.id
            db.flush()
            db.delete(legacy_account)
            changed = True

        # Repair inconsistent historical rows whose entity was the alias even
        # though their account had already been moved to headquarters.
        alias_batches = db.scalars(
            select(BankStatementBatch).where(
                BankStatementBatch.entity_id == legacy_entity.id
            )
        ).all()
        for batch in alias_batches:
            batch.entity_id = headquarters.id
            changed = True
        alias_transactions = db.scalars(
            select(BankTransaction).where(
                BankTransaction.entity_id == legacy_entity.id
            )
        ).all()
        for transaction in alias_transactions:
            transaction.entity_id = headquarters.id
            changed = True

        linked_transfers = db.scalars(
            select(BankTransaction).where(
                BankTransaction.internal_transfer_counterparty_entity_id
                == legacy_entity.id
            )
        ).all()
        for transaction in linked_transfers:
            transaction.internal_transfer_counterparty_entity_id = headquarters.id
            changed = True

        legacy_projects = db.scalars(
            select(ManagedProject).where(
                (ManagedProject.entity_id == legacy_entity.id)
                | (ManagedProject.company_name == legacy_entity.name)
            )
        ).all()
        for project in legacy_projects:
            project.entity_id = headquarters.id
            project.company_name = headquarters.name
            changed = True

    return changed


def normalize_business_entity_registry(
    db: Session,
    *,
    created_by_user_id: str | None = None,
) -> list[dict]:
    """Create the three canonical entities and retire every legacy alias.

    Historic entity rows remain in the database for auditability, but only
    the three configured legal entities stay active.  Project and finance
    foreign keys use immutable IDs, so migrating the old Jingao alias does
    not break reviews, cashflow plans or audit references.
    """

    actor_id = created_by_user_id or db.scalar(
        select(User.id).where(User.role == "founder").limit(1)
    ) or db.scalar(select(User.id).limit(1))
    if not actor_id:
        raise RuntimeError("至少需要一个本地账号才能初始化公司主体")
    rows: list[dict] = []
    changed = False
    for definition in FINANCE_ENTITY_DEFINITIONS:
        entity = db.scalar(
            select(BusinessEntity).where(BusinessEntity.name == definition["name"])
        )
        if entity is None:
            entity = BusinessEntity(
                name=definition["name"],
                short_name=definition["display_name"],
                created_by_user_id=actor_id,
            )
            db.add(entity)
            db.flush()
            changed = True
        elif entity.short_name != definition["display_name"] or not entity.active:
            entity.short_name = definition["display_name"]
            entity.active = True
            changed = True
        rows.append({
            "id": entity.id,
            **definition,
            "show_cash": bool(definition["is_headquarters"]),
        })

    headquarters = db.scalar(
        select(BusinessEntity).where(
            BusinessEntity.name == HEADQUARTERS_ENTITY_NAME
        )
    )
    if headquarters is not None and _migrate_legacy_finance_data(db, headquarters):
        changed = True

    retired_ids: list[str] = []
    legacy_entities = db.scalars(
        select(BusinessEntity).where(
            BusinessEntity.name.not_in(FINANCE_ENTITY_NAMES),
            BusinessEntity.active.is_(True),
        )
    ).all()
    for entity in legacy_entities:
        entity.active = False
        retired_ids.append(entity.id)
        changed = True

    if changed:
        db.add(
            AuditLog(
                user_id=created_by_user_id,
                action="business_entity_registry_normalized_v1",
                details_json=json.dumps(
                    {
                        "canonical_entity_ids": [item["id"] for item in rows],
                        "retired_entity_ids": retired_ids,
                        "active_entity_count": 3,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
    return rows


@router.get("/entities")
def finance_entities(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_finance_view(user)
    return normalize_business_entity_registry(
        db,
        created_by_user_id=user.id,
    )


@router.post("/statements/upload")
async def upload_statement(
    file: UploadFile = File(...),
    entity_id: str = Form(default=""),
    company_name: str = Form(default=""),
    bank_name: str = Form(...),
    account_name: str = Form(default=""),
    account_number: str = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_finance_edit(user)
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_STATEMENTS:
        raise HTTPException(status_code=415, detail="银行流水首期仅支持XLSX或CSV")
    payload = await file.read(settings.inbox_max_file_bytes + 1)
    await file.close()
    if not payload:
        raise HTTPException(status_code=422, detail="不能上传空文件")
    if len(payload) > settings.inbox_max_file_bytes:
        raise HTTPException(status_code=413, detail="文件超过上传大小限制")
    try:
        rows, error_count = parse_statement(payload, suffix)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if entity_id:
        entity = _entity_by_id(db, entity_id)
    elif company_name in FINANCE_ENTITY_NAMES:
        entity = _entity(db, company_name, user)
    else:
        raise HTTPException(status_code=422, detail="请选择系统内已登记的公司主体")
    account = _account(db, entity, bank_name, account_name, account_number)
    file_hash = hashlib.sha256(payload).hexdigest().upper()
    existing = db.scalar(
        select(BankStatementBatch).where(
            BankStatementBatch.account_id == account.id,
            BankStatementBatch.file_hash == file_hash,
        )
    )
    if existing:
        return {**_batch_payload(existing, db), "duplicate_file": True}

    year = min(_business_date(row["transacted_at"]).year for row in rows)
    target = (
        settings.knowledge_root
        / "财务系统"
        / "银行流水"
        / _safe_part(entity.name, "未命名公司")
        / _safe_part(f"{account.bank_name}_{account.account_number_masked}", "银行账户")
        / str(year)
    )
    target.mkdir(parents=True, exist_ok=True)
    source = target / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{secrets.token_hex(3)}_{_safe_part(filename, '流水'+suffix)}"
    source.write_bytes(payload)
    batch = BankStatementBatch(
        entity_id=entity.id,
        account_id=account.id,
        original_filename=filename,
        source_path=str(source),
        file_hash=file_hash,
        period_start=min(_business_date(row["transacted_at"]) for row in rows),
        period_end=max(_business_date(row["transacted_at"]) for row in rows),
        error_count=error_count,
        uploaded_by_user_id=user.id,
    )
    db.add(batch)
    db.flush()
    duplicates = 0
    inserted = 0
    seen: set[str] = set()
    for row in rows:
        fingerprint = _transaction_fingerprint(account.id, row)
        if fingerprint in seen or db.scalar(
            select(BankTransaction.id).where(
                BankTransaction.account_id == account.id,
                BankTransaction.fingerprint == fingerprint,
            )
        ):
            duplicates += 1
            continue
        seen.add(fingerprint)
        db.add(BankTransaction(
            batch_id=batch.id,
            entity_id=entity.id,
            account_id=account.id,
            transacted_at=row["transacted_at"],
            income=row["income"],
            expense=row["expense"],
            balance=row["balance"],
            counterparty=row["counterparty"],
            counterparty_account_masked=(
                _mask_account(row["counterparty_account"])
                if row["counterparty_account"] else None
            ),
            counterparty_account_hash=_hash_account_number(
                row["counterparty_account"]
            ),
            summary=row["summary"],
            bank_serial=row["serial"],
            fingerprint=fingerprint,
        ))
        inserted += 1
    batch.row_count = inserted
    batch.duplicate_count = duplicates
    db.add(AuditLog(
        user_id=user.id,
        action="finance_statement_upload",
        details_json=json.dumps({
            "batch_id": batch.id,
            "company": entity.name,
            "bank": account.bank_name,
            "row_count": inserted,
            "duplicates": duplicates,
            "errors": error_count,
        }, ensure_ascii=False),
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        source.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="该流水已由其他操作导入")
    return {**_batch_payload(batch, db), "duplicate_file": False}


@router.get("/statements")
def list_statement_batches(
    limit: int = Query(default=50, ge=1, le=200),
    entity_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_finance_view(user)
    query = select(BankStatementBatch)
    if entity_id:
        _entity_by_id(db, entity_id)
        query = query.where(BankStatementBatch.entity_id == entity_id)
    rows = db.scalars(
        query.order_by(BankStatementBatch.created_at.desc()).limit(limit)
    ).all()
    return [_batch_payload(item, db) for item in rows]


@router.get("/statements/{batch_id}/transactions")
def statement_transactions(
    batch_id: str,
    entity_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_finance_view(user)
    batch = db.get(BankStatementBatch, batch_id)
    if batch is None or (entity_id and batch.entity_id != entity_id):
        raise HTTPException(status_code=404, detail="流水批次不存在")
    rows = db.scalars(
        select(BankTransaction)
        .where(BankTransaction.batch_id == batch_id)
        .order_by(BankTransaction.transacted_at)
    ).all()
    return [{
        "id": item.id,
        "transacted_at": item.transacted_at,
        "income": item.income,
        "expense": item.expense,
        "balance": item.balance,
        "counterparty": item.counterparty,
        "summary": item.summary,
        "category": item.category,
        "note": item.note,
        "pm_project_id": item.pm_project_id,
        "status": item.status,
        **{
            key: value
            for key, value in _internal_transfer_payload(db, item).items()
            if key in {
                "internal_transfer_status",
                "internal_transfer_source",
                "target_entity_id",
                "target_entity_name",
                "is_candidate",
                "candidate_reason",
                "reviewed_by_user_id",
                "reviewed_at",
            }
        },
    } for item in rows]


@router.get("/internal-transfers")
def internal_transfer_registry(
    entity_id: str | None = None,
    review_status: Literal[
        "all", "candidate", "confirmed", "rejected", "unreviewed"
    ] = "all",
    limit: int = Query(default=200, ge=1, le=500),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_finance_view(user)
    if entity_id:
        _entity_by_id(db, entity_id)
    query = select(BankTransaction).where(BankTransaction.status == "confirmed")
    if entity_id:
        query = query.where(BankTransaction.entity_id == entity_id)
    transactions = db.scalars(
        query.order_by(BankTransaction.transacted_at.desc())
    ).all()
    if _refresh_auto_internal_transfers(db, transactions):
        db.commit()

    matching_items = []
    for item in transactions:
        payload = _internal_transfer_payload(db, item)
        if review_status == "candidate" and not payload["is_candidate"]:
            continue
        if review_status == "confirmed" and not _is_internal_transfer(item):
            continue
        if review_status == "rejected" and item.internal_transfer_status != "not_internal":
            continue
        if review_status == "unreviewed" and item.internal_transfer_status != "unreviewed":
            continue
        if review_status == "all" and not (
            _is_internal_transfer(item)
            or item.internal_transfer_status == "not_internal"
            or payload["is_candidate"]
        ):
            continue
        matching_items.append(payload)

    confirmed_items = [item for item in matching_items if item["internal_transfer_status"] in {"auto_confirmed", "manual_confirmed"}]
    candidate_items = [item for item in matching_items if item["is_candidate"]]
    rejected_items = [
        item for item in matching_items
        if item["internal_transfer_status"] == "not_internal"
    ]
    confirmed_amount = sum(
        (Decimal(str(item["amount"])) for item in confirmed_items), Decimal("0")
    )
    candidate_amount = sum(
        (Decimal(str(item["amount"])) for item in candidate_items), Decimal("0")
    )
    items = matching_items[:limit]
    return {
        "items": items,
        "confirmed_count": len(confirmed_items),
        "candidate_count": len(candidate_items),
        "rejected_count": len(rejected_items),
        "confirmed_amount": confirmed_amount,
        "candidate_amount": candidate_amount,
        "summary": {
            "count": len(matching_items),
            "candidate_count": len(candidate_items),
            "confirmed_count": len(confirmed_items),
            "rejected_count": len(rejected_items),
            "gross_amount": confirmed_amount,
            "confirmed_amount": confirmed_amount,
            "candidate_amount": candidate_amount,
        },
        "confirmed_only": True,
    }


@router.patch("/internal-transfers/{transaction_id}")
def review_internal_transfer(
    transaction_id: str,
    payload: InternalTransferReview,
    entity_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Confirm, reject or reset a transfer classification.

    This is metadata governance, so it remains valid after the statement batch
    is confirmed.  Amounts and bank evidence are never edited here.
    """
    _require_finance_edit(user)
    item = db.get(BankTransaction, transaction_id)
    if item is None or item.status != "confirmed" or (
        entity_id and item.entity_id != entity_id
    ):
        raise HTTPException(status_code=404, detail="已确认流水不存在")
    before = {
        "status": item.internal_transfer_status,
        "source": item.internal_transfer_source,
        "target_entity_id": item.internal_transfer_counterparty_entity_id,
    }
    target: BusinessEntity | None = None
    if payload.target_entity_id:
        target = _entity_by_id(db, payload.target_entity_id)

    if payload.decision == "confirm":
        exact_target_id, _source, _target_name = _exact_internal_transfer_match(db, item)
        _is_candidate, _candidate_reason, candidate_target_name = (
            _internal_transfer_candidate(db, item)
        )
        candidate_target = (
            db.scalar(
                select(BusinessEntity).where(
                    BusinessEntity.name == candidate_target_name
                )
            )
            if candidate_target_name
            else None
        )
        target_id = (
            target.id
            if target
            else exact_target_id
            or (candidate_target.id if candidate_target else None)
        )
        if target_id is None:
            raise HTTPException(
                status_code=422,
                detail="人工确认内部划转时必须选择本集团目标公司",
            )
        item.internal_transfer_status = "manual_confirmed"
        item.internal_transfer_source = "manual_finance_review"
        item.internal_transfer_counterparty_entity_id = target_id
    elif payload.decision == "reject":
        item.internal_transfer_status = "not_internal"
        item.internal_transfer_source = "manual_finance_review"
        item.internal_transfer_counterparty_entity_id = None
    else:
        item.internal_transfer_status = "unreviewed"
        item.internal_transfer_source = None
        item.internal_transfer_counterparty_entity_id = None
        # Reset immediately re-applies only a deterministic exact match.
        _refresh_auto_internal_transfers(db, [item])

    item.internal_transfer_reviewed_by_user_id = (
        None if payload.decision == "reset" else user.id
    )
    item.internal_transfer_reviewed_at = (
        None if payload.decision == "reset" else datetime.now(timezone.utc)
    )
    db.add(AuditLog(
        user_id=user.id,
        action="finance_internal_transfer_review",
        details_json=json.dumps({
            "transaction_id": item.id,
            "decision": payload.decision,
            "note": payload.note,
            "before": before,
            "after": {
                "status": item.internal_transfer_status,
                "source": item.internal_transfer_source,
                "target_entity_id": item.internal_transfer_counterparty_entity_id,
            },
        }, ensure_ascii=False),
    ))
    db.commit()
    return _internal_transfer_payload(db, item)


@router.patch("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: str,
    payload: FinanceTransactionUpdate,
    entity_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_finance_edit(user)
    item = db.get(BankTransaction, transaction_id)
    if item is None or (entity_id and item.entity_id != entity_id):
        raise HTTPException(status_code=404, detail="流水不存在")
    batch = db.get(BankStatementBatch, item.batch_id)
    if batch and batch.status == "confirmed":
        raise HTTPException(status_code=409, detail="已确认批次不能直接修改")
    if payload.pm_project_id:
        project = db.get(ManagedProject, payload.pm_project_id)
        if project is None:
            raise HTTPException(status_code=422, detail="关联项目不存在")
        if project.entity_id and project.entity_id != item.entity_id:
            raise HTTPException(status_code=422, detail="不能关联其他公司的项目")
    before = {
        "transacted_at": item.transacted_at.isoformat(),
        "counterparty": item.counterparty,
        "summary": item.summary,
        "category": item.category,
        "note": item.note,
        "pm_project_id": item.pm_project_id,
    }
    updated_fields = payload.model_fields_set
    if "transacted_at" in updated_fields and payload.transacted_at is not None:
        edited_at = payload.transacted_at
        if edited_at.tzinfo is None:
            edited_at = edited_at.replace(tzinfo=SHANGHAI_ZONE)
        item.transacted_at = edited_at.astimezone(timezone.utc)
    if "counterparty" in updated_fields:
        item.counterparty = payload.counterparty.strip() if payload.counterparty else None
    if "summary" in updated_fields:
        item.summary = payload.summary.strip() if payload.summary else None
    item.category = payload.category.strip()
    item.note = payload.note
    item.pm_project_id = payload.pm_project_id
    db.add(AuditLog(
        user_id=user.id,
        action="finance_transaction_update",
        details_json=json.dumps({
            "transaction_id": item.id,
            "before": before,
            "after": {
                "transacted_at": item.transacted_at.isoformat(),
                "counterparty": item.counterparty,
                "summary": item.summary,
                "category": item.category,
                "note": item.note,
                "pm_project_id": item.pm_project_id,
            },
        }, ensure_ascii=False),
    ))
    db.commit()
    return {"status": "updated", "transaction_id": item.id}


@router.post("/statements/{batch_id}/confirm")
def confirm_statement_batch(
    batch_id: str,
    entity_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_finance_edit(user)
    batch = db.get(BankStatementBatch, batch_id)
    if batch is None or (entity_id and batch.entity_id != entity_id):
        raise HTTPException(status_code=404, detail="流水批次不存在")
    if batch.status == "confirmed":
        return {"status": "confirmed", "batch_id": batch.id}
    if batch.error_count:
        raise HTTPException(status_code=409, detail="本批次存在未解析行，请核对原文件后重新上传")
    transactions = db.scalars(
        select(BankTransaction).where(BankTransaction.batch_id == batch.id)
    ).all()
    if not transactions:
        raise HTTPException(status_code=409, detail="本批次没有可确认流水")
    for item in transactions:
        item.status = "confirmed"
    batch.status = "confirmed"
    batch.confirmed_by_user_id = user.id
    batch.confirmed_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=user.id,
        action="finance_statement_confirm",
        details_json=json.dumps({"batch_id": batch.id, "row_count": len(transactions)}, ensure_ascii=False),
    ))
    db.commit()
    return {"status": "confirmed", "batch_id": batch.id, "row_count": len(transactions)}


@router.post("/cash")
def create_cash_entry(
    payload: CashEntryCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not _cash_edit_allowed(user):
        raise HTTPException(status_code=403, detail="仅财务及两名最高管理账号可以登记现金")
    entity = (
        _entity_by_id(db, payload.entity_id)
        if payload.entity_id
        else _entity(db, payload.company_name, user)
    )
    if entity.name != HEADQUARTERS_ENTITY_NAME:
        raise HTTPException(status_code=403, detail="账外现金仅归属于京奥电竞总公司")
    if payload.pm_project_id:
        project = db.get(ManagedProject, payload.pm_project_id)
        if project is None:
            raise HTTPException(status_code=422, detail="关联项目不存在")
        if project.entity_id and project.entity_id != entity.id:
            raise HTTPException(status_code=422, detail="不能关联其他公司的项目")
    entry = CashEntry(
        entity_id=entity.id,
        cash_account=payload.cash_account,
        transaction_date=payload.transaction_date,
        direction=payload.direction,
        amount=payload.amount,
        category=payload.category,
        note=payload.note,
        pm_project_id=payload.pm_project_id,
        created_by_user_id=user.id,
    )
    db.add(entry)
    db.flush()
    db.add(AuditLog(
        user_id=user.id,
        action="finance_cash_create",
        details_json=json.dumps({
            "entry_id": entry.id,
            "company": entity.name,
            "direction": entry.direction,
            "amount": str(entry.amount),
        }, ensure_ascii=False),
    ))
    db.commit()
    return {"id": entry.id, "status": "created"}


@router.get("/cash")
def list_cash_entries(
    limit: int = Query(default=100, ge=1, le=500),
    entity_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_finance_view(user)
    query = select(CashEntry)
    if entity_id:
        entity = _entity_by_id(db, entity_id)
        if entity.name != HEADQUARTERS_ENTITY_NAME:
            return []
        query = query.where(CashEntry.entity_id == entity_id)
    entries = db.scalars(
        query.order_by(CashEntry.transaction_date.desc(), CashEntry.created_at.desc()).limit(limit)
    ).all()
    return [{
        "id": item.id,
        "company": db.get(BusinessEntity, item.entity_id).name,
        "cash_account": item.cash_account,
        "transaction_date": item.transaction_date,
        "direction": item.direction,
        "amount": item.amount,
        "category": item.category,
        "note": item.note,
        "pm_project_id": item.pm_project_id,
    } for item in entries]


@router.get("/dashboard")
def finance_dashboard(
    from_date: date | None = None,
    to_date: date | None = None,
    entity_id: str | None = None,
    include_internal_transfers: bool = Query(default=False),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_finance_view(user)
    # Bank statements are normally uploaded with a one-week delay.  The
    # executive dashboard therefore defaults to the previous rolling 7-day
    # window, rather than a current-week window that is predictably empty.
    period_end = to_date or (date.today() - timedelta(days=7))
    period_start = from_date or (period_end - timedelta(days=6))
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    selected_entity = _entity_by_id(db, entity_id) if entity_id else None
    all_transactions = db.scalars(select(BankTransaction)).all()
    transactions = [
        item for item in all_transactions if item.status == "confirmed"
    ]
    cash_entries = db.scalars(select(CashEntry)).all()
    if selected_entity:
        transactions = [item for item in transactions if item.entity_id == entity_id]
        all_transactions = [
            item for item in all_transactions if item.entity_id == entity_id
        ]
        cash_entries = (
            [item for item in cash_entries if item.entity_id == entity_id]
            if selected_entity.name == HEADQUARTERS_ENTITY_NAME
            else []
        )

    # Exact group accounts/names are re-evaluated idempotently so an account
    # registered after an old statement was imported is picked up.  Manual
    # finance decisions always win.
    if _refresh_auto_internal_transfers(db, transactions):
        db.commit()
    operating_transactions = (
        transactions
        if include_internal_transfers
        else [item for item in transactions if not _is_internal_transfer(item)]
    )

    in_period = [
        item for item in operating_transactions
        if period_start <= _business_date(item.transacted_at) <= period_end
    ]
    # The executive dashboard is the company's on-book banking view.  Manual
    # off-book cash is deliberately kept in the separate cash ledger and must
    # never change bank income, bank expense, net inflow, or the trend chart.
    income = sum((item.income for item in in_period), Decimal("0"))
    expense = sum((item.expense for item in in_period), Decimal("0"))

    weekly_top_income, weekly_top_expense = _top_counterparties(in_period)

    anomaly_rows = _transaction_alerts(
        operating_transactions, period_start, period_end
    )

    month_reference = to_date or date.today()
    current_month_start = date(month_reference.year, month_reference.month, 1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = date(previous_month_end.year, previous_month_end.month, 1)
    previous_month_transactions = [
        item for item in operating_transactions
        if previous_month_start <= _business_date(item.transacted_at) <= previous_month_end
    ]
    previous_month_income = sum(
        (item.income for item in previous_month_transactions), Decimal("0")
    )
    previous_month_expense = sum(
        (item.expense for item in previous_month_transactions), Decimal("0")
    )
    monthly_top_income, monthly_top_expense = _top_counterparties(
        previous_month_transactions
    )
    monthly_anomalies = _transaction_alerts(
        operating_transactions,
        previous_month_start,
        previous_month_end,
    )

    current_year_start = date(month_reference.year, 1, 1)
    current_year_end = month_reference
    current_year_transactions = [
        item for item in operating_transactions
        if current_year_start <= _business_date(item.transacted_at) <= current_year_end
    ]
    current_year_income = sum(
        (item.income for item in current_year_transactions), Decimal("0")
    )
    current_year_expense = sum(
        (item.expense for item in current_year_transactions), Decimal("0")
    )

    # Balance is evidence from the bank account itself.  It must remain the
    # real closing balance regardless of the operating-flow toggle.
    latest_by_account: dict[str, BankTransaction] = {}
    for item in transactions:
        previous = latest_by_account.get(item.account_id)
        if previous is None or _transaction_order_key(item) > _transaction_order_key(previous):
            latest_by_account[item.account_id] = item
    bank_balance = sum(
        (item.balance for item in latest_by_account.values() if item.balance is not None),
        Decimal("0"),
    )
    cash_balance = sum(
        (
            item.amount
            if item.direction in {"opening", "income"}
            else -item.amount
        )
        for item in cash_entries
    ) if cash_entries else Decimal("0")

    weekly: dict[tuple[int, int], dict[str, Decimal | date]] = defaultdict(
        lambda: {"income": Decimal("0"), "expense": Decimal("0")}
    )
    for item in operating_transactions:
        iso = _business_date(item.transacted_at).isocalendar()
        key = (iso.year, iso.week)
        weekly[key]["income"] += item.income
        weekly[key]["expense"] += item.expense
    weekly_rows = []
    for (year, week), values in sorted(weekly.items())[-26:]:
        week_start = date.fromisocalendar(year, week, 1)
        weekly_rows.append({
            "year": year,
            "week": week,
            "week_start": week_start,
            "income": values["income"],
            "expense": values["expense"],
            "net": values["income"] - values["expense"],
        })

    account_rows = []
    for account_id, transaction in latest_by_account.items():
        account = db.get(FinancialAccount, account_id)
        entity = db.get(BusinessEntity, transaction.entity_id)
        account_rows.append({
            "company": entity.name if entity else "",
            "bank_name": account.bank_name if account else "",
            "account": account.account_number_masked if account else "",
            "balance": transaction.balance,
            "as_of": transaction.transacted_at,
        })
    pending_query = select(BankStatementBatch.id).where(
        BankStatementBatch.status == "pending"
    )
    if selected_entity:
        pending_query = pending_query.where(
            BankStatementBatch.entity_id == selected_entity.id
        )
    return {
        "confidentiality": "L4",
        "period_start": period_start,
        "period_end": period_end,
        "income": income,
        "expense": expense,
        "net": income - expense,
        "weekly_top_income": weekly_top_income,
        "weekly_top_expense": weekly_top_expense,
        "anomaly_count": len(anomaly_rows),
        "anomalies": anomaly_rows[:20],
        "monthly_top_income": monthly_top_income,
        "monthly_top_expense": monthly_top_expense,
        "monthly_anomaly_count": len(monthly_anomalies),
        "monthly_anomalies": monthly_anomalies[:20],
        "oa_rule_ready": False,
        "planned_rules": [item["name"] for item in OA_PLANNED_ALERT_RULES],
        "alert_rule_status": {
            "version": "v2",
            "oa_rule_ready": False,
            "oa_integration_status": "not_connected",
            "active_rules": [
                "首次出现的往来单位（同一统计周期仅首笔）",
                (
                    "同单位同方向金额突增（至少 3 笔更早历史；"
                    "本笔大于历史中位数 3 倍且差额超过 1 万元）"
                ),
                "负数、收支冲突、零金额、余额断裂、疑似重复及字段缺失",
            ],
            "planned_rules": list(OA_PLANNED_ALERT_RULES),
        },
        "previous_month": {
            "period_start": previous_month_start,
            "period_end": previous_month_end,
            "income": previous_month_income,
            "expense": previous_month_expense,
            "net": previous_month_income - previous_month_expense,
        },
        "current_year": {
            "period_start": current_year_start,
            "period_end": current_year_end,
            "income": current_year_income,
            "expense": current_year_expense,
            "net": current_year_income - current_year_expense,
        },
        "bank_balance": bank_balance,
        "cash_balance": cash_balance,
        "total_balance": bank_balance + cash_balance,
        "pending_batches": db.scalar(pending_query.limit(1)) is not None,
        "accounts": account_rows,
        "weekly": weekly_rows,
        "include_internal_transfers": include_internal_transfers,
        "health": _finance_health(
            transactions=transactions,
            operating_transactions=operating_transactions,
            period_start=period_start,
            period_end=period_end,
            include_internal_transfers=include_internal_transfers,
        ),
    }
