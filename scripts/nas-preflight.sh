#!/bin/sh
# 京奥智库飞牛 NAS 首次上线前只读检查。不会安装软件、修改文件或启动服务。

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE="$PROJECT_DIR/.env"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --env)
      [ "$#" -ge 2 ] || { printf '%s\n' "缺少 --env 参数值"; exit 2; }
      ENV_FILE=$2
      shift 2
      ;;
    --project)
      [ "$#" -ge 2 ] || { printf '%s\n' "缺少 --project 参数值"; exit 2; }
      PROJECT_DIR=$2
      shift 2
      ;;
    *)
      printf '%s\n' "未知参数：$1"
      exit 2
      ;;
  esac
done

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

pass_check() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '[通过] %s\n' "$1"
}

warn_check() {
  WARN_COUNT=$((WARN_COUNT + 1))
  printf '[提醒] %s\n' "$1"
}

fail_check() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf '[失败] %s\n' "$1"
}

env_value() {
  key=$1
  if [ ! -f "$ENV_FILE" ]; then
    return 0
  fi
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r'
}

check_secret() {
  key=$1
  minimum=$2
  value=$(env_value "$key")
  if [ -z "$value" ]; then
    fail_check "$key 尚未填写"
  elif [ "${#value}" -lt "$minimum" ]; then
    fail_check "$key 长度不足 ${minimum} 位"
  elif [ "$value" = "jingao-local" ] || [ "$value" = "password" ]; then
    fail_check "$key 仍为测试默认值"
  else
    pass_check "$key 已设置（内容不显示）"
  fi
}

check_directory() {
  label=$1
  path=$2
  mode=$3
  if [ -z "$path" ]; then
    fail_check "$label 尚未填写"
  elif [ ! -d "$path" ]; then
    fail_check "$label 目录不存在"
  elif [ "$mode" = "read" ] && [ ! -r "$path" ]; then
    fail_check "$label 目录不可读"
  elif [ "$mode" = "write" ] && [ ! -w "$path" ]; then
    fail_check "$label 目录不可写"
  else
    pass_check "$label 目录可用"
  fi
}

printf '%s\n' "京奥智库 NAS 上线前检查"
printf '%s\n' "项目：$PROJECT_DIR"
printf '%s\n' "配置：$ENV_FILE"
printf '%s\n' "----------------------------------------"

if [ "$(uname -s 2>/dev/null || true)" = "Linux" ]; then
  pass_check "运行环境为 Linux"
else
  fail_check "当前不是 Linux/fnOS 环境"
fi

ARCH=$(uname -m 2>/dev/null || true)
case "$ARCH" in
  x86_64|amd64)
    pass_check "CPU 架构为 x86_64"
    ;;
  *)
    fail_check "CPU 架构不是预期的 x86_64"
    ;;
esac

CPU_COUNT=$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '0')
if [ "$CPU_COUNT" -ge 4 ] 2>/dev/null; then
  pass_check "CPU 线程数不少于 4"
else
  warn_check "CPU 线程数少于 4，解析和并发测试可能较慢"
fi

MEM_KB=$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || printf '0')
if [ "$MEM_KB" -ge 15728640 ] 2>/dev/null; then
  pass_check "内存达到 16GB 建议值"
elif [ "$MEM_KB" -ge 7864320 ] 2>/dev/null; then
  warn_check "内存可运行，但低于 16GB 建议值"
else
  fail_check "可用内存低于 8GB 最低值"
fi

if command -v docker >/dev/null 2>&1; then
  pass_check "Docker 命令可用"
  if docker info >/dev/null 2>&1; then
    pass_check "Docker 服务正在运行"
  else
    fail_check "Docker 服务未运行或当前账号无权限"
  fi
  if docker compose version >/dev/null 2>&1; then
    pass_check "Docker Compose 插件可用"
  else
    fail_check "Docker Compose 插件不可用"
  fi
else
  fail_check "未找到 Docker"
fi

if [ -f "$PROJECT_DIR/compose.yaml" ]; then
  pass_check "compose.yaml 已找到"
else
  fail_check "compose.yaml 不存在"
fi

if [ -f "$ENV_FILE" ]; then
  pass_check "正式 .env 配置文件已找到"
else
  fail_check "尚未创建 .env；请从 .env.example 复制后填写"
fi

check_secret "JINGAO_DB_PASSWORD" 16
check_secret "JINGAO_BOOTSTRAP_PASSWORD" 16

