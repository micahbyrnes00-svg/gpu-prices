"""Background read-only Celeron polling; requests never wait for SSH."""
import json
import subprocess
import threading
import time


class Fleet:
    def __init__(self, state):
        self.state = state
        self.lock = threading.Lock()
        self.remote = {'id': 'themachine', 'label': 'themachine',
                       'role': 'Apps · shared storage · backup destination',
                       'online': False, 'status': 'Connecting', 'lastSuccess': None}
        threading.Thread(target=self._loop, daemon=True).start()

    def _poll(self):
        command = ['ssh', '-F', '/dev/null', '-T', '-p', '2222', '-o', 'BatchMode=yes',
                   '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
                   '-o', 'ConnectTimeout=4', '-o', 'ConnectionAttempts=1',
                   '-o', 'ControlMaster=auto', '-o', 'ControlPersist=30',
                   '-o', 'ControlPath=' + str(self.state / 'metrics-ssh.sock'),
                   '-o', 'UserKnownHostsFile=' + str(self.state / 'themachine_known_hosts'),
                   '-i', str(self.state / 'orbit_themachine_ed25519'),
                   'micahbyrnes@100.125.132.108']
        result = subprocess.run(command, capture_output=True, text=True, timeout=7)
        if result.returncode:
            raise RuntimeError('SSH metrics unavailable')
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get('host') != 'themachine':
            raise ValueError('Unexpected metrics')
        if not isinstance(data.get('mem'), dict) or not isinstance(data.get('cpu'), (float, int)):
            raise ValueError('Incomplete metrics')
        return data

    def _loop(self):
        while True:
            try:
                data = self._poll()
                with self.lock:
                    self.remote.update(online=True, status='Online', metrics=data,
                                       lastSuccess=time.time())
            except Exception:
                with self.lock:
                    self.remote.update(online=False, status='Unreachable')
                    self.remote.pop('metrics', None)
            time.sleep(3)

    def snapshot(self, pi):
        with self.lock:
            remote = dict(self.remote)
        return {'ts': time.time(), 'machines': [
            {'id': 'pi', 'label': 'Raspberry Pi', 'role': 'Orbit · price tracker · cloud backups',
             'online': bool(pi.get('ts')), 'status': 'Online' if pi.get('ts') else 'Starting',
             'lastSuccess': pi.get('ts'), 'metrics': pi}, remote]}
