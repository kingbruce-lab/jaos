#!/bin/sh
set -eu

runtime_dir="/vol1/@team/京奥智库/00_部署/jingao-runtime"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
source_dir="$(dirname "$script_dir")"
knowledge_dir="/vol1/@team/京奥智库/01_知识资料"
backup_dir="/vol1/@team/京奥智库/02_备份"

test -d "$runtime_dir"
test -d "$source_dir/agent"
test -d "$knowledge_dir/99_AI入库待审核"
test -d "$backup_dir"
test -f "$source_dir/compose.yaml"

if [ -f "$source_dir/SHA256SUMS" ]; then
  checksum_file="$(mktemp)"
  trap 'rm -f "$checksum_file"' EXIT HUP INT TERM
  tr -d '\r' < "$source_dir/SHA256SUMS" > "$checksum_file"
  (
    cd "$source_dir"
    sha256sum -c "$checksum_file" >/dev/null
  )
fi

current_source=""
if [ -f "$runtime_dir/CURRENT-SOURCE.txt" ]; then
  current_source="$(sed -n '1p' "$runtime_dir/CURRENT-SOURCE.txt" | tr -d '\r')"
fi
current_version="$(sed -n '1p' "$runtime_dir/VERSION" 2>/dev/null | tr -d '\r')"
source_version="$(sed -n '1p' "$source_dir/VERSION" 2>/dev/null | tr -d '\r')"
if [ -n "$current_source" ] &&
   [ "$current_source" != "$source_dir" ] &&
   { [ -z "$source_version" ] || [ "$current_version" != "$source_version" ] || [ ! -s "$runtime_dir/PREVIOUS-SOURCE.txt" ]; }; then
  printf '%s\n' "$current_source" > "$runtime_dir/PREVIOUS-SOURCE.txt.new"
  chown root:root "$runtime_dir/PREVIOUS-SOURCE.txt.new"
  chmod 600 "$runtime_dir/PREVIOUS-SOURCE.txt.new"
  mv -f "$runtime_dir/PREVIOUS-SOURCE.txt.new" "$runtime_dir/PREVIOUS-SOURCE.txt"
fi

install -m 600 -o root -g root "$source_dir/compose.yaml" "$runtime_dir/docker-compose.yml"
for release_file in DEPLOYMENT-PACKAGE.txt VERSION SHA256SUMS; do
  if [ -f "$source_dir/$release_file" ]; then
    install -m 600 -o root -g root \
      "$source_dir/$release_file" \
      "$runtime_dir/$release_file"
  fi
done
for runtime_script in manage-nas-runtime.sh verify-nas-runtime.sh sync-offsite-backup.sh install-offsite-backup-timer.sh; do
  if [ -f "$source_dir/scripts/$runtime_script" ]; then
    target_name="$(printf '%s' "$runtime_script" | sed 's/-nas-runtime//')"
    install -m 700 -o root -g root \
      "$source_dir/scripts/$runtime_script" \
      "$runtime_dir/$target_name"
  fi
done

umask 077
printf '%s\n' "$source_dir" > "$runtime_dir/CURRENT-SOURCE.txt.new"
chown root:root "$runtime_dir/CURRENT-SOURCE.txt.new"
chmod 600 "$runtime_dir/CURRENT-SOURCE.txt.new"
mv -f "$runtime_dir/CURRENT-SOURCE.txt.new" "$runtime_dir/CURRENT-SOURCE.txt"

sed -i \
  -e "s|context: ./agent|context: \"$source_dir/agent\"|g" \
  -e "s|context: \\.$|context: \"$source_dir\"|g" \
  "$runtime_dir/docker-compose.yml"

