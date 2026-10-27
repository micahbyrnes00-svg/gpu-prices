#!/usr/bin/env bash
# Pi helper. Usage: bash p.sh disks | format | vscode | web | status
set -uo pipefail
cd "$(dirname "$0")"

root_disk() { lsblk -no PKNAME "$(findmnt -n -o SOURCE /)" 2>/dev/null; }

seagates() {  # whole disks whose model/vendor says Seagate, never the boot disk
  local boot; boot=$(root_disk)
  lsblk -dn -o NAME,TYPE,VENDOR,MODEL | awk -v b="$boot" 'tolower($0) ~ /seagate|st[0-9]+/ && $2=="disk" && $1!=b {print $1}'
}

case "${1:-status}" in
disks)
  echo "Boot disk: /dev/$(root_disk)"
  lsblk -o NAME,SIZE,VENDOR,MODEL,TRAN,FSTYPE,LABEL,MOUNTPOINTS
  echo "Seagate disks detected: $(seagates | tr '\n' ' ')"
  ;;
format)
  mapfile -t D < <(seagates)
  boot=$(root_disk)
  if [ "${#D[@]}" -ne 2 ]; then echo "Expected 2 Seagate disks, found ${#D[@]}: ${D[*]:-none}. Not formatting."; exit 1; fi
  for d in "${D[@]}"; do [ "$d" = "$boot" ] && { echo "Refusing: $d is the boot disk"; exit 1; }; done
  echo "Will ERASE: ${D[*]} (boot disk $boot is untouched)"; sleep 3
  i=1
  for d in "${D[@]}"; do
    dev=/dev/$d
    sudo umount "${dev}"* 2>/dev/null
    sudo wipefs -a "${dev}"* >/dev/null
    sudo parted -s "$dev" mklabel gpt mkpart seagate$i ext4 0% 100%
    sudo partprobe "$dev"; sleep 2
    part=$(lsblk -lnpo NAME "$dev" | sed -n 2p)
    sudo mkfs.ext4 -F -q -L seagate$i "$part"
    uuid=$(sudo blkid -s UUID -o value "$part")
    sudo mkdir -p /mnt/seagate$i
    sudo sed -i "\|/mnt/seagate$i |d" /etc/fstab
    echo "UUID=$uuid /mnt/seagate$i ext4 defaults,nofail,noatime,x-systemd.device-timeout=10 0 2" | sudo tee -a /etc/fstab >/dev/null
    i=$((i+1))
  done
  sudo systemctl daemon-reload; sudo mount -a
  sudo mkdir -p /mnt/seagate1/gpu-prices /mnt/seagate2/backups
  sudo chown -R pi:pi /mnt/seagate1 /mnt/seagate2
  df -h /mnt/seagate1 /mnt/seagate2
  ;;
vscode)  # forget MatrixVMS in VS Code (files and service are left alone)
  pkill -f /usr/share/code/code 2>/dev/null; sleep 1
  python3 - <<'EOF'
import json, os, sqlite3
base = os.path.expanduser("~/.config/Code/User/globalStorage")
db = os.path.join(base, "state.vscdb")
if os.path.exists(db):
    con = sqlite3.connect(db)
    row = con.execute("SELECT value FROM ItemTable WHERE key='history.recentlyOpenedPathsList'").fetchone()
    if row:
        data = json.loads(row[0])
        data["entries"] = [e for e in data.get("entries", []) if "MatrixVMS" not in json.dumps(e)]
        con.execute("UPDATE ItemTable SET value=? WHERE key='history.recentlyOpenedPathsList'", (json.dumps(data),))
        con.commit()
st = os.path.join(base, "storage.json")
if os.path.exists(st):
    s = json.load(open(st))
    for k in ("windowsState", "backupWorkspaces"):
        if k in s:
            s[k] = json.loads(json.dumps(s[k]).replace("MatrixVMS", "__removed__")) if "MatrixVMS" not in json.dumps(s[k]) else {}
    json.dump(s, open(st, "w"))
print("MatrixVMS removed from VS Code recent/restore lists")
EOF
  ;;
