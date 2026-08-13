#!/bin/sh
set -eu

log=/tmp/jingao-postdeploy-backup.log
exit_file=/tmp/jingao-postdeploy-backup.exit
container=jingao-copilot-backup-1

case "${1:-status}" in
  start)
    rm -f "$log" "$exit_file"
    nohup sh -c "docker exec '$container' python -m app.cli backup > '$log' 2>&1; printf '%s\n' \"\$?\" > '$exit_file'" >/dev/null 2>&1 &
    echo 'backup-started'
    ;;
  status)
    if [ -f "$log" ]; then
      tail -n 30 "$log"
    fi
    if [ -f "$exit_file" ]; then
      printf 'BACKUP_EXIT='
      cat "$exit_file"
    else
      echo 'BACKUP_EXIT=RUNNING'
    fi
    ;;
  *)
    echo 'usage: run-postdeploy-backup.sh {start|status}' >&2
    exit 2
    ;;
esac
