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
  mkdir -p /home/pi/site-logs
  rapid=$(grep -E '^RAPIDAPI_PROXY_SECRET=' .env 2>/dev/null | tail -1 | cut -d= -f2-)
  if ! docker run --rm -e RAPIDAPI_PROXY_SECRET="${rapid:-x}" -v /home/pi/gpu-prices/deploy/Caddyfile:/etc/caddy/Caddyfile:ro \
       caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile >/tmp/caddy-validate.log 2>&1; then
    echo "Caddyfile is invalid; keeping the current web server running. Details: /tmp/caddy-validate.log"; tail -3 /tmp/caddy-validate.log; exit 1
  fi
  docker rm -f gpu-prices-web >/dev/null 2>&1
  docker run -d --name gpu-prices-web --restart unless-stopped -p $bind:8088:80 -e RAPIDAPI_PROXY_SECRET="$rapid" \
    -v $src:/usr/share/caddy:ro -v /home/pi/gpu-prices/deploy/Caddyfile:/etc/caddy/Caddyfile:ro \
    -v /home/pi/site-logs:/logs caddy:2-alpine >/dev/null && echo "Serving $src on $bind:8088 (access log: /home/pi/site-logs)"
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
golive)  # first real build with live eBay data, serve it, enable 6-hour updates
  grep -q '^EBAY_CLIENT_SECRET=.\+' .env || { echo "Run: bash p.sh keys  first"; exit 1; }
  site=$(grep -E '^SITE_URL=' .env | tail -1 | cut -d= -f2-)
  if systemctl is-active --quiet cloudflared && [ -n "$site" ] && ! echo "$site" | grep -q 'ts.net\|github.io'; then
    via="Cloudflare ($site)"
  else
    dns=$(tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
    site="https://$dns"; bash "$0" setenv SITE_URL "$site" >/dev/null; via="Tailscale Funnel"
  fi
  echo "Collecting live prices for every model (first run takes 5-15 minutes)..."
  bash deploy/update.sh || exit 1
  bash "$0" web 127.0.0.1
  [ "$via" = "Tailscale Funnel" ] && { sudo tailscale funnel --bg 8088 || { echo "Funnel not allowed yet."; exit 1; }; }
  sudo systemctl enable --now gpu-prices.timer
  sudo -n /usr/bin/systemctl restart picommand.service 2>/dev/null
  echo "LIVE via $via: $site"; systemctl list-timers gpu-prices.timer --no-pager | head -2
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
  case $k in EPNCAMPAIGNID) k=EPN_CAMPAIGN_ID;; EBAYCLIENTID) k=EBAY_CLIENT_ID;; EBAYCLIENTSECRET) k=EBAY_CLIENT_SECRET;;
    AMAZONTAG) k=AMAZON_TAG;; RAPIDAPIPROXYSECRET) k=RAPIDAPI_PROXY_SECRET;; RAPIDAPIURL) k=RAPIDAPI_URL;; AMAZONSIGNUP) k=AMAZON_SIGNUP;; NEWSLETTERURL) k=NEWSLETTER_URL;; DISCORDINVITE) k=DISCORD_INVITE;; ADSENSECLIENT) k=ADSENSE_CLIENT;; CONTACTEMAIL) k=CONTACT_EMAIL;; SITENAME) k=SITE_NAME;; SITEURL) k=SITE_URL;; *) k=$2;; esac
  set -- "$1" "$k" "$3"
  if grep -q "^$2=" .env; then sed -i "s|^$2=.*|$2=$3|" .env; else echo "$2=$3" >> .env; fi
  grep "^$2=" .env | sed -E 's/(SECRET=|WEBHOOK=).+/\1*****/'
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
    -e GLANCES_OPT="-w" -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -v /etc/os-release:/etc/os-release:ro nicolargo/glances:latest-full >/dev/null || exit 1
  sleep 5
  sudo tailscale serve --https=8443 off >/dev/null 2>&1; sudo tailscale serve --bg --https=10000 http://127.0.0.1:61208 >/dev/null
  dns=$(tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
  echo "Live stats (tailnet only): https://$dns:10000"
  tailscale serve status
  ;;
dashinstall)  # Pi Command iPhone app: service + limited sudo rules + private HTTPS on the tailnet
  login=$(tailscale status --json | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["User"][str(d["Self"]["UserID"])]["LoginName"])')
  [ -n "$login" ] || { echo "Could not read Tailscale login"; exit 1; }
  units="gpu-prices.timer pi-cloud-backup.timer tailscaled.service docker.service wayvnc.service fieldpi-scan.service fieldpi-web.service matrixvms.service shairport-sync.service cockpit.socket picommand.service cloudflared.service"
  tmp=$(mktemp)
  { echo "# Pi Command app: exact commands only"
    for u in $units; do for a in start stop restart; do echo "pi ALL=(root) NOPASSWD: /usr/bin/systemctl $a $u"; done; done
    echo "pi ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block gpu-prices.service"
    echo "pi ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block pi-cloud-backup.service"
    echo "pi ALL=(root) NOPASSWD: /usr/bin/systemctl reboot"
    echo "pi ALL=(root) NOPASSWD: /usr/bin/tailscale funnel --bg 8088"
    echo "pi ALL=(root) NOPASSWD: /usr/bin/tailscale funnel --https=443 off"
    for d in sat 'sat\,12' 'sat\,16' usbjmicron usbsunplus usbcypress; do echo "pi ALL=(root) NOPASSWD: /usr/sbin/smartctl -a -j -d $d /dev/sd[a-z]"; done
    echo "pi ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block apt-daily-upgrade.service"
  } > "$tmp"
  sudo visudo -cf "$tmp" >/dev/null && sudo install -m 440 -o root -g root "$tmp" /etc/sudoers.d/picommand || { echo "sudoers check failed"; exit 1; }
  rm -f "$tmp"
  printf '%s\n' "[Unit]" "Description=Pi Command dashboard (iPhone app backend)" \
    "After=network-online.target tailscaled.service" "Wants=network-online.target" "[Service]" "User=pi" \
    "WorkingDirectory=/home/pi/gpu-prices" "Environment=ALLOWED_LOGIN=$login" \
    "Environment=PUSH_CONTACT=mailto:$login" "Environment=SITE_LOG=/home/pi/site-logs/access.log" \
    "Environment=PATH=/home/pi/.local/bin:/usr/local/bin:/usr/bin:/bin" \
    "ExecStart=/usr/bin/python3 /home/pi/gpu-prices/dash/server.py" "Restart=always" "RestartSec=3" \
    "[Install]" "WantedBy=multi-user.target" | sudo tee /etc/systemd/system/picommand.service >/dev/null
  sudo systemctl daemon-reload && sudo systemctl enable --now picommand.service && sudo systemctl restart picommand.service
  sudo tailscale serve --bg --https=8443 http://127.0.0.1:8099 >/dev/null
  dns=$(tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
  sleep 2; systemctl is-active picommand.service
  echo "Pi Command: https://$dns:8443  (only $login)"
  ;;
lockdown)  # admin tools (Portainer, Cockpit, Glances, raw site port) reachable only over Tailscale, not the LAN
  printf '%s\n' '#!/bin/sh' 'for i in eth0 wlan0; do' \
    ' for p in 9443 8088 61208; do' \
    '  iptables -C DOCKER-USER -i $i -p tcp -m conntrack --ctorigdstport $p -j DROP 2>/dev/null || iptables -I DOCKER-USER -i $i -p tcp -m conntrack --ctorigdstport $p -j DROP 2>/dev/null' \
    ' done' \
    ' for p in 9090 9443 61208; do' \
    '  iptables -C INPUT -i $i -p tcp --dport $p -j DROP 2>/dev/null || iptables -I INPUT -i $i -p tcp --dport $p -j DROP' \
    ' done' 'done' 'exit 0' | sudo tee /usr/local/sbin/orbit-lockdown >/dev/null
  sudo chmod 755 /usr/local/sbin/orbit-lockdown
  printf '%s\n' "[Unit]" "Description=Orbit: block admin ports from the LAN (Tailscale only)" "After=docker.service network-online.target" \
    "Wants=docker.service" "[Service]" "Type=oneshot" "RemainAfterExit=yes" "ExecStart=/usr/local/sbin/orbit-lockdown" \
    "[Install]" "WantedBy=multi-user.target" | sudo tee /etc/systemd/system/orbit-lockdown.service >/dev/null
  sudo systemctl daemon-reload && sudo systemctl enable orbit-lockdown.service >/dev/null 2>&1 && sudo systemctl restart orbit-lockdown.service
  echo "LAN blocked: 9090 9443 8088 61208 (Tailscale and localhost unaffected)"
  ;;
