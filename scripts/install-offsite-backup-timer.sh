#!/bin/sh
set -eu

runtime_dir="${1:-/vol1/@team/京奥智库/00_部署/jingao-runtime}"
service_file='/etc/systemd/system/jaos-offsite-backup.service'
timer_file='/etc/systemd/system/jaos-offsite-backup.timer'

if ! command -v systemctl >/dev/null 2>&1; then
  printf 'systemd-unavailable; run %s/sync-offsite-backup.sh manually\n' "$runtime_dir"
  exit 0
fi

cat > "$service_file" <<EOF
[Unit]
Description=JAOS second physical media backup verification
After=docker.service

[Service]
Type=oneshot
ExecStart=$runtime_dir/sync-offsite-backup.sh --env-file $runtime_dir/.env
EOF

cat > "$timer_file" <<EOF
[Unit]
Description=Run JAOS second-media backup daily

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
RandomizedDelaySec=900

[Install]
WantedBy=timers.target
EOF

chmod 644 "$service_file" "$timer_file"
systemctl daemon-reload
systemctl enable --now jaos-offsite-backup.timer >/dev/null
printf 'OFFSITE_BACKUP_TIMER=enabled\n'