KNOWLEDGE_PATH=$(env_value "JINGAO_KNOWLEDGE_PATH")
BACKUP_PATH=$(env_value "JINGAO_BACKUP_PATH")
case "$KNOWLEDGE_PATH" in
  ""|/*) ;;
  *)
    fail_check "JINGAO_KNOWLEDGE_PATH 必须填写 NAS 绝对路径"
    KNOWLEDGE_PATH="$PROJECT_DIR/$KNOWLEDGE_PATH"
    ;;
esac
case "$BACKUP_PATH" in
  ""|/*) ;;
  *) BACKUP_PATH="$PROJECT_DIR/$BACKUP_PATH" ;;
esac
check_directory "知识库原件" "$KNOWLEDGE_PATH" "read"
check_directory "备份" "$BACKUP_PATH" "write"
if [ -n "$KNOWLEDGE_PATH" ]; then
  check_directory \
    "AI入库待审核" \
    "$KNOWLEDGE_PATH/99_AI入库待审核" \
    "read"
fi

if [ -n "$KNOWLEDGE_PATH" ] && [ -d "$KNOWLEDGE_PATH" ]; then
  FREE_KB=$(df -Pk "$KNOWLEDGE_PATH" 2>/dev/null | awk 'NR==2 {print $4}')
  if [ "${FREE_KB:-0}" -ge 104857600 ] 2>/dev/null; then
    pass_check "知识盘剩余空间不少于 100GB"
  else
    warn_check "知识盘剩余空间不足 100GB 或无法读取"
  fi
fi

if [ -n "$KNOWLEDGE_PATH" ] && [ -d "$KNOWLEDGE_PATH" ] \
  && [ -n "$BACKUP_PATH" ] && [ -d "$BACKUP_PATH" ]; then
  KNOWLEDGE_DEVICE=$(df -P "$KNOWLEDGE_PATH" 2>/dev/null | awk 'NR==2 {print $1}')
  BACKUP_DEVICE=$(df -P "$BACKUP_PATH" 2>/dev/null | awk 'NR==2 {print $1}')
  if [ -n "$KNOWLEDGE_DEVICE" ] && [ "$KNOWLEDGE_DEVICE" != "$BACKUP_DEVICE" ]; then
    pass_check "备份目录位于不同存储设备"
  else
    warn_check "备份与知识资料位于同一设备；测试期可接受，不能作为灾难恢复备份"
  fi
fi

EMBEDDING_ENABLED=$(env_value "JINGAO_EMBEDDING_ENABLED")
GATEWAY_KEY=$(env_value "ORIGINGAME_API_KEY")
if [ "$EMBEDDING_ENABLED" = "true" ]; then
  if [ -n "$GATEWAY_KEY" ]; then
    pass_check "语义检索已启用且网关密钥已设置（内容不显示）"
  else
    fail_check "语义检索已启用，但网关密钥为空"
  fi
else
  pass_check "当前保持本地确定性检索，不依赖模型网关"
fi

if command -v docker >/dev/null 2>&1 \
  && docker compose version >/dev/null 2>&1 \
  && [ -f "$ENV_FILE" ] \
  && [ -f "$PROJECT_DIR/compose.yaml" ]; then
  if (
    cd "$PROJECT_DIR" \
      && docker compose --env-file "$ENV_FILE" config --quiet >/dev/null 2>&1
  ); then
    pass_check "Compose 配置可解析"
  else
    fail_check "Compose 配置无法解析，请检查 .env 必填项"
  fi
fi

if command -v ss >/dev/null 2>&1 \
  && ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:|\])3000$'; then
  warn_check "端口 3000 已被占用；若是旧版京奥智库可在升级时处理"
else
  pass_check "端口 3000 当前可用"
fi

warn_check "单盘与 UPS 状态无法由本工具可靠判断；当前试点已接受单盘、无 UPS，正式发布前需再次确认"

printf '%s\n' "----------------------------------------"
printf '汇总：通过 %s，提醒 %s，失败 %s\n' \
  "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  printf '%s\n' "结论：暂不可部署，请先处理失败项。"
  exit 2
fi
if [ "$WARN_COUNT" -gt 0 ]; then
  printf '%s\n' "结论：可进入试点部署，但提醒项不能视为正式发布通过。"
  exit 1
fi
printf '%s\n' "结论：技术预检通过；正式发布仍需业务与权限确认。"
exit 0