domain)  # bash p.sh domain example.com : serve the site on your own domain through a Cloudflare Tunnel (no open ports)
  d=${2:-}; [ -n "${3:-}" ] && d="$2.$3"   # "domain example com" works where a dot can't be typed (VNC)
  [ -n "$d" ] || { echo "usage: bash p.sh domain example.com  (domain must already be on your Cloudflare account)"; exit 1; }
  if ! command -v cloudflared >/dev/null; then
    sudo mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
    sudo apt-get update -qq && sudo apt-get install -y -qq cloudflared || { echo "cloudflared install failed"; exit 1; }
  fi
  [ -f ~/.cloudflared/cert.pem ] || { echo ">>> Open the link below, sign in to Cloudflare and click $d to authorize:"; cloudflared tunnel login || exit 1; }
  cloudflared tunnel list -o json | python3 -c 'import json,sys;sys.exit(0 if any(t["name"]=="site" for t in (json.load(sys.stdin) or [])) else 1)' || cloudflared tunnel create site
  id=$(cloudflared tunnel list -o json | python3 -c 'import json,sys;print([t["id"] for t in json.load(sys.stdin) if t["name"]=="site"][0])')
  cloudflared tunnel route dns --overwrite-dns site "$d" && cloudflared tunnel route dns --overwrite-dns site "www.$d"
  sudo mkdir -p /etc/cloudflared && sudo cp ~/.cloudflared/"$id".json /etc/cloudflared/ && sudo chmod 600 /etc/cloudflared/"$id".json
  printf '%s\n' "tunnel: $id" "credentials-file: /etc/cloudflared/$id.json" "ingress:" \
    "  - hostname: $d" "    service: http://127.0.0.1:8088" "  - hostname: www.$d" "    service: http://127.0.0.1:8088" \
    "  - service: http_status:404" | sudo tee /etc/cloudflared/config.yml >/dev/null
  systemctl list-unit-files cloudflared.service >/dev/null 2>&1 && systemctl cat cloudflared >/dev/null 2>&1 || sudo cloudflared service install
  sudo systemctl enable cloudflared >/dev/null 2>&1; sudo systemctl restart cloudflared
  bash "$0" setenv SITE_URL "https://$d"
  bash "$0" web 127.0.0.1
  [ -f /home/pi/site/index.html ] && python3 run.py build --no-ai
  sudo tailscale funnel --https=443 off >/dev/null 2>&1 || true
  sleep 5; echo "https://$d -> $(curl -s -o /dev/null -w '%{http_code}' https://$d/)"
  ;;
