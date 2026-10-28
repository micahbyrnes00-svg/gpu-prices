#!/usr/bin/env python3
"""Fixed, unprivileged snapshot for Orbit's forced-command SSH key."""
import json
import os
import subprocess
import time
from pathlib import Path

_previous_net = None


def counters():
    cpu = []
    for line in Path('/proc/stat').read_text().splitlines():
        if line.startswith('cpu'):
            values = list(map(int, line.split()[1:9]))
            cpu.append((sum(values), values[3] + values[4]))
    return cpu


def snapshot():
    global _previous_net
    before = counters()
    time.sleep(0.3)
    after = counters()
    usage = []
    for (total0, idle0), (total1, idle1) in zip(before, after):
        delta = total1 - total0
        usage.append(round(max(0, min(100, 100 * (1 - (idle1-idle0)/delta))), 1) if delta else 0)
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        mem[key] = int(value.split()[0]) * 1024
    disks = []
    for mount, label in [('/', 'SSD · Ubuntu'), ('/srv/data', '2 TB · Data'), ('/srv/backups', '4 TB · Backups')]:
        mounted = os.path.ismount(mount)
        item = {'mount': mount, 'label': label, 'mounted': mounted}
        if mounted:
            stat = os.statvfs(mount)
            item.update(total=stat.f_blocks*stat.f_frsize, free=stat.f_bavail*stat.f_frsize)
        disks.append(item)
    temperatures = []
    for path in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        try:
            value = int(path.read_text()) / 1000
            if 0 < value < 130:
                temperatures.append(value)
        except (OSError, ValueError):
            pass
    rx = tx = 0
    for line in Path('/proc/net/dev').read_text().splitlines()[2:]:
        interface, values = line.split(':', 1)
        if interface.strip().startswith(('lo', 'veth', 'docker', 'br-', 'tailscale')):
            continue
        fields = values.split(); rx += int(fields[0]); tx += int(fields[8])
    now = time.monotonic()
    rates = {'rx': 0, 'tx': 0}
    if _previous_net:
        r0,t0,stamp = _previous_net
        elapsed = now-stamp
        rates = {'rx': max(0,(rx-r0)/elapsed), 'tx': max(0,(tx-t0)/elapsed)}
    _previous_net = rx,tx,now
    procs = []
    try:
        result = subprocess.run(['ps','-eo','pid,pcpu,pmem,comm','--sort=-pcpu','--no-headers'],capture_output=True,text=True,timeout=2)
        for line in result.stdout.splitlines()[:8]:
            fields = line.split(None,3)
            if len(fields)==4 and fields[3]!='ps':
                procs.append({'pid':int(fields[0]),'cpu':float(fields[1]),'mem':float(fields[2]),'name':fields[3]})
    except (OSError,ValueError,subprocess.TimeoutExpired):
        pass
    clocks = []
    for path in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_cur_freq'):
        try:
            clocks.append(int(path.read_text())/1000)
        except (OSError,ValueError):
            pass
    try:
        drive_health = json.loads(Path('/var/lib/orbit-drive-health/status.json').read_text())
        drive_health['stale'] = time.time() - drive_health.get('ts', 0) > 1200
    except (OSError, ValueError, TypeError):
        drive_health = {'configured': False, 'drives': []}
    try:
        backup = json.loads(Path('/var/lib/orbit-backup/status.json').read_text())
    except (OSError, ValueError, TypeError):
        backup = {'configured': False}
    return {
        'ts': time.time(), 'host': os.uname().nodename,
        'cpu': usage[0] if usage else 0, 'cores': usage[1:],
        'mem': {'total': mem['MemTotal'], 'avail': mem['MemAvailable'],
                'swapTotal': mem.get('SwapTotal', 0), 'swapFree': mem.get('SwapFree', 0)},
        'temp': max(temperatures) if temperatures else None,
        'load': list(os.getloadavg()),
        'uptime': float(Path('/proc/uptime').read_text().split()[0]),
        'disks': disks,
        'driveHealth': drive_health,
        'backup': backup,
        'net': rates, 'procs': procs[:6],
        'clock': round(sum(clocks)/len(clocks)) if clocks else None,
    }


if __name__ == '__main__':
    try:
        cached = json.loads((Path.home()/'.cache/orbit/metrics.json').read_text())
        if time.time()-cached['ts']>5:
            raise ValueError('stale')
    except (OSError,ValueError,KeyError):
        cached = snapshot()
    print(json.dumps(cached))
