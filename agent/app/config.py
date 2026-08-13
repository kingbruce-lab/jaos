from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus


AGENT_ROOT = Path(__file__).resolve().parents[1]


def _as_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    data_dir: Path
    managed_source_dir: Path
    knowledge_root: Path
    inbox_dir: Path
    inbox_scan_interval_seconds: int
    inbox_settle_seconds: int
    inbox_max_file_bytes: int
    source_reconcile_interval_seconds: int
    source_health_max_age_seconds: int
    database_url: str
    dev_mode: bool
    copy_sources: bool
    bootstrap_username: str
    bootstrap_password: str | None
    session_hours: int
    cors_origins: tuple[str, ...]
    gateway_base_url: str
    gateway_api_key: str | None
    embedding_model: str
    embedding_enabled: bool
    embedding_l3_enabled: bool
    embedding_batch_size: int
    embedding_concurrency: int
    llm_enabled: bool
    llm_l3_enabled: bool
    primary_model: str
    fallback_model: str
    llm_timeout_seconds: int
    llm_max_context_characters: int
    login_max_attempts: int
    login_window_seconds: int
    login_lockout_seconds: int
    backup_dir: Path
    offsite_backup_status_file: Path
    evaluation_dir: Path
    backup_max_age_seconds: int
    offsite_backup_max_age_seconds: int
    disk_warning_percent: int
    disk_critical_percent: int
    memory_warning_percent: int
    memory_critical_percent: int
    api_title: str = "京奥AI智能运营系统（JAOS）Agent API"
    policy_version: str = "jingao-policy-v1.9"


