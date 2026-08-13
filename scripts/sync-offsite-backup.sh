#!/bin/sh
set -eu

runtime_dir='/vol1/@team/京奥智库/00_部署/jingao-runtime'
env_file="$runtime_dir/.env"
source_root=''
target_root=''

while [ "$#" -gt 0 ]; do
  case "$1" in
    --env-file)
      env_file="$2"
      shift 2
      ;;
    --source)
      source_root="$2"
      shift 2
      ;;
    --target)
      target_root="$2"
      shift 2
      ;;
    *)
      printf 'usage: %s [--env-file FILE] [--source DIR] [--target DIR]\n' "$0" >&2
      exit 2
      ;;
  esac
done

env_value() {
  key="$1"
  sed -n "s/^${key}=//p" "$env_file" 2>/dev/null | tail -1 | tr -d '\r'
}

[ -n "$source_root" ] || source_root="$(env_value JINGAO_BACKUP_PATH)"
[ -n "$source_root" ] || source_root='/vol1/@team/京奥智库/02_备份'
[ -n "$target_root" ] || target_root="$(env_value JINGAO_OFFSITE_BACKUP_PATH)"
status_file="$source_root/.jaos-offsite-status.json"

write_status() {
  state="$1"
  code="$2"
  message="$3"
  configured="$4"
  available="$5"
  separate="$6"
  verified="$7"
  package="${8:-}"
  now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  mkdir -p "$source_root"
  umask 077
  temporary="$status_file.tmp.$$"
  cat > "$temporary" <<EOF
{"status":"$state","code":"$code","message":"$message","media_configured":$configured,"media_available":$available,"separate_device":$separate,"verified":$verified,"latest_package":"$package","last_attempt_at":"$now","latest_completed_at":"$now"}
EOF
  mv -f "$temporary" "$status_file"
}

if [ -z "$target_root" ]; then
  write_status warning media_not_configured '尚未配置第二物理介质；主备份仍只在NAS单盘' false false false false
  exit 2
fi
if [ ! -d "$source_root" ]; then
  printf 'Primary backup directory is unavailable: %s\n' "$source_root" >&2
  exit 1
fi
if [ ! -d "$target_root" ]; then
  write_status warning media_not_mounted '第二备份介质未插入或未挂载' true false false false
  exit 2
fi
if [ ! -w "$target_root" ]; then
  write_status critical media_not_writable '第二备份介质不可写' true true false false
  exit 1
fi

source_real="$(readlink -f "$source_root")"
target_real="$(readlink -f "$target_root")"
case "$target_real/" in
  "$source_real/"*|"$source_real/")
    write_status critical target_inside_primary '第二备份目标不能位于主备份目录内' true true false false
    exit 1
    ;;
esac
source_device="$(df -P "$source_root" | awk 'END {print $1}')"
target_device="$(df -P "$target_root" | awk 'END {print $1}')"
if [ -z "$source_device" ] || [ "$source_device" = "$target_device" ]; then
  write_status critical same_physical_device '第二备份目标与NAS主备份位于同一物理设备' true true false false
  exit 1
fi

latest="$(
  find "$source_root" -mindepth 1 -maxdepth 1 -type d -name 'jingao-*' \
    -exec test -f '{}/COMPLETE' ';' -exec test -f '{}/manifest.json' ';' -print \
    | sort | tail -1
)"
if [ -z "$latest" ]; then
  write_status critical no_complete_primary_backup '没有可同步的完整主备份' true true true false
  exit 1
fi

package="$(basename "$latest")"
destination_root="$target_root/JAOS-backups"
destination="$destination_root/$package"
stage="$destination_root/.incomplete-$package-$$"
mkdir -p "$destination_root"
if [ ! -d "$destination" ]; then
  if [ -e "$stage" ]; then
    write_status critical staging_conflict '第二备份临时目录冲突，未覆盖任何文件' true true true false "$package"
    exit 1
  fi
  mkdir "$stage"
  cp -a "$latest/." "$stage/"
  sync "$stage" 2>/dev/null || true
  mv "$stage" "$destination"
fi

verification="$(
  docker run --rm --network none \
    -v "$target_root:/offsite:ro" \
    jingao-agent:local \
    python -m app.cli verify-backup --path "/offsite/JAOS-backups/$package" \
    2>&1
)" || {
  write_status critical verification_failed '第二介质备份复制后校验失败' true true true false "$package"
  printf '%s\n' "$verification" >&2
  exit 1
}
if ! printf '%s\n' "$verification" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"verified"'; then
  write_status critical verification_failed '第二介质备份复制后校验失败' true true true false "$package"
  exit 1
fi

write_status ok verified '第二物理介质备份已复制并完成全量哈希校验' true true true true "$package"
printf 'OFFSITE_BACKUP_VERIFIED=%s\n' "$destination"
