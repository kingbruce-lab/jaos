from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import func, select

from .auth import bootstrap_admin
from .backup import (
    BackupError,
    create_backup,
    isolated_restore_check,
    restore_sqlite_backup,
    verify_backup,
)
from .database import SessionLocal, init_database
from .derivatives import derive_pending
from .embeddings import index_pending_embeddings
from .evaluation import (
    generate_business_gold_candidates,
    run_concurrency_evaluation,
    run_technical_evaluation,
)
from .ingest import ingest_manifest, scan_inbox
from .maintained_artifacts import run_due_artifact_reviews
from .models import AuditLog, Chunk, Document, InboxIssue, Project, User
from .config import settings
from .source_integrity import reconcile_sources, source_health_counts
from .storage_layout import (
    normalize_inbox_storage,
    normalize_web_upload_storage,
)


def command_init() -> int:
    init_database()
    with SessionLocal() as db:
        bootstrap_admin(db)
    print(json.dumps({"status": "ready"}, ensure_ascii=False))
    return 0


def command_ingest(manifest: str) -> int:
    init_database()
    with SessionLocal() as db:
        bootstrap_admin(db)
        results = ingest_manifest(db, Path(manifest).resolve())
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if any(item["status"] == "failed" for item in results) else 0


def command_scan_inbox(path: str | None = None) -> int:
    init_database()
    with SessionLocal() as db:
        bootstrap_admin(db)
        result = scan_inbox(db, Path(path).resolve() if path else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "unavailable" else 0


def command_reconcile_sources(path: str | None = None) -> int:
    init_database()
    root = Path(path).resolve() if path else settings.knowledge_root
    with SessionLocal() as db:
        result = reconcile_sources(db, root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_normalize_web_storage(apply_changes: bool) -> int:
    init_database()
    with SessionLocal() as db:
        result = normalize_web_upload_storage(
            db,
            settings.knowledge_root,
            settings.inbox_dir,
            apply_changes=apply_changes,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_normalize_inbox_storage(apply_changes: bool) -> int:
    init_database()
    with SessionLocal() as db:
        result = normalize_inbox_storage(
            db,
            settings.knowledge_root,
            settings.inbox_dir,
            apply_changes=apply_changes,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_evolution_due() -> int:
    init_database()
    with SessionLocal() as db:
        result = run_due_artifact_reviews(db)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def command_status() -> int:
    init_database()
    with SessionLocal() as db:
        payload = {
            "projects": db.scalar(select(func.count(Project.id))) or 0,
            "documents": db.scalar(select(func.count(Document.id))) or 0,
            "chunks": db.scalar(select(func.count(Chunk.id))) or 0,
            "open_inbox_issues": db.scalar(
                select(func.count(InboxIssue.id)).where(
                    InboxIssue.resolved_at.is_(None)
                )
            ) or 0,
            "source_health": source_health_counts(db),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_derive(*, retry_failed: bool = True) -> int:
    init_database()
    with SessionLocal() as db:
        bootstrap_admin(db)
        results = derive_pending(db, retry_failed=retry_failed)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if any(item["status"] == "failed" for item in results) else 0


def command_embed(force: bool = False) -> int:
    init_database()
    with SessionLocal() as db:
        results = index_pending_embeddings(db, force=force)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if results["status"] in {"blocked", "failed"} else 0


def command_evaluate() -> int:
    init_database()
    with SessionLocal() as db:
        report = run_technical_evaluation(db)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["technical_status"] == "passed" else 1


def command_concurrency() -> int:
    init_database()
    report = run_concurrency_evaluation(SessionLocal)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


def command_governance_ai(actor: str, apply_changes: bool) -> int:
    from .main import ai_classify_governance_documents
    from .schemas import GovernanceAIClassifyRequest

    init_database()
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.username == actor, User.active.is_(True))
        )
        if user is None or user.role != "founder":
            raise ValueError("actor must be an active founder")
        result = ai_classify_governance_documents(
            GovernanceAIClassifyRequest(
                dry_run=not apply_changes,
                confirmation="确认AI梳理资料密级",
            ),
            user=user,
            db=db,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_business_gold_generate(actor: str, target: int) -> int:
    init_database()
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.username == actor, User.active.is_(True))
        )
        if user is None or user.role not in {"founder", "knowledge_admin"}:
            raise ValueError("actor must be an active founder or knowledge admin")
        result = generate_business_gold_candidates(
            db,
            user=user,
            target=target,
        )
        generation = result.get("generation", {})
        db.add(
            AuditLog(
                user_id=user.id,
                action="business_gold_candidates_generated",
                details_json=json.dumps(generation, ensure_ascii=False),
            )
        )
        db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_backup(output: str | None = None) -> int:
    init_database()
    with SessionLocal() as db:
        result = create_backup(db, Path(output).resolve() if output else None)
    verification = verify_backup(Path(result["path"]))
    print(
        json.dumps(
            {**result, "verification": verification["status"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_verify_backup(path: str, restore_check: bool = False) -> int:
    package = Path(path).resolve()
    result = verify_backup(package)
    if restore_check and result["database_engine"] == "sqlite":
        result["restore_check"] = isolated_restore_check(package)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_restore_sqlite(path: str, target: str) -> int:
    result = restore_sqlite_backup(
        Path(path).resolve(),
        Path(target).resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="京奥AI智能运营系统（JAOS）本地管理命令")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--manifest", required=True)
    scan_parser = subparsers.add_parser("scan-inbox")
    scan_parser.add_argument("--path")
    reconcile_parser = subparsers.add_parser("reconcile-sources")
    reconcile_parser.add_argument("--path")
    normalize_parser = subparsers.add_parser("normalize-web-storage")
    normalize_parser.add_argument("--apply", action="store_true")
    normalize_inbox_parser = subparsers.add_parser("normalize-inbox-storage")
    normalize_inbox_parser.add_argument("--apply", action="store_true")
    subparsers.add_parser("evolution-due")
    subparsers.add_parser("status")
    derive_parser = subparsers.add_parser("derive")
    derive_parser.add_argument("--only-new", action="store_true")
    embed_parser = subparsers.add_parser("embed")
    embed_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("evaluate")
    subparsers.add_parser("concurrency")
    governance_parser = subparsers.add_parser("governance-ai")
    governance_parser.add_argument("--actor", default="founder")
    governance_parser.add_argument("--apply", action="store_true")
    gold_parser = subparsers.add_parser("business-gold-generate")
    gold_parser.add_argument("--actor", default="founder")
    gold_parser.add_argument("--target", type=int, default=150, choices=range(1, 151))
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--output")
    verify_parser = subparsers.add_parser("verify-backup")
    verify_parser.add_argument("--path", required=True)
    verify_parser.add_argument("--restore-check", action="store_true")
    restore_parser = subparsers.add_parser("restore-sqlite")
    restore_parser.add_argument("--path", required=True)
    restore_parser.add_argument("--target", required=True)
    args = parser.parse_args()
    if args.command == "init":
        return command_init()
    if args.command == "ingest":
        return command_ingest(args.manifest)
    if args.command == "scan-inbox":
        return command_scan_inbox(args.path)
    if args.command == "reconcile-sources":
        return command_reconcile_sources(args.path)
    if args.command == "normalize-web-storage":
        return command_normalize_web_storage(args.apply)
    if args.command == "normalize-inbox-storage":
        return command_normalize_inbox_storage(args.apply)
    if args.command == "evolution-due":
        return command_evolution_due()
    if args.command == "derive":
        return command_derive(retry_failed=not args.only_new)
    if args.command == "embed":
        return command_embed(args.force)
    if args.command == "evaluate":
        return command_evaluate()
    if args.command == "concurrency":
        return command_concurrency()
    if args.command == "governance-ai":
        return command_governance_ai(args.actor, args.apply)
    if args.command == "business-gold-generate":
        return command_business_gold_generate(args.actor, args.target)
    if args.command == "backup":
        return command_backup(args.output)
    if args.command == "verify-backup":
        return command_verify_backup(args.path, args.restore_check)
    if args.command == "restore-sqlite":
        return command_restore_sqlite(args.path, args.target)
    return command_status()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackupError as exc:
        print(
            json.dumps(
                {"status": "failed", "reason": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(1) from None
