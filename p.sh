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
