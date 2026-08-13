#!/bin/sh
set -eu

inbox='/vol1/@team/京奥智库/01_知识资料/99_AI入库待审核'

install -o JADJ -g Users -m 0644 \
  /home/JADJ/synthetic-ingest-a.txt \
  "$inbox/synthetic-ingest-a.txt"
install -o JADJ -g Users -m 0644 \
  /home/JADJ/synthetic-ingest-b.txt \
  "$inbox/synthetic-ingest-b.txt"

# Make the files immediately eligible for the scanner's settle-time check.
touch -d '5 minutes ago' \
  "$inbox/synthetic-ingest-a.txt" \
  "$inbox/synthetic-ingest-b.txt"

hash_a="$(sha256sum "$inbox/synthetic-ingest-a.txt" | cut -d ' ' -f 1)"
hash_b="$(sha256sum "$inbox/synthetic-ingest-b.txt" | cut -d ' ' -f 1)"

if [ "$hash_a" != "$hash_b" ]; then
  echo "Synthetic fixture hashes differ" >&2
  exit 1
fi

printf 'SYNTHETIC_FIXTURES_STAGED=1\n'
printf 'IDENTICAL_HASH_CONFIRMED=1\n'
