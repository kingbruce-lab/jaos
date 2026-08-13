#!/bin/sh
set -eu

runtime='/vol1/@team/京奥智库/00_部署/jingao-runtime'
backup_root='/vol1/@team/京奥智库/02_备份'
project_name='jingao-copilot'
compose_file="$runtime/docker-compose.yml"
env_file="$runtime/.env"
expected_services='db agent web ingest reconcile backup uptime-kuma'
failures=0

compose() {
  docker compose \
    -p "$project_name" \
    --env-file "$env_file" \
    -f "$compose_file" \
    "$@"
}

pass() {
  printf 'PASS|%s\n' "$1"
}

fail() {
  printf 'FAIL|%s\n' "$1"
  failures=$((failures + 1))
}

info() {
  printf 'INFO|%s\n' "$1"
}

check_service() {
  service="$1"
  container_id="$(compose ps -q "$service" 2>/dev/null || true)"
  if [ -z "$container_id" ]; then
    fail "服务未创建：$service"
    return
  fi

  running="$(docker inspect --format '{{.State.Running}}' "$container_id" 2>/dev/null || true)"
  if [ "$running" = 'true' ]; then
    pass "服务正在运行：$service"
  else
    fail "服务未运行：$service"
    return
  fi

  restart_count="$(docker inspect --format '{{.RestartCount}}' "$container_id" 2>/dev/null || printf 'unknown')"
  if [ "$restart_count" = '0' ]; then
    pass "服务无异常重启：$service"
  else
    info "服务重启次数：$service=$restart_count（需结合维护记录判断）"
  fi
}

probe_from_agent() {
  label="$1"
  url="$2"
  if compose exec -T agent python -c \
    'import sys, urllib.request; response = urllib.request.urlopen(sys.argv[1], timeout=10); raise SystemExit(0 if response.status == 200 else 1)' \
    "$url" >/dev/null 2>&1; then
    pass "$label"
  else
    fail "$label"
  fi
}

check_flag() {
  flag="$1"
  expected="$2"
  value="$(
    sed -n "s/^${flag}=//p" "$runtime/.env" |
      tail -1 |
      tr -d '\r'
  )"
  if [ "$value" = "$expected" ]; then
    pass "功能开关符合预期：$flag=$expected"
  else
    fail "功能开关不符合预期：$flag（期望 $expected）"
  fi
}

check_l3_generation_flag() {
  value="$(
    sed -n 's/^JINGAO_LLM_L3_ENABLED=//p' "$runtime/.env" |
      tail -1 |
      tr -d '\r'
  )"
  case "$value" in
    false)
      pass 'L3 生成默认关闭'
      ;;
    true)
      info 'L3 生成总开关已启用；仍须由创始人在每次创作时显式授权'
      ;;
    *)
      fail 'JINGAO_LLM_L3_ENABLED 必须明确为 true 或 false'
      ;;
  esac
}

printf 'JINGAO_RUNTIME_ACCEPTANCE_V1\n'

if [ -f "$compose_file" ] && [ -f "$env_file" ]; then
  pass '运行目录与配置文件存在'
else
  fail '运行目录、docker-compose.yml 或 .env 缺失'
fi

for service in $expected_services; do
  check_service "$service"
done

probe_from_agent 'Agent 健康检查通过' 'http://127.0.0.1:8000/healthz'
probe_from_agent 'Agent 就绪检查通过' 'http://127.0.0.1:8000/readyz'
probe_from_agent '员工 Web 入口可访问' 'http://web:3000/'
probe_from_agent 'Uptime Kuma 可访问' 'http://uptime-kuma:3001/'

latest_backup="$(
  find "$backup_root" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -name 'jingao-*' \
    -printf '%f\n' |
    sort |
    tail -1
)"
if [ -z "$latest_backup" ]; then
  fail '未找到完整备份目录'
else
  backup_json="$(
    compose exec -T backup \
      python -m app.cli verify-backup --path "/backup/$latest_backup" \
      2>/dev/null || true
  )"
  if printf '%s\n' "$backup_json" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"verified"'; then
    pass "最新备份清单与文件哈希通过：$latest_backup"
  else
    fail "最新备份校验失败：$latest_backup"
  fi
  if printf '%s\n' "$backup_json" | grep -Eq '"source_files_missing_at_backup"[[:space:]]*:[[:space:]]*0([,}]|$)'; then
    pass '最新备份包含全部可用原件'
  else
    fail '最新备份存在未纳入的可用原件'
  fi
fi

if [ -f "$runtime/VERSION" ]; then
  pass "正式版本已登记：$(sed -n '1p' "$runtime/VERSION" | tr -d '\r')"
else
  fail '运行目录缺少 VERSION'
fi
if [ -s "$runtime/CURRENT-SOURCE.txt" ]; then
  pass '当前版本源码指针存在'
else
  fail '当前版本源码指针缺失'
fi

offsite_status="$backup_root/.jaos-offsite-status.json"
if [ -f "$offsite_status" ] && grep -Eq '"verified"[[:space:]]*:[[:space:]]*true' "$offsite_status" && grep -Eq '"separate_device"[[:space:]]*:[[:space:]]*true' "$offsite_status"; then
  pass '第二物理介质备份已经独立设备校验'
else
  info '第二物理介质备份尚未完成；系统状态应保持明确告警'
fi

check_flag 'JINGAO_LLM_ENABLED' 'true'
check_l3_generation_flag
check_flag 'JINGAO_EMBEDDING_ENABLED' 'true'
check_flag 'JINGAO_EMBEDDING_L3_ENABLED' 'false'

printf 'RESOURCE_SNAPSHOT\n'
running_ids="$(docker ps -q --filter name="$project_name" || true)"
if [ -n "$running_ids" ]; then
  docker stats \
    --no-stream \
    --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}' \
    $running_ids
else
  info '没有可生成资源快照的运行容器'
fi
df -h /vol1 | tail -1

if [ "$failures" -eq 0 ]; then
  printf 'RESULT|PASS|首版运行验收通过\n'
  exit 0
fi

printf 'RESULT|FAIL|%s 项验收未通过\n' "$failures"
exit 1
