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
web)  # serve the real site (docs/) once it exists, else the demo
  src=/home/pi/gpu-prices/docs; [ -f $src/index.html ] || src=/home/pi/gpu-prices/demo-site
  sudo docker rm -f gpu-prices-web >/dev/null 2>&1
  sudo docker run -d --name gpu-prices-web --restart unless-stopped -p 8088:80 \
    -v $src:/usr/share/caddy:ro caddy:2-alpine >/dev/null && echo "Serving $src on :8088"
  ;;
scale)  # resize the headless VNC desktop to fit the TigerVNC window; persists via kanshi
  mode=${2:-1504x846}
  out=$(wlr-randr | awk 'NR==1{print $1}')
  wlr-randr --output "$out" --custom-mode "$mode" && echo "Set $out to $mode"
  mkdir -p ~/.config/kanshi
  printf 'profile {\n  output %s mode --custom %s\n}\n' "$out" "$mode" > ~/.config/kanshi/config
  ;;
status)
  hostname; uptime
  systemctl --failed --no-legend
  df -h / /mnt/seagate1 /mnt/seagate2 2>/dev/null
  sudo docker ps --format '{{.Names}} {{.Status}}'
  ;;
esac