discord)  # paste your Discord channel webhook URL (hidden) and send a test message
  read -rsp "Discord webhook URL (hidden): " wh; echo
  case "$wh" in https://discord.com/api/webhooks/*|https://discordapp.com/api/webhooks/*) ;; *) echo "That isn't a Discord webhook URL"; exit 1;; esac
  bash "$0" setenv DISCORD_WEBHOOK "$wh" >/dev/null
  python3 -c 'import json,urllib.request,sys;u=sys.argv[1];urllib.request.urlopen(urllib.request.Request(u,json.dumps({"content":"Deal alerts connected. New deals will post here after each price update."}).encode(),{"Content-Type":"application/json","User-Agent":"UsedTechPrices-DealBot/1"}),timeout=20);print("Discord OK: test message sent")' "$wh" || echo "Test failed - check the URL"
  unset wh
  ;;
autoupdate)  # automatic daily security updates (unattended-upgrades), no automatic reboots
  sudo apt-get install -y -qq unattended-upgrades apt-listchanges >/dev/null
  printf '%s\n' 'APT::Periodic::Update-Package-Lists "1";' 'APT::Periodic::Unattended-Upgrade "1";' 'APT::Periodic::AutocleanInterval "7";' \
    | sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null
  printf '%s\n' 'Unattended-Upgrade::Automatic-Reboot "false";' 'Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";' \
    'Unattended-Upgrade::Remove-Unused-Dependencies "true";' | sudo tee /etc/apt/apt.conf.d/52orbit-unattended >/dev/null
  sudo systemctl enable --now unattended-upgrades apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1
  echo "auto updates: $(systemctl is-enabled unattended-upgrades) / timer $(systemctl is-active apt-daily-upgrade.timer)"
  ;;
