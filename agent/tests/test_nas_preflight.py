from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "nas-preflight.sh"
VERIFY_SCRIPT = ROOT / "scripts" / "verify-nas-runtime.sh"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy-nas-runtime.sh"
COMPOSE_FILE = ROOT / "compose.yaml"


def test_nas_preflight_is_read_only_and_checks_required_gates() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "JINGAO_DB_PASSWORD" in text
    assert "JINGAO_BOOTSTRAP_PASSWORD" in text
    assert "JINGAO_KNOWLEDGE_PATH" in text
    assert "JINGAO_BACKUP_PATH" in text
    assert "docker compose --env-file" in text
    assert "MemTotal" in text
    assert "NPROCESSORS_ONLN" in text
    assert "端口 3000" in text
    assert "单盘" in text
    assert "UPS" in text
    forbidden = (
        "docker compose up",
        "docker compose down",
        "docker compose build",
        "chmod ",
        "chown ",
        "rm -",
        "apt ",
        "apk ",
    )
    assert not any(item in text for item in forbidden)


def test_nas_onboarding_never_contains_real_secrets() -> None:
    text = (ROOT / "docs" / "NAS首次上线.md").read_text(encoding="utf-8")
    assert "sk-" not in text
    assert "JINGAO_DB_PASSWORD=" in text
    assert "JINGAO_BOOTSTRAP_PASSWORD=" in text
    assert "不安装、不启动、不改文件、不改权限" in text


def test_runtime_verifier_checks_the_active_compose_and_env_files() -> None:
    text = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert 'compose_file="$runtime/docker-compose.yml"' in text
    assert 'env_file="$runtime/.env"' in text
    assert '--env-file "$env_file"' in text
    assert '-f "$compose_file"' in text
    assert '$runtime/compose.yaml' not in text


def test_deployer_records_the_active_source_directory() -> None:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert 'DEPLOYMENT-PACKAGE.txt' in text
    assert 'CURRENT-SOURCE.txt.new' in text
    assert 'mv -f "$runtime_dir/CURRENT-SOURCE.txt.new"' in text


def test_backup_waits_for_startup_and_reconciles_sources_before_snapshot() -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    backup_service = text.split("\n  backup:\n", 1)[1].split(
        "\n  ingest:\n",
        1,
    )[0]

    assert "JINGAO_KNOWLEDGE_ROOT: /knowledge" in backup_service
    assert "JINGAO_BACKUP_START_DELAY_SECONDS" in backup_service
    delay = backup_service.index("sleep \"$${JINGAO_BACKUP_START_DELAY_SECONDS")
    reconcile = backup_service.index("python -m app.cli reconcile-sources")
    snapshot = backup_service.index("python -m app.cli backup --output /backup")
    assert delay < reconcile < snapshot


def test_agent_image_contains_office_converters_for_legacy_files() -> None:
    dockerfile = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")

    assert "libreoffice-calc" in dockerfile
    assert "libreoffice-writer" in dockerfile
    assert "libreoffice-impress" in dockerfile


def test_ingest_worker_cpu_is_capped_to_preserve_interactive_services() -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    ingest_service = text.split("\n  ingest:\n", 1)[1].split(
        "\n  reconcile:\n",
        1,
    )[0]

    assert "cpus: 2.0" in ingest_service
