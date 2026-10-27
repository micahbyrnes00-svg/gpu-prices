"""Disk health via smartctl (USB bridges need -d sat). Runs through a narrow sudo rule."""
import json
import subprocess
import time

import store

DTYPES = ["sat", "sat,12", "sat,16", "usbjmicron", "usbsunplus", "usbcypress"]
WATCH_ATTRS = {5: "Reallocated sectors", 187: "Uncorrectable errors", 188: "Command timeouts",
               197: "Pending sectors", 198: "Offline uncorrectable", 199: "UDMA CRC errors"}


def _disks():
    out = subprocess.run(["lsblk", "-dnJ", "-o", "NAME,MODEL,SIZE,TRAN,TYPE"], capture_output=True, text=True).stdout
    return [d for d in json.loads(out or '{"blockdevices":[]}')["blockdevices"]
            if d.get("type") == "disk" and d.get("tran") in ("usb", "sata", "nvme")]


def read_all():
    res = []
    for d in _disks():
        dev = "/dev/" + d["name"]
        info = {"dev": dev, "model": (d.get("model") or "").strip(), "size": d.get("size")}
        j, raw = None, ""
        for dtype in DTYPES:  # USB bridges differ: try the common SAT pass-through variants
            r = subprocess.run(["sudo", "-n", "/usr/sbin/smartctl", "-a", "-j", "-d", dtype, dev],
                               capture_output=True, text=True, timeout=60)
            raw = r.stderr or r.stdout
            try:
                j = json.loads(r.stdout)
            except ValueError:
                continue
            if "smart_status" in j:
                info["via"] = dtype
                break
        if j is None:
            info["error"] = (raw or "smartctl failed").strip()[-200:]
            res.append(info)
            continue
        if not j.get("smart_support", {}).get("available", True) or "smart_status" not in j:
            info["error"] = "Drive doesn't report SMART health over USB"
            msgs = j.get("smartctl", {}).get("messages") or []
            if msgs:
                info["error"] += ": " + msgs[0].get("string", "")[:120]
            res.append(info)
            continue
        attrs = {a["id"]: a for a in j.get("ata_smart_attributes", {}).get("table", [])}
        info.update({
            "passed": j["smart_status"].get("passed"),
            "temp": (j.get("temperature") or {}).get("current"),
            "hours": (j.get("power_on_time") or {}).get("hours"),
            "cycles": j.get("power_cycle_count"),
            "serial": j.get("serial_number"),
            "attrs": {WATCH_ATTRS[k]: attrs[k]["raw"]["value"] for k in WATCH_ATTRS if k in attrs},
        })
        res.append(info)
    store.put("disks", {"ts": time.time(), "disks": res})
    return res


def cached():
    return store.get("disks", {"ts": None, "disks": []})