orbitupgrade)  # Orbit v3: push, network radar, drive health, money panel, logs, Face ID, LAN lockdown
  sudo apt-get install -y -qq python3-cryptography smartmontools ieee-data >/dev/null && echo "packages ok"
  bind=$(docker port gpu-prices-web 80/tcp 2>/dev/null | head -1 | cut -d: -f1); [ -n "$bind" ] || bind=0.0.0.0
  bash "$0" web "$bind"
  bash "$0" lockdown
  bash "$0" autoupdate
  bash "$0" dashinstall
  sleep 3; curl -s -o /dev/null -w "app api: %{http_code} (403 = locked to your login)\n" http://127.0.0.1:8099/api/alerts
  ;;
probe)  # ping + SSH check of a LAN host by MAC suffix or IP (default: the Ubuntu server, MAC ...57:dd)
  t=${2:-57:dd}
  h=$(ip neigh | grep -i "$t" | awk '{print $1}' | head -1); [ -n "$h" ] || h=$t
  echo "Host: $h"; ping -c2 -W1 "$h" | tail -2
  if b=$(timeout 3 bash -c "exec 3<>/dev/tcp/$h/22 && head -1 <&3" 2>/dev/null); then echo "SSH OPEN: $b"; else echo "SSH CLOSED / no answer on port 22"; fi
  ;;
sshscan)  # list LAN hosts with SSH open, with their SSH banner (finds a freshly installed server)
  net=$(ip -4 route | awk '/^default/ {print $3}' | head -1 | cut -d. -f1-3)
  echo "Scanning $net.0/24 for SSH..."
  for i in $(seq 1 254); do
    ( h=$net.$i
      if timeout 1 bash -c "exec 3<>/dev/tcp/$h/22 && head -c 64 <&3" 2>/dev/null | grep -q SSH; then
        b=$(timeout 2 bash -c "exec 3<>/dev/tcp/$h/22 && head -1 <&3" 2>/dev/null | tr -d '\r')
        echo "$h  $b  $(ip neigh show $h | awk '{print $5}')"
      fi ) &
    [ $((i % 64)) -eq 0 ] && wait
  done; wait
  ;;
mkusb)  # download + verify Ubuntu Server 24.04 and write it to the one USB disk that isn't the boot disk (ERASES it)
  set -e
  base=https://releases.ubuntu.com/noble
  mkdir -p "$HOME/iso"; cd "$HOME/iso"
  curl -fsSL "$base/SHA256SUMS" -o SHA256SUMS
  iso=$(grep -o 'ubuntu-24\.04[0-9.]*-live-server-amd64\.iso' SHA256SUMS | sort -V | tail -1)
  [ -n "$iso" ] || { echo "Couldn't find the ISO name"; exit 1; }
  echo "Ubuntu image: $iso"
  if ! grep " \*\?$iso\$" SHA256SUMS | sha256sum -c --status 2>/dev/null; then
    curl -fL --progress-bar -C - "$base/$iso" -o "$iso"
  fi
  grep " \*\?$iso\$" SHA256SUMS | sha256sum -c || { echo "Checksum FAILED, not writing"; exit 1; }
  root=$(lsblk -no PKNAME "$(findmnt -no SOURCE /)" | head -1)
  mapfile -t cands < <(lsblk -dnpo NAME,TRAN,TYPE | awk -v r="/dev/$root" '$2=="usb" && $3=="disk" && $1!=r {print $1}')
  [ ${#cands[@]} -eq 1 ] || { echo "Expected exactly 1 USB disk besides the boot disk, found ${#cands[@]}:"; lsblk -dpo NAME,SIZE,TRAN,MODEL; exit 1; }
  dev=${cands[0]}
  echo; echo "Boot disk (kept): /dev/$root"; echo "Target (ERASED):"; lsblk -po NAME,SIZE,FSTYPE,LABEL,MODEL "$dev"
  read -rp "Type y to ERASE $dev and write the installer: " ok
  [ "$ok" = y ] || { echo "Cancelled"; exit 1; }
  for part in $(lsblk -lnpo NAME "$dev" | tail -n +2); do sudo umount "$part" 2>/dev/null || true; done
  sudo dd if="$iso" of="$dev" bs=4M conv=fsync oflag=direct status=progress
  sync; sudo eject "$dev" 2>/dev/null || true
  echo "DONE: installer written to $dev. Unplug it and move it to the server."
  ;;
runprices)  # start a price update now (no password: allowed by the Orbit sudo rule)
  sudo -n /usr/bin/systemctl start --no-block gpu-prices.service && echo "Price update started (15-30 min)"
  ;;
setinvite)  # save the Discord invite code (VNC can't type capitals, so the default is built in)
  [ -f .env ] || cp .env.example .env
  v="${2:-vwnb8CMxQB}"
  if grep -q "^DISCORD_INVITE=" .env; then sed -i "s|^DISCORD_INVITE=.*|DISCORD_INVITE=$v|" .env; else echo "DISCORD_INVITE=$v" >> .env; fi
  chmod 600 .env; grep "^DISCORD_INVITE=" .env
  ;;
