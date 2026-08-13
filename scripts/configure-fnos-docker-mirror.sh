#!/bin/sh
set -eu

config="/etc/docker/daemon.json"
backup="/etc/docker/daemon.json.jingao-20260727.bak"

test -f "$config"
if [ ! -f "$backup" ]; then
  cp -a "$config" "$backup"
fi

python3 - "$config" <<'PY'
import json
import os
import sys
import tempfile

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    config = json.load(handle)

config["registry-mirrors"] = [
    "https://docker.m.daocloud.io",
    "https://registry.hub.docker.com",
]

directory = os.path.dirname(path)
fd, temporary = tempfile.mkstemp(prefix=".daemon.json.", dir=directory)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY

python3 -m json.tool "$config" >/dev/null
systemctl restart docker

ready=0
for _ in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  printf 'Docker did not become ready after restart\n' >&2
  exit 1
fi

docker info 2>/dev/null | sed -n '/Registry Mirrors:/,/Live Restore/p'
