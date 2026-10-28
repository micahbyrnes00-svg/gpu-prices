#!/bin/bash
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo.'; exit 1; }
[ "$(hostname)" = themachine ]
[ "$(findmnt -n -o UUID --mountpoint /srv/backups)" = dcc7b6ea-5712-4599-a038-034104c29103 ]
[ "$(findmnt -n -o UUID --mountpoint /srv/data)" = d7005f94-ab26-4575-a511-c84f7a1526a3 ]
source_dir=$(cd "$(dirname "$0")" && pwd)
test -s "$source_dir/drive_health.py"
test -s "$source_dir/backup.sh"
apt-get update
apt-get install -y smartmontools restic
install -d -m 755 /usr/local/lib/orbit /var/lib/orbit-drive-health /var/lib/orbit-backup
install -o root -g root -m 755 "$source_dir/drive_health.py" /usr/local/lib/orbit/drive_health.py
install -o root -g root -m 700 "$source_dir/backup.sh" /usr/local/lib/orbit/backup.sh
install -d -m 700 /etc/orbit-backup
if [ ! -s /etc/orbit-backup/password ]; then
    [ ! -e /srv/backups/themachine/restic/config ] || { echo 'STOP: existing repository needs its original password.'; exit 1; }
    (umask 077; head -c 48 /dev/urandom | base64 > /etc/orbit-backup/password)
fi
cat > /etc/systemd/system/orbit-drive-health.service <<'EOF'
[Unit]
Description=Orbit read-only SMART drive health

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/orbit/drive_health.py
TimeoutStartSec=150
Nice=15
EOF
cat > /etc/systemd/system/orbit-drive-health.timer <<'EOF'
[Unit]
Description=Refresh Orbit drive health every ten minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/orbit-backup.service <<'EOF'
[Unit]
Description=Orbit versioned local backup of themachine
RequiresMountsFor=/srv/data /srv/backups
[Service]
Type=oneshot
ExecStart=/usr/local/lib/orbit/backup.sh
Nice=19
IOSchedulingClass=idle
CPUQuota=75%
EOF
cat > /etc/systemd/system/orbit-backup.timer <<'EOF'
[Unit]
Description=Nightly Orbit backup
[Timer]
OnCalendar=*-*-* 03:15:00 America/Detroit
RandomizedDelaySec=15min
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now orbit-drive-health.timer orbit-backup.timer
systemctl start orbit-drive-health.service
systemctl start --no-block orbit-backup.service
echo 'DRIVE HEALTH ACTIVE; FIRST BACKUP STARTED'
cat /var/lib/orbit-drive-health/status.json
echo
echo 'Backup recovery password: /etc/orbit-backup/password. Save it privately off this machine.'
echo 'Do not paste the recovery password into chat.'