mcp)  # Orbit MCP server for AI assistants at https://<domain>/mcp (container on 127.0.0.1:8090 + tunnel route)
  mkdir -p ~/orbit-mcp
  [ -f ~/orbit-mcp/keys.json ] || { echo '{}' > ~/orbit-mcp/keys.json; chmod 600 ~/orbit-mcp/keys.json; }
  site=$(grep -E '^SITE_URL=' .env | cut -d= -f2-)
  docker rm -f orbit-mcp >/dev/null 2>&1 || true
  docker run -d --name orbit-mcp --restart unless-stopped --user "$(id -u):$(id -g)" --read-only \
    -p 127.0.0.1:8090:8000 -e ORBIT_DATA=/site/api/v1 -e ORBIT_STATE=/state -e SITE_URL="$site" \
    -v "$HOME/gpu-prices/mcp:/app:ro" -v "$HOME/worker/site:/site:ro" -v "$HOME/orbit-mcp:/state" \
    python:3.12-alpine python /app/server.py >/dev/null || { echo "docker run failed"; exit 1; }
  sleep 3; echo "local: $(curl -s 127.0.0.1:8090/healthz)"
  cfg=/etc/cloudflared/config.yml
  if ! sudo grep -q "127.0.0.1:8090" "$cfg"; then
    d=$(sudo grep -m1 -E '^ *- hostname:' "$cfg" | awk '{print $3}')
    sudo cp "$cfg" "$cfg.bak-mcp"
    sudo python3 - "$cfg" "$d" <<'PY'
import sys
p, d = sys.argv[1], sys.argv[2]
lines = open(p).read().splitlines()
i = lines.index("ingress:") + 1
lines[i:i] = [f"  - hostname: {d}", "    path: ^/mcp", "    service: http://127.0.0.1:8090"]
open(p, "w").write("\n".join(lines) + "\n")
PY
    sudo cloudflared tunnel ingress validate --config "$cfg" >/dev/null 2>&1 || { sudo cp "$cfg.bak-mcp" "$cfg"; echo "tunnel config invalid; restored"; exit 1; }
    sudo systemctl restart cloudflared; sleep 5
  fi
  echo "public: $(curl -s -X POST "$site/mcp" -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 120)"
  ;;
mcpkey)  # bash p.sh mcpkey <label> : create a paid-tier MCP API key (printed once)
  [ -n "${2:-}" ] || { echo "usage: bash p.sh mcpkey customer-name"; exit 1; }
  python3 - "$2" <<'PY'
import json, secrets, sys, pathlib
p = pathlib.Path.home() / "orbit-mcp/keys.json"
k = json.loads(p.read_text() or "{}"); key = "orb_" + secrets.token_urlsafe(24); k[key] = sys.argv[1]
p.write_text(json.dumps(k, indent=1)); print(key)
PY
  ;;
