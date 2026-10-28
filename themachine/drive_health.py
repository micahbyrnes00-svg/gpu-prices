#!/usr/bin/env python3
"""Root timer: read SMART for the three known disks and cache sanitized results."""
import json
import os
import subprocess
import time
from pathlib import Path

EXPECTED = {
    '50026B76833809AC': 'SSD · Ubuntu',
    'WD-WCC4M5UU3REH': '2 TB · Data',
    'NACMALZM': '4 TB · Backups',
}


def summarize(data, code):
    passed = data.get('smart_status', {}).get('passed')
    attrs = data.get('ata_smart_attributes', {}).get('table', [])
    errors = {}
    labels = {5: 'Reallocated sectors', 197: 'Pending sectors', 198: 'Uncorrectable sectors', 199: 'Interface CRC errors'}
    for attr in attrs:
        if attr.get('id') in labels:
            value = attr.get('raw', {}).get('value')
            if isinstance(value, (int, float)):
                errors[labels[attr['id']]] = value
    nvme = data.get('nvme_smart_health_information_log', {})
    if isinstance(nvme.get('media_errors'), int):
        errors['Media errors'] = nvme['media_errors']
    if passed is False or code & 0x18:
        status = 'failed'
    elif passed is not True:
        status = 'unavailable'
    elif any(errors.values()) or code & 0xe7 or nvme.get('critical_warning', 0):
        status = 'attention'
    else:
        status = 'passed'
    return {'status': status, 'smartPassed': passed,
            'temperature': data.get('temperature', {}).get('current', nvme.get('temperature')),
            'powerOnHours': data.get('power_on_time', {}).get('hours', nvme.get('power_on_hours')),
            'errors': errors, 'wearUsedPercent': nvme.get('percentage_used'),
            'message': 'SMART unavailable through this connection' if status == 'unavailable' else
                       'Historical error counts can include past events; review trends.' if status == 'attention' else ''}


def read_smart(device, usb):
    attempts = [None, 'sat', 'sat,12'] if usb else [None]
    for kind in attempts:
        command = ['/usr/sbin/smartctl', '-a', '-j']
        if kind:
            command += ['-d', kind]
        command.append(device)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=12)
            data = json.loads(result.stdout)
            summary = summarize(data, result.returncode)
            if summary['status'] != 'unavailable':
                return summary
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    return {'status': 'unavailable', 'message': 'SMART unavailable through this connection', 'errors': {}}


def main():
    result = subprocess.run(['lsblk', '-J', '-d', '-b', '-o', 'NAME,MODEL,SERIAL,TRAN,SIZE'],
                            check=True, capture_output=True, text=True)
    devices = {str(d.get('serial') or '').strip(): d for d in json.loads(result.stdout)['blockdevices']}
    drives = []
    for serial, label in EXPECTED.items():
        device = devices.get(serial)
        if not device:
            drives.append({'serial': serial, 'label': label, 'status': 'missing', 'message': 'Drive not detected'})
            continue
        drives.append({'serial': serial, 'label': label, 'model': device.get('model'),
                       'device': '/dev/' + device['name'], 'size': device.get('size'),
                       **read_smart('/dev/' + device['name'], device.get('tran') == 'usb')})
    dest = Path('/var/lib/orbit-drive-health/status.json')
    dest.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temp = dest.with_suffix('.new')
    temp.write_text(json.dumps({'ts': time.time(), 'drives': drives}))
    temp.chmod(0o644)
    os.replace(temp, dest)
    print(json.dumps({'drives': [{'label': d['label'], 'status': d['status']} for d in drives]}))


if __name__ == '__main__':
    main()