web)  # serve the real site (/home/pi/site) if built, else the demo; localhost only when public via Funnel
  src=/home/pi/site; [ -f $src/index.html ] || src=/home/pi/gpu-prices/demo-site
  bind=${2:-0.0.0.0}
  docker rm -f gpu-prices-web >/dev/null 2>&1
  docker run -d --name gpu-prices-web --restart unless-stopped -p $bind:8088:80 \
    -v $src:/usr/share/caddy:ro caddy:2-alpine >/dev/null && echo "Serving $src on $bind:8088"
  ;;
prep)  # everything that doesn't need eBay keys
  bash "$0" setenv PUBLISH pi >/dev/null; bash "$0" setenv SITE_DIR /home/pi/site >/dev/null
  bash "$0" setenv DATA_DIR /home/pi/gpu-prices/data >/dev/null
  mkdir -p /home/pi/site /home/pi/gpu-prices/data
  sudo cp deploy/gpu-prices.service deploy/gpu-prices.timer /etc/systemd/system/ && sudo systemctl daemon-reload
  echo "timer installed (not enabled until golive)"
  echo "--- AI CLI:"; if command -v claude >/dev/null; then claude --version; echo 'Reply with exactly: ok' | timeout 90 claude -p 2>&1 | tail -2; else echo "claude not found"; fi
  echo "--- Tailscale:"; tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'
  echo "--- .env:"; grep -E '^(PUBLISH|SITE_DIR|DATA_DIR|EPN_CAMPAIGN_ID|AI_CMD)=' .env
  ;;
keys)  # prompt for eBay production keys (typed by you, never shown) and test them
  read -rp "eBay App ID (Client ID): " cid
  read -rsp "eBay Cert ID (Client Secret, hidden): " csec; echo
  bash "$0" setenv EBAY_CLIENT_ID "$cid" >/dev/null; bash "$0" setenv EBAY_CLIENT_SECRET "$csec" >/dev/null
  unset csec
  python3 -c 'from tracker.ebay import EbayClient; c=EbayClient(); c._get_token(); r=c.search("RTX 3080","27386",200,700,pages=1); print("eBay OK:", len(r), "listings for RTX 3080")' \
    || echo "Key test FAILED - check the keys are the Production set"
  ;;
golive)  # first real build, serve it, publish through Tailscale Funnel, enable 6-hour updates
  grep -q '^EBAY_CLIENT_SECRET=.\+' .env || { echo "Run: bash p.sh keys  first"; exit 1; }
  dns=$(tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
  bash "$0" setenv SITE_URL "https://$dns"
  bash deploy/update.sh || exit 1
  bash "$0" web 127.0.0.1
  sudo tailscale funnel --bg 8088 || { echo "Funnel not allowed yet: enable HTTPS + Funnel in the Tailscale admin console (link above), then rerun golive."; exit 1; }
  sudo systemctl enable --now gpu-prices.timer
  echo "LIVE: https://$dns"; systemctl list-timers gpu-prices.timer --no-pager | head -2
  ;;
scale)  # resize the headless VNC desktop to fit the TigerVNC window; persists via kanshi
  mode=${2:-1504x846}
  out=$(wlr-randr | awk 'NR==1{print $1}')
  wlr-randr --output "$out" --custom-mode "$mode" && echo "Set $out to $mode"
  mkdir -p ~/.config/kanshi
  printf 'profile {\n  output %s mode --custom %s\n}\n' "$out" "$mode" > ~/.config/kanshi/config
  ;;