founder_secret=""
if [ ! -f "$runtime_dir/.env" ]; then
  db_secret="$(openssl rand -hex 32)"
  founder_secret="$(openssl rand -hex 12)Aa7!"

  umask 077
  {
    printf 'JINGAO_DB_PASSWORD=%s\n' "$db_secret"
    printf 'JINGAO_BOOTSTRAP_PASSWORD=%s\n' "$founder_secret"
    printf 'JINGAO_KNOWLEDGE_PATH=%s\n' "$knowledge_dir"
    printf 'JINGAO_BACKUP_PATH=%s\n' "$backup_dir"
    printf 'JINGAO_OFFSITE_BACKUP_PATH=%s\n' ""
    printf 'JINGAO_OFFSITE_BACKUP_MAX_AGE_SECONDS=%s\n' "604800"
    printf 'JINGAO_WEB_ORIGINS=%s\n' "http://192.168.2.53:3000,http://jadj-nas.local:3000,http://localhost:3000,https://knowledge.jingao.club"
    printf 'JINGAO_WEB_HOSTS=%s\n' "localhost,127.0.0.1,web,jadj-nas.local,192.168.2.53,knowledge.jingao.club"
    printf 'JINGAO_WEB_MAX_REQUEST_BODY_BYTES=%s\n' "2147483648"
    printf 'JINGAO_WEB_PORT=%s\n' "3000"
    printf 'JINGAO_LLM_ENABLED=%s\n' "true"
    printf 'JINGAO_LLM_L3_ENABLED=%s\n' "false"
    printf 'JINGAO_EMBEDDING_ENABLED=%s\n' "true"
    printf 'JINGAO_EMBEDDING_L3_ENABLED=%s\n' "false"
  } > "$runtime_dir/.env.new"
  chown root:root "$runtime_dir/.env.new"
  chmod 600 "$runtime_dir/.env.new"
  mv -f "$runtime_dir/.env.new" "$runtime_dir/.env"
fi

ensure_env_default() {
  key="$1"
  value="$2"
  if ! grep -q "^${key}=" "$runtime_dir/.env"; then
    printf '%s=%s\n' "$key" "$value" >> "$runtime_dir/.env"
  fi
}

ensure_env_default JINGAO_OFFSITE_BACKUP_PATH ""
ensure_env_default JINGAO_OFFSITE_BACKUP_MAX_AGE_SECONDS "604800"
chown root:root "$runtime_dir/.env"
chmod 600 "$runtime_dir/.env"

cd "$runtime_dir"
docker compose \
  -p jingao-copilot \
  --env-file .env \
  -f docker-compose.yml \
  config --quiet

version="$(test -f "$source_dir/VERSION" && sed -n '1p' "$source_dir/VERSION" | tr -d '\r' || printf 'unversioned')"
git_commit="$(sed -n 's/^Git commit: //p' "$source_dir/DEPLOYMENT-PACKAGE.txt" 2>/dev/null | head -1 | tr -d '\r')"
printf '%s|version=%s|commit=%s|source=%s|previous=%s\n' \
  "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  "$version" \
  "${git_commit:-unknown}" \
  "$source_dir" \
  "${current_source:-none}" \
  >> "$runtime_dir/RELEASE-HISTORY.log"
chown root:root "$runtime_dir/RELEASE-HISTORY.log"
chmod 600 "$runtime_dir/RELEASE-HISTORY.log"

if [ -x "$runtime_dir/install-offsite-backup-timer.sh" ]; then
  "$runtime_dir/install-offsite-backup-timer.sh" "$runtime_dir" >/dev/null
  "$runtime_dir/sync-offsite-backup.sh" --env-file "$runtime_dir/.env" >/dev/null 2>&1 || true
fi

if [ -n "$founder_secret" ]; then
  printf 'FOUNDER_TEMP_PASSWORD=%s\n' "$founder_secret"
else
  printf '%s\n' "EXISTING_ENV_PRESERVED"
fi
printf 'DEPLOYED_VERSION=%s\n' "$version"
printf 'CURRENT_SOURCE=%s\n' "$source_dir"
printf 'PREVIOUS_SOURCE=%s\n' "${current_source:-none}"
