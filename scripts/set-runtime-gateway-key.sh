#!/bin/sh
set -eu

runtime="${1:-/tmp/jingao-runtime}"
key_file="${2:-/tmp/jingao-gateway.key}"
env_file="$runtime/.env"

test -f "$env_file"
test -f "$key_file"

gateway_key="$(tr -d '\r\n' < "$key_file")"
case "$gateway_key" in
  sk-*) ;;
  *) echo 'invalid gateway key format' >&2; exit 1 ;;
esac

temporary="$(mktemp "$runtime/.env.gateway.XXXXXX")"
trap 'rm -f "$temporary"' EXIT
awk '!/^ORIGINGAME_API_KEY=/' "$env_file" > "$temporary"
printf 'ORIGINGAME_API_KEY=%s\n' "$gateway_key" >> "$temporary"
chmod 600 "$temporary"
mv "$temporary" "$env_file"
rm -f "$key_file"
trap - EXIT
echo 'gateway key installed'
