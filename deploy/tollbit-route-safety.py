#!/usr/bin/env python3
"""Verify exact public routes and enable origin fallback after Wrangler deploy.

Run with the same authorized Wrangler profile as deployment. Credentials stay in
memory and are sent only to Cloudflare's API. No route is created or deleted.
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

p = argparse.ArgumentParser()
p.add_argument('--apply', action='store_true')
a = p.parse_args()
cfg = json.loads(Path(__file__).with_name('wrangler-tollbit.jsonc').read_text())
expected = {r['pattern'] for r in cfg['routes']}
zone_ids = {r['zone_id'] for r in cfg['routes']}
assert len(zone_ids) == 1 and expected
assert all(re.fullmatch(r'orbitbymicah\.com/(?:[a-z0-9]+(?:-[a-z0-9]+)*\.html|robots\.txt|sitemap\.xml|llms(?:-full)?\.txt)?', x) for x in expected)
assert not any(x.split('/', 1)[1].startswith(('api', 'mcp', 'key', 'checkout')) for x in expected)
auth = json.loads(subprocess.check_output([os.environ.get('WRANGLER_BIN', 'wrangler'), 'auth', 'token', '--json'], text=True))
base = 'https://api.cloudflare.com/client/v4/zones/' + next(iter(zone_ids)) + '/workers/routes'

def api(method='GET', suffix='', body=None):
    req = urllib.request.Request(base + suffix, method=method,
        headers={'Authorization': 'Bearer ' + auth['token'], 'Content-Type': 'application/json'},
        data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    assert data['success'], 'Cloudflare route operation failed'
    return data['result']

routes = [r for r in api() if r.get('script') == cfg['name']]
assert {r['pattern'] for r in routes} == expected, 'Deployed routes differ from reviewed public routes; stop.'
changes = [r for r in routes if not r.get('request_limit_fail_open')]
print('Verified exact public routes:', len(routes))
print('Routes needing origin fallback:', len(changes))
if a.apply:
    def update(r):
        return api('PUT', '/' + r['id'], {'pattern': r['pattern'], 'script': cfg['name'], 'request_limit_fail_open': True})
    if changes:
        first = update(changes[0])
        check = api(suffix='/' + changes[0]['id'])
        assert check.get('request_limit_fail_open') is True, 'Cloudflare did not accept fallback setting; stop.'
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(update, changes[1:]))
    final = [r for r in api() if r.get('script') == cfg['name']]
    assert {r['pattern'] for r in final} == expected
    assert all(r.get('request_limit_fail_open') is True for r in final)
    print('All public routes verified with origin fallback enabled.')