def load_settings() -> Settings:
    environment = os.getenv("JINGAO_ENV", "development").strip().lower()
    dev_mode = _as_bool("JINGAO_DEV_MODE", environment != "production")
    copy_sources = _as_bool("JINGAO_COPY_SOURCES", dev_mode)
    data_dir = Path(os.getenv("JINGAO_DATA_DIR", AGENT_ROOT / "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    managed_source_dir = Path(
        os.getenv("JINGAO_MANAGED_SOURCE_DIR", data_dir / "sources")
    ).resolve()
    if copy_sources:
        managed_source_dir.mkdir(parents=True, exist_ok=True)
    database_url = os.getenv("DATABASE_URL")
    if not database_url and os.getenv("JINGAO_DB_HOST"):
        db_user = quote_plus(os.getenv("JINGAO_DB_USER", "jingao"))
        db_password = quote_plus(os.getenv("JINGAO_DB_PASSWORD", ""))
        db_host = os.getenv("JINGAO_DB_HOST", "db")
        db_port = int(os.getenv("JINGAO_DB_PORT", "5432"))
        db_name = quote_plus(os.getenv("JINGAO_DB_NAME", "jingao"))
        database_url = (
            f"postgresql+psycopg://{db_user}:{db_password}"
            f"@{db_host}:{db_port}/{db_name}"
        )
    if not database_url:
        database_url = f"sqlite:///{(data_dir / 'jingao.db').as_posix()}"
    bootstrap_password = os.getenv("JINGAO_BOOTSTRAP_PASSWORD")
    if dev_mode and not bootstrap_password:
        bootstrap_password = "jingao-local"
    origins = tuple(
        item.strip()
        for item in os.getenv(
            "JINGAO_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if item.strip()
    )
    disk_warning_percent = max(
        50,
        min(int(os.getenv("JINGAO_DISK_WARNING_PERCENT", "80")), 95),
    )
    disk_critical_percent = max(
        disk_warning_percent + 1,
        min(int(os.getenv("JINGAO_DISK_CRITICAL_PERCENT", "90")), 99),
    )
    memory_warning_percent = max(
        50,
        min(int(os.getenv("JINGAO_MEMORY_WARNING_PERCENT", "80")), 95),
    )
    memory_critical_percent = max(
        memory_warning_percent + 1,
        min(int(os.getenv("JINGAO_MEMORY_CRITICAL_PERCENT", "90")), 99),
    )
    backup_dir = Path(
        os.getenv("JINGAO_BACKUP_DIR", AGENT_ROOT / "backups")
    ).resolve()
    return Settings(
        environment=environment,
        data_dir=data_dir,
        managed_source_dir=managed_source_dir,
        knowledge_root=Path(
            os.getenv("JINGAO_KNOWLEDGE_ROOT", data_dir)
        ).resolve(),
        inbox_dir=Path(
            os.getenv("JINGAO_INBOX_DIR", data_dir / "inbox")
        ).resolve(),
        inbox_scan_interval_seconds=max(
            60,
            int(os.getenv("JINGAO_INBOX_SCAN_INTERVAL_SECONDS", "900")),
        ),
        inbox_settle_seconds=max(
            30,
            int(os.getenv("JINGAO_INBOX_SETTLE_SECONDS", "120")),
        ),
        inbox_max_file_bytes=max(
            1024 * 1024,
            int(os.getenv("JINGAO_INBOX_MAX_FILE_BYTES", str(2 * 1024**3))),
        ),
        source_reconcile_interval_seconds=max(
            3600,
            int(
                os.getenv(
                    "JINGAO_SOURCE_RECONCILE_INTERVAL_SECONDS",
                    "86400",
                )
            ),
        ),
        source_health_max_age_seconds=max(
            3600,
            int(
                os.getenv(
                    "JINGAO_SOURCE_HEALTH_MAX_AGE_SECONDS",
                    "93600",
                )
            ),
        ),
        database_url=database_url,
        dev_mode=dev_mode,
        copy_sources=copy_sources,
        bootstrap_username=os.getenv("JINGAO_BOOTSTRAP_USERNAME", "founder"),
        bootstrap_password=bootstrap_password,
        session_hours=int(os.getenv("JINGAO_SESSION_HOURS", "8")),
        cors_origins=origins,
        gateway_base_url=os.getenv(
            "ORIGINGAME_BASE_URL",
            "https://api.origingame.dev/v1",
        ).rstrip("/"),
        gateway_api_key=os.getenv("ORIGINGAME_API_KEY") or None,
        embedding_model=os.getenv(
            "JINGAO_EMBEDDING_MODEL",
            "gemini-embedding-2",
        ),
        embedding_enabled=_as_bool("JINGAO_EMBEDDING_ENABLED", False),
        embedding_l3_enabled=_as_bool("JINGAO_EMBEDDING_L3_ENABLED", False),
        embedding_batch_size=max(
            1,
            min(int(os.getenv("JINGAO_EMBEDDING_BATCH_SIZE", "16")), 64),
        ),
        embedding_concurrency=max(
            1,
            min(int(os.getenv("JINGAO_EMBEDDING_CONCURRENCY", "4")), 4),
        ),
        llm_enabled=_as_bool("JINGAO_LLM_ENABLED", False),
        llm_l3_enabled=_as_bool("JINGAO_LLM_L3_ENABLED", False),
        primary_model=(
            os.getenv("JINGAO_PRIMARY_MODEL", "grok-4.5").strip()
            or "grok-4.5"
        ),
        fallback_model=(
            os.getenv(
                "JINGAO_FALLBACK_MODEL",
                "deepseek-v4-flash",
            ).strip()
            or "deepseek-v4-flash"
        ),
        llm_timeout_seconds=max(
            5,
            min(int(os.getenv("JINGAO_LLM_TIMEOUT_SECONDS", "45")), 120),
        ),
        llm_max_context_characters=max(
            1000,
            min(
                int(
                    os.getenv(
                        "JINGAO_LLM_MAX_CONTEXT_CHARACTERS",
                        "10000",
                    )
                ),
                30000,
            ),
        ),
        login_max_attempts=max(
            3,
            min(int(os.getenv("JINGAO_LOGIN_MAX_ATTEMPTS", "5")), 20),
        ),
        login_window_seconds=max(
            60,
            int(os.getenv("JINGAO_LOGIN_WINDOW_SECONDS", "900")),
        ),
        login_lockout_seconds=max(
            60,
            int(os.getenv("JINGAO_LOGIN_LOCKOUT_SECONDS", "900")),
        ),
        backup_dir=backup_dir,
        offsite_backup_status_file=Path(
            os.getenv(
                "JINGAO_OFFSITE_STATUS_FILE",
                backup_dir / ".jaos-offsite-status.json",
            )
        ).resolve(),
        evaluation_dir=Path(
            os.getenv("JINGAO_EVALUATION_DIR", data_dir / "evaluations")
        ).resolve(),
        backup_max_age_seconds=max(
            3600,
            int(os.getenv("JINGAO_BACKUP_MAX_AGE_SECONDS", "93600")),
        ),
        offsite_backup_max_age_seconds=max(
            86400,
            int(
                os.getenv(
                    "JINGAO_OFFSITE_BACKUP_MAX_AGE_SECONDS",
                    "604800",
                )
            ),
        ),
        disk_warning_percent=disk_warning_percent,
        disk_critical_percent=disk_critical_percent,
        memory_warning_percent=memory_warning_percent,
        memory_critical_percent=memory_critical_percent,
    )


settings = load_settings()
