"""Background read-only polling of themachine over the tailnet; requests never wait for SSH.

Polls every 3 s only while someone is looking at Orbit (an /api/fleet request in the last 20 s),
and every 60 s otherwise so alerts still work. The address comes from Tailscale by device name,
and when Tailscale already knows the device is offline no SSH attempt is made at all.
"""
import json
import os
import subprocess
import threading
import time

import tailnet

HOST = os.environ.get("FLEET_HOST", "themachine")          # tailnet device name
USER = os.environ.get("FLEET_USER", "micahbyrnes")
PORT = os.environ.get("FLEET_PORT", "2222")
FALLBACK_IP = os.environ.get("FLEET_ADDR", "100.125.132.108")  # used only if Tailscale can't be read
FAST, SLOW, WATCHED = 3, 60, 20


class Fleet:
    def __init__(self, state):
        self.state = state
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.viewed = 0.0
        self.remote = {'id': HOST, 'label': HOST,
                       'role': 'Apps · shared storage · backup destination',
                       'online': False, 'status': 'Connecting', 'lastSuccess': None}
        threading.Thread(target=self._loop, daemon=True).start()

    def _command(self, addr):
        return ['ssh', '-F', '/dev/null', '-T', '-p', PORT, '-o', 'BatchMode=yes',
                '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'ConnectTimeout=4', '-o', 'ConnectionAttempts=1',
                '-o', 'ControlMaster=auto', '-o', 'ControlPersist=90',
                '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=2',
                '-o', 'ControlPath=' + str(self.state / 'metrics-ssh.sock'),
                '-o', 'UserKnownHostsFile=' + str(self.state / 'themachine_known_hosts'),
                '-i', str(self.state / 'orbit_themachine_ed25519'), f'{USER}@{addr}']

    def _poll(self, addr):
        result = subprocess.run(self._command(addr), capture_output=True, text=True, timeout=7)
        if result.returncode:
            raise RuntimeError('SSH metrics unavailable')
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get('host') != HOST:
            raise ValueError('Unexpected metrics')
        if not isinstance(data.get('mem'), dict) or not isinstance(data.get('cpu'), (float, int)):
            raise ValueError('Incomplete metrics')
        return data

    def _loop(self):
        while True:
            peer = tailnet.peer(HOST)
            link = {'path': peer['path'], 'ip': peer['ip'], 'os': peer['os'],
                    'lastSeen': peer['lastSeen']} if peer else None
            try:
                if peer and not peer['online']:
                    raise ConnectionError('Offline on tailnet')
                data = self._poll((peer or {}).get('ip') or FALLBACK_IP)
                with self.lock:
                    self.remote.update(online=True, status='Online', metrics=data,
                                       lastSuccess=time.time(), tailnet=link)
            except Exception as error:  # noqa: BLE001
                with self.lock:
                    self.remote.update(online=False, tailnet=link,
                                       status='Offline' if isinstance(error, ConnectionError) else 'Unreachable')
                    self.remote.pop('metrics', None)
            fast = time.time() - self.viewed < WATCHED
            self.wake.wait(FAST if fast else SLOW)
            self.wake.clear()

    def remote_state(self):
        with self.lock:
            return dict(self.remote)

    def snapshot(self, pi):
        idle = time.time() - self.viewed >= WATCHED
        self.viewed = time.time()
        if idle:
            self.wake.set()  # someone opened Orbit: refresh now instead of after the slow interval
        remote = self.remote_state()
        return {'ts': time.time(), 'machines': [
            {'id': 'pi', 'label': 'Raspberry Pi', 'role': 'Orbit · price tracker · cloud backups',
             'online': bool(pi.get('ts')), 'status': 'Online' if pi.get('ts') else 'Starting',
             'lastSuccess': pi.get('ts'), 'metrics': pi}, remote]}
