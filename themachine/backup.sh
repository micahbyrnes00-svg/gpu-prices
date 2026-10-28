#!/bin/bash
set -euo pipefail
export RESTIC_REPOSITORY=/srv/backups/themachine/restic
export RESTIC_PASSWORD_FILE=/etc/orbit-backup/password
export RESTIC_CACHE_DIR=/var/cache/orbit-backup
exec 9>/run/lock/orbit-backup.lock
flock -n 9 || exit 0

record() {
    python3 - "$1" <<'PY'
import json,os,sys,time
from pathlib import Path
p=Path('/var/lib/orbit-backup/status.json')
try:
    data=json.loads(p.read_text())
except (OSError,ValueError):
    data={}
data.update(configured=True,status=sys.argv[1],lastAttempt=time.time())
if sys.argv[1]=='success':
    data['lastSuccess']=time.time()
p.parent.mkdir(parents=True,exist_ok=True)
t=p.with_suffix('.new')
t.write_text(json.dumps(data)); t.chmod(0o644); os.replace(t,p)
PY
}
trap 'record failed' ERR
[ "$(findmnt -n -o UUID --mountpoint /srv/backups)" = dcc7b6ea-5712-4599-a038-034104c29103 ]
[ "$(findmnt -n -o UUID --mountpoint /srv/data)" = d7005f94-ab26-4575-a511-c84f7a1526a3 ]
record running
if [ ! -f "$RESTIC_REPOSITORY/config" ]; then
    restic init
fi
restic backup --host themachine --tag orbit --one-file-system \
    --exclude /dev --exclude /proc --exclude /sys --exclude /run \
    --exclude /tmp --exclude /mnt --exclude /media --exclude /srv/backups \
    --exclude /swap.img --exclude /var/cache --exclude /var/tmp \
    --exclude '/home/*/.cache' --exclude /root/.cache \
    / /boot /boot/efi /srv/data
restic forget --host themachine --tag orbit --keep-daily 7 --keep-weekly 4 --keep-monthly 3
if [ "$(date +%u)" = 7 ]; then
    restic prune
    restic check
fi
record success