migrate)  # copy the running OS onto the single attached Seagate (ERASES it)
  mapfile -t D < <(seagates)
  boot=$(root_disk)
  [ "${#D[@]}" -eq 1 ] || { echo "Need exactly 1 Seagate attached, found ${#D[@]}: ${D[*]:-none}"; exit 1; }
  t=/dev/${D[0]}
  [ "${D[0]}" != "$boot" ] || { echo "Refusing: target is the boot disk"; exit 1; }
  size=$(lsblk -bdno SIZE "$t")
  [ "$size" -lt 2199023255552 ] && label=msdos || label=gpt   # MBR up to 2 TiB, GPT beyond
  echo "Target: $t ($(lsblk -dno SIZE,MODEL "$t"), $label). Boot disk $boot is NOT touched."
  echo "Erasing $t in 10 seconds. Ctrl+C to cancel."; sleep 10
  sudo apt-get install -y -qq parted rsync dosfstools >/dev/null
  sudo umount "$t"* 2>/dev/null
  sudo wipefs -a "$t"* >/dev/null
  sudo parted -s "$t" mklabel $label mkpart primary fat32 4MiB 516MiB mkpart primary ext4 516MiB 100%
  [ $label = msdos ] && sudo parted -s "$t" set 1 boot on
  sudo partprobe "$t"; sleep 3
  p1=$(lsblk -lnpo NAME "$t" | sed -n 2p); p2=$(lsblk -lnpo NAME "$t" | sed -n 3p)
  sudo mkfs.vfat -F 32 -n SGBOOT "$p1" >/dev/null
  sudo mkfs.ext4 -F -q -L sgroot "$p2"
  sudo mkdir -p /mnt/newroot
  sudo mount "$p2" /mnt/newroot
  sudo mkdir -p /mnt/newroot/boot/firmware
  sudo mount "$p1" /mnt/newroot/boot/firmware
  echo "Copying system (several minutes)..."
  sudo rsync -aHAXx --info=progress2 --exclude={"/proc/*","/sys/*","/dev/*","/run/*","/tmp/*","/mnt/*","/media/*","/lost+found","/var/cache/apt/archives/*.deb","/home/*/.cache/*"} / /mnt/newroot/
  sudo rsync -rt /boot/firmware/ /mnt/newroot/boot/firmware/
  old1=$(findmnt -no PARTUUID /boot/firmware); old2=$(findmnt -no PARTUUID /)
  new1=$(sudo blkid -s PARTUUID -o value "$p1"); new2=$(sudo blkid -s PARTUUID -o value "$p2")
  sudo sed -i "s/$old1/$new1/; s/$old2/$new2/" /mnt/newroot/etc/fstab
  sudo sed -i "s/root=PARTUUID=[^ ]*/root=PARTUUID=$new2/" /mnt/newroot/boot/firmware/cmdline.txt
  echo "--- new fstab:"; grep -v '^#' /mnt/newroot/etc/fstab | grep -v '^$'
  echo "--- new cmdline:"; cat /mnt/newroot/boot/firmware/cmdline.txt
  sudo umount /mnt/newroot/boot/firmware /mnt/newroot
  echo "DONE. Shut down, unplug the SanDisk, power on: it will boot from the Seagate."
  ;;
wipeold)  # after booting from the Seagate: erase the old SanDisk OS stick as a plain exFAT drive
  [ "$(findmnt -no LABEL /)" = sgroot ] || { echo "Not booted from the Seagate yet (root=$(findmnt -no SOURCE /)). Refusing."; exit 1; }
  s=$(lsblk -dn -o NAME,MODEL | awk 'tolower($0) ~ /sandisk/ {print $1}')
  [ -n "$s" ] && [ "$s" != "$(root_disk)" ] || { echo "SanDisk stick not found or is the boot disk. Refusing."; exit 1; }
  echo "Erasing /dev/$s ($(lsblk -dno SIZE,MODEL /dev/$s)) in 10 seconds. Ctrl+C to cancel."; sleep 10
  sudo apt-get install -y -qq exfatprogs >/dev/null
  sudo umount /dev/$s* 2>/dev/null; sudo wipefs -a /dev/$s* >/dev/null
  sudo parted -s /dev/$s mklabel msdos mkpart primary 1MiB 100%; sudo partprobe /dev/$s; sleep 2
  sudo mkfs.exfat -L USB "$(lsblk -lnpo NAME /dev/$s | sed -n 2p)" >/dev/null && echo "SanDisk is now an empty exFAT drive labelled USB."
  ;;
