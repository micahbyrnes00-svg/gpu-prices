"""Security autopilot status: automatic updates, reboot-needed, SSH logins, site probing, LAN exposure."""
import re
import subprocess
import time
from pathlib import Path

import store

LOCKDOWN_PORTS = {9090, 9443, 8088, 61208}


def _run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def updates():
    """Simulated upgrade (no root needed, changes nothing): how many packages wait, how many are security."""
    code, out = _run(["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"], 120)
    inst = [l for l in out.splitlines() if l.startswith("Inst ")]
    sec = [l for l in inst if "-security" in l]
    res = {"pending": len(inst), "security": len(sec), "names": [l.split()[1] for l in inst][:30], "ts": time.time(),
           "error": None if code == 0 else out.strip()[-160:]}
    store.put("sec_updates", res)
    return res


def auto_updates():
    _, en = _run(["systemctl", "is-enabled", "unattended-upgrades"])
    _, tm = _run(["systemctl", "is-active", "apt-daily-upgrade.timer"])
    log = Path("/var/log/unattended-upgrades/unattended-upgrades.log")
    last = log.stat().st_mtime if log.exists() else None
    applied = None
    try:
        lines = [l for l in log.read_text(errors="ignore").splitlines() if "Packages that will be upgraded" in l or "All upgrades installed" in l]
        applied = lines[-1][:200] if lines else None
    except OSError:
        pass
    return {"enabled": en.strip() == "enabled" and tm.strip() == "active", "lastRun": last, "lastNote": applied}


def ssh_events(since):
    """Accepted / failed SSH logins since a unix time (pi is in the adm group, so it can read the journal)."""
    _, out = _run(["journalctl", "-u", "ssh", "-u", "sshd", "--since", f"@{int(since)}", "--no-pager", "-o", "short-unix", "-q"], 30)
    ev = []
    for line in out.splitlines():
        m = re.match(r"^([\d.]+) \S+ \S+: (Accepted|Failed) (\S+) for (?:invalid user )?(\S+) from (\S+)", line)
        if m:
            ev.append({"ts": float(m.group(1)), "ok": m.group(2) == "Accepted", "method": m.group(3), "user": m.group(4), "ip": m.group(5)})
    return ev


def listening():
    _, out = _run(["ss", "-Hltn"])
    ports = set()
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 4 and ":" in f[3]:
            addr, port = f[3].rsplit(":", 1)
            if addr in ("0.0.0.0", "*", "[::]") and port.isdigit():
                ports.add(int(port))
    return sorted(ports)


def summary():
    now = time.time()
    _, lock = _run(["systemctl", "is-active", "orbit-lockdown.service"])
    lock_on = lock.strip() == "active"
    ports = listening()
    ev = store.get("ssh_log", [])
    probes = store.q("SELECT path, COUNT(*) n FROM hits WHERE kind='err' AND ts>? GROUP BY path ORDER BY n DESC LIMIT 6", (now - 86400,))
    probers = store.q("SELECT COUNT(DISTINCT visitor) v, COUNT(*) n FROM hits WHERE kind='err' AND ts>?", (now - 86400,))[0]
    return {
        "auto": auto_updates(),
        "updates": store.get("sec_updates"),
        "reboot": Path("/run/reboot-required").exists() or Path("/var/run/reboot-required").exists(),
        "rebootPkgs": (Path("/run/reboot-required.pkgs").read_text().split() if Path("/run/reboot-required.pkgs").exists() else [])[:10],
        "lockdown": lock_on,
        "openPorts": [{"port": p, "blocked": lock_on and p in LOCKDOWN_PORTS} for p in ports],
        "sshOk": [e for e in ev if e["ok"]][-5:][::-1],
        "sshFail24": sum(1 for e in ev if not e["ok"] and e["ts"] > now - 86400),
        "probes24": probers["n"], "probers24": probers["v"], "probePaths": probes,
    }
