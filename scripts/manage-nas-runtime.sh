#!/bin/sh
set -eu

runtime_dir="/vol1/@team/京奥智库/00_部署/jingao-runtime"
project_name="jingao-copilot"
compose_file="$runtime_dir/docker-compose.yml"
env_file="$runtime_dir/.env"

compose() {
  docker compose \
    -p "$project_name" \
    --env-file "$env_file" \
    -f "$compose_file" \
    "$@"
}

case "${1:-}" in
  build)
    rm -f "$runtime_dir/build.exit" "$runtime_dir/build.log"
    nohup sh -c "
      cd '$runtime_dir'
      docker compose -p '$project_name' --env-file '$env_file' -f '$compose_file' build agent web > '$runtime_dir/build.log' 2>&1
      printf '%s\n' \"\$?\" > '$runtime_dir/build.exit'
    " >/dev/null 2>&1 &
    printf 'build-started\n'
    ;;
  build-status)
    if [ -f "$runtime_dir/build.log" ]; then
      tail -n 60 "$runtime_dir/build.log"
    fi
    if [ -f "$runtime_dir/build.exit" ]; then
      printf 'BUILD_EXIT='
      cat "$runtime_dir/build.exit"
    else
      printf 'BUILD_EXIT=RUNNING\n'
    fi
    ;;
  start)
    compose up -d --no-build --pull never
    ;;
  status)
    compose ps
    ;;
  release)
    printf 'CURRENT_SOURCE='
    sed -n '1p' "$runtime_dir/CURRENT-SOURCE.txt" 2>/dev/null || printf 'unknown\n'
    printf 'PREVIOUS_SOURCE='
    sed -n '1p' "$runtime_dir/PREVIOUS-SOURCE.txt" 2>/dev/null || printf 'none\n'
    printf 'VERSION='
    sed -n '1p' "$runtime_dir/VERSION" 2>/dev/null || printf 'unversioned\n'
    tail -n 5 "$runtime_dir/RELEASE-HISTORY.log" 2>/dev/null || true
    ;;
  offsite-backup)
    "$runtime_dir/sync-offsite-backup.sh" --env-file "$env_file"
    ;;
  rollback)
    previous_source="$(sed -n '1p' "$runtime_dir/PREVIOUS-SOURCE.txt" 2>/dev/null | tr -d '\r')"
    current_source="$(sed -n '1p' "$runtime_dir/CURRENT-SOURCE.txt" 2>/dev/null | tr -d '\r')"
    if [ -z "$previous_source" ] || [ ! -f "$previous_source/scripts/deploy-nas-runtime.sh" ]; then
      printf 'rollback-unavailable: PREVIOUS-SOURCE is missing or invalid\n' >&2
      exit 3
    fi
    if [ "$previous_source" = "$current_source" ]; then
      printf 'rollback-unavailable: previous and current sources are identical\n' >&2
      exit 3
    fi
    printf 'Creating a sealed pre-rollback backup...\n'
    compose exec -T backup python -m app.cli backup --output /backup >/dev/null
    printf 'Switching source to %s\n' "$previous_source"
    sh "$previous_source/scripts/deploy-nas-runtime.sh"
    compose build agent web
    compose up -d --no-build --pull never
    compose ps
    ;;
  logs)
    compose logs --tail 100
    ;;
  down)
    compose down
    ;;
  *)
    printf 'usage: %s {build|build-status|start|status|release|offsite-backup|rollback|logs|down}\n' "$0" >&2
    exit 2
    ;;
esac