sdbackup)  # after booting from the Seagate: erase the SD card and store a compressed backup of the OS on it
  [ "$(findmnt -no LABEL /)" = sgroot ] || { echo "Not booted from the Seagate yet. Refusing."; exit 1; }
  sd=/dev/mmcblk0; [ -b $sd ] || { echo "No SD card"; exit 1; }
  echo "Erasing SD card $sd ($(lsblk -dno SIZE $sd)) in 10 seconds. Ctrl+C to cancel."; sleep 10
  sudo apt-get install -y -qq exfatprogs zstd >/dev/null
  sudo umount ${sd}p* 2>/dev/null; sudo wipefs -a ${sd}* >/dev/null
  sudo parted -s $sd mklabel msdos mkpart primary 1MiB 100%; sudo partprobe $sd; sleep 2
  sudo mkfs.exfat -L PIBACKUP ${sd}p1 >/dev/null
  sudo mkdir -p /mnt/sdbackup && sudo mount ${sd}p1 /mnt/sdbackup
  f=/mnt/sdbackup/micahbyrnespi-$(date +%F).tar.zst
  echo "Writing $f (10-30 min)..."
  sudo tar --one-file-system -cpf - --exclude='./var/cache/apt/archives/*.deb' --exclude='./home/*/.cache' \
    --exclude='./var/lib/docker/overlay2' -C / . 2>/dev/null | zstd -T0 -6 -q -o "$f"
  sudo tar -cpf - -C /boot/firmware . | zstd -T0 -q -o "${f%.tar.zst}-boot.tar.zst"
  sudo cp /boot/firmware/cmdline.txt /etc/fstab /mnt/sdbackup/ 2>/dev/null
  printf 'Restore: partition a drive (FAT32 boot + ext4 root), extract root with\n  sudo tar -I zstd -xpf %s -C /mnt/newroot\nand the -boot archive into /mnt/newroot/boot/firmware, and fix PARTUUIDs in cmdline.txt and etc/fstab.\n' "$(basename $f)" | sudo tee /mnt/sdbackup/RESTORE.txt >/dev/null
  ls -lh /mnt/sdbackup; sudo umount /mnt/sdbackup
  ;;
setenv)  # setenv KEY VALUE -> writes into .env (created from .env.example), chmod 600
  [ -f .env ] || cp .env.example .env
  chmod 600 .env
  sed -i '/^[a-z][a-z]*=/d' .env   # drop lowercase junk keys from VNC typing
  k=$(echo "$2" | tr a-z A-Z | tr -d '_')   # VNC can't type _ or capitals: accept "epncampaignid"
  case $k in EPNCAMPAIGNID) k=EPN_CAMPAIGN_ID;; EBAYCLIENTID) k=EBAY_CLIENT_ID;; EBAYCLIENTSECRET) k=EBAY_CLIENT_SECRET;; *) k=$2;; esac
  set -- "$1" "$k" "$3"
  if grep -q "^$2=" .env; then sed -i "s|^$2=.*|$2=$3|" .env; else echo "$2=$3" >> .env; fi
  grep "^$2=" .env | sed -E 's/(SECRET=).+/\1*****/'
  ;;
cloudsetup)  # one-time: connect Google Drive (browser sign-in) + encrypted remote + weekly timer
  sudo apt-get install -y -qq rclone zstd >/dev/null
  rclone listremotes | grep -q '^gdrive:' || rclone config create gdrive drive scope=drive.file
  if ! rclone listremotes | grep -q '^gcrypt:'; then
    while :; do
      read -rsp "Choose a backup encryption password: " p1; echo
      read -rsp "Type it again: " p2; echo
      [ -n "$p1" ] && [ "$p1" = "$p2" ] && break; echo "Did not match, try again."
    done
    rclone config create gcrypt crypt remote=gdrive:pi-backups filename_encryption=standard password="$p1" --obscure >/dev/null
    unset p1 p2; echo "Encrypted remote created. SAVE THAT PASSWORD in your password manager."
  fi
  sudo tee /etc/systemd/system/pi-cloud-backup.service >/dev/null <<EOF
[Unit]
Description=Encrypted OS backup to Google Drive
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
ExecStart=/bin/bash /home/pi/gpu-prices/p.sh cloudrun
Nice=15
IOSchedulingClass=idle
EOF
  sudo tee /etc/systemd/system/pi-cloud-backup.timer >/dev/null <<EOF