aikey)  # type your OpenRouter API key (hidden, never shown) and test it with one tiny request
  read -rsp "OpenRouter API key (hidden): " k; echo
  case "$k" in sk-or-*) ;; *) echo "That isn't an OpenRouter key (starts with sk-or-)"; exit 1;; esac
  bash "$0" setenv OPENROUTER_API_KEY "$k" >/dev/null; unset k
  python3 -c 'from tracker import ai,config;print("model:",config.AI_MODEL);print("test:",ai._openrouter("Reply with exactly: The RTX 3080 is typically $400 used.") or "FAILED")'
  ;;
restartorbit)  # restart the Orbit app (no password: allowed by the Orbit sudo rule)
  sudo -n /usr/bin/systemctl restart picommand.service && sleep 2 && echo "Orbit: $(systemctl is-active picommand.service)"
  ;;
dashtest)  # check the app backend answers (with and without your identity header)
  login=$(systemctl show picommand.service -p Environment --value | tr ' ' '\n' | sed -n 's/^ALLOWED_LOGIN=//p')
  echo "no identity -> $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8099/api/live) (expect 403)"
  python3 dash/selftest.py "$login"
  for a in "restart wayvnc.service" "start --no-block gpu-prices.service"; do sudo -n -l /usr/bin/systemctl $a >/dev/null && echo "sudo rule ok: $a"; done
  ;;
appcheck)  # why won't the app open?
  dns=$(tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
  echo "== serve config"; tailscale serve status
  echo "== service: $(systemctl is-active picommand.service)  local: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8099/)"
  echo "== via tailnet https: $(curl -s -o /dev/null -w '%{http_code} %{errormsg}' --max-time 40 https://$dns:8443/)"
  echo "== cert: $(echo | timeout 20 openssl s_client -connect $dns:8443 -servername $dns 2>/dev/null | openssl x509 -noout -subject -enddate 2>/dev/null)"
  echo "== peers"; tailscale status | head -5
  ;;
netfix)  # Pi is on Ethernet AND Wi-Fi in the same subnet: stop each NIC answering for the other's IP (ARP flux)
  printf '%s\n' '# Two NICs on one subnet: answer ARP only on the owning interface' \
    'net.ipv4.conf.all.arp_ignore=1' 'net.ipv4.conf.all.arp_announce=2' \
    'net.ipv4.conf.all.rp_filter=2' 'net.ipv4.conf.default.rp_filter=2' \
    | sudo tee /etc/sysctl.d/90-dual-nic.conf >/dev/null
  sudo sysctl -q -p /etc/sysctl.d/90-dual-nic.conf && echo "applied"
  ip -4 -br addr | grep -E 'eth|wlan'; ip route | grep default
  ;;
mtutest)  # does the direct path to the phone carry big packets? (TLS needs ~1200+ byte packets)
  peer=${2:-iphone-14-pro-max}
  for sz in 100 800 1100 1200 1260; do
    printf "size %-5s " $sz; tailscale ping -c 3 --timeout 3s --size $sz "$peer" 2>&1 | grep -E "pong|timeout|no reply" | tail -1
  done
  ip -br link | grep -E "eth|wlan|tailscale"
  ;;
dnstest)  # what does the name resolve to via MagicDNS, your router, and public DNS?
  dns=$(tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
  q() { python3 - "$1" "$2" <<'PY'
import socket,struct,sys,random
name,server=sys.argv[1],sys.argv[2]
tid=random.randint(0,65535)
pkt=struct.pack(">HHHHHH",tid,0x0100,1,0,0,0)+b"".join(bytes([len(p)])+p.encode() for p in name.split("."))+b"\0"+struct.pack(">HH",1,1)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3)
try:
    s.sendto(pkt,(server,53)); d,_=s.recvfrom(2048)
    an=struct.unpack(">H",d[6:8])[0]; i=12
    while d[i]: i+=d[i]+1
    i+=5; ips=[]
    for _ in range(an):
        i+= 2 if d[i]&0xC0==0xC0 else 0
        t,c,ttl,l=struct.unpack(">HHIH",d[i:i+10]); i+=10
        if t==1: ips.append(".".join(map(str,d[i:i+4])))
        i+=l
    print(server, "->", ips or "no A record")
except Exception as e: print(server, "->", e)
PY
  }
  echo "name: $dns"
  q "$dns" 100.100.100.100; q "$dns" 192.168.1.1; q "$dns" 1.1.1.1; q "$dns" 8.8.8.8
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
