#!/usr/bin/env python3
"""Unprivileged live metrics and bounded history; no network listener."""
import json
import os
import time
from pathlib import Path
from metrics import snapshot

history = {'cpu': [], 'rx': [], 'tx': [], 'temp': []}
dest=Path.home()/'.cache/orbit/metrics.json'
dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
while True:
    started=time.monotonic()
    try:
        data=snapshot()
        for key,value in [('cpu',data['cpu']),('rx',data['net']['rx']),('tx',data['net']['tx']),('temp',data['temp'])]:
            history[key].append(value or 0)
            del history[key][:-120]
        data['history']=history
        temp=dest.with_suffix('.new')
        temp.write_text(json.dumps(data));temp.chmod(0o600);os.replace(temp,dest)
    except Exception as error:
        print(type(error).__name__,str(error),flush=True)
    time.sleep(max(0.1,1-(time.monotonic()-started)))