[Unit]
Description=Weekly encrypted OS backup to Google Drive
[Timer]
OnCalendar=Sun *-*-* 03:30:00
Persistent=true
RandomizedDelaySec=30min
[Install]
WantedBy=timers.target
EOF
  sudo systemctl daemon-reload && sudo systemctl enable --now pi-cloud-backup.timer
  systemctl list-timers pi-cloud-backup.timer --no-pager | head -2
  ;;
cloudrun)  # make one backup now (runs as root via timer, or with sudo)
  conf=/home/pi/.config/rclone/rclone.conf
  name=micahbyrnespi-$(date +%F).tar.zst
  echo "Uploading $name (encrypted)..."
  tar --one-file-system -cpf - --exclude='./var/cache/apt/archives/*.deb' --exclude='./home/*/.cache' \
      --exclude='./var/lib/docker/overlay2' --exclude='./tmp/*' --exclude='./swap*' -C / . 2>/dev/null \
    | zstd -T0 -6 -q | rclone --config "$conf" rcat "gcrypt:$name"
  tar -cpf - -C /boot/firmware . | zstd -q | rclone --config "$conf" rcat "gcrypt:${name%.tar.zst}-boot.tar.zst"
  # keep the 4 newest system backups
  rclone --config "$conf" lsf gcrypt: --files-only | grep -v -- -boot | sort | head -n -4 | while read -r old; do
    rclone --config "$conf" deletefile "gcrypt:$old"; rclone --config "$conf" deletefile "gcrypt:${old%.tar.zst}-boot.tar.zst"
  done
  rclone --config "$conf" lsl gcrypt:
  ;;
monitor)  # live stats web app (Glances), reachable only on your tailnet over HTTPS
  docker rm -f glances >/dev/null 2>&1
  docker run -d --name glances --restart unless-stopped --pid host -p 127.0.0.1:61208:61208 \
    -e GLANCES_OPT="-w --disable-webui-password" -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -v /etc/os-release:/etc/os-release:ro nicolargo/glances:latest-full >/dev/null || exit 1
  sleep 5
  sudo tailscale serve --bg --https=8443 http://127.0.0.1:61208 >/dev/null
  dns=$(tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
  echo "Live stats (tailnet only): https://$dns:8443"
  tailscale serve status
  ;;
stats)  # health snapshot
  echo "== $(hostname)  $(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')"
  uptime -p; echo "load: $(cut -d' ' -f1-3 /proc/loadavg)  cores: $(nproc)"
  echo "temp: $(vcgencmd measure_temp 2>/dev/null | cut -d= -f2)  clock: $(( $(vcgencmd measure_clock arm 2>/dev/null | cut -d= -f2) / 1000000 )) MHz  power: $(vcgencmd get_throttled 2>/dev/null)"
  free -h | sed -n '1,3p'
  df -h / /boot/firmware | sed 1d | awk '{print "disk " $6 ": " $3 " used of " $2 " (" $5 ")"}'
  echo "== top CPU"; ps -eo pid,pcpu,pmem,etime,comm --sort=-pcpu | head -8
  echo "== top memory"; ps -eo pid,pmem,rss,comm --sort=-rss | head -6 | awk 'NR==1{print;next}{printf "%s %s %dMB %s\n",$1,$2,$3/1024,$4}'
  echo "== containers"; docker stats --no-stream --format '{{.Name}}  cpu {{.CPUPerc}}  mem {{.MemUsage}}' 2>/dev/null
  echo "== services"; systemctl --failed --no-legend | head; systemctl list-timers --no-pager | grep -E 'gpu-prices|pi-cloud' 
  pgrep -af "rclone|zstd" >/dev/null && echo "cloud backup upload running"
  ;;
diag)  # why did USB disks drop? power + kernel USB log
  vcgencmd get_throttled 2>/dev/null
  lsusb
  journalctl -k -b --no-pager -o cat | grep -iE "under-?voltage|over-?current|disconnect|sd[a-z]:|sd [0-9]|seagate|reset (high|super)speed" | tail -25
  ;;
status)
  hostname; uptime
  systemctl --failed --no-legend
  df -h / /mnt/seagate1 /mnt/seagate2 2>/dev/null
  sudo docker ps --format '{{.Names}} {{.Status}}'
  ;;
esac
