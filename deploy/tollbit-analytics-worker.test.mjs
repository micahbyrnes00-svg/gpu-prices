import assert from 'node:assert/strict';
import { test } from 'node:test';
import worker, { logEvent } from './tollbit-analytics-worker.mjs';

test('logs only public page paths and removes query strings, referrers and location', () => {
  const request = new Request('https://orbitbymicah.com/check.html?session_id=SECRET', {
    headers: { 'cf-connecting-ip': '192.0.2.1', 'user-agent': 'ExampleBot',
      referer: 'https://example.com/private?token=SECRET', authorization: 'Bearer SECRET', cookie: 'SECRET' },
  });
  request.cf = { city: 'PRIVATE', latitude: 'PRIVATE', longitude: 'PRIVATE', httpProtocol: 'HTTP/2' };
  const entry = logEvent(request, new Response('public'));
  assert.equal(entry.url, '/check.html');
  assert.equal(entry.ip_address, '192.0.2.1');
  assert.equal(entry.request_referer, null);
  assert.doesNotMatch(JSON.stringify(entry), /SECRET|PRIVATE|authorization|cookie|latitude|longitude/);
});

test('excludes key issuance, MCP, raw API data, private paths and other hosts', () => {
  for (const path of ['/mcp', '/mcp/key?session_id=SECRET', '/api/v1/models.json', '/.env',
      '/healthz', '/data/index.json', '/mcp%2Fkey', '/anything/secret.html']) {
    assert.equal(logEvent(new Request('https://orbitbymicah.com' + path), new Response()), null, path);
  }
  assert.equal(logEvent(new Request('https://other.example/index.html'), new Response()), null);
  assert.equal(logEvent(new Request('https://orbitbymicah.com/', { method: 'POST' }), new Response()), null);
});

test('returns the original response even when analytics delivery fails', async () => {
  const oldFetch = globalThis.fetch;
  const response = new Response('original response', { headers: { 'X-Test': 'unchanged' } });
  const background = [];
  globalThis.fetch = async input => {
    if (input instanceof Request) return response;
    throw new Error('network failure');
  };
  try {
    const result = await worker.fetch(new Request('https://orbitbymicah.com/'),
      { TOLLBIT_LOG_KEY: 'TEST' }, { waitUntil: p => background.push(p) });
    assert.equal(result, response);
    assert.equal(await result.text(), 'original response');
    await Promise.all(background);
  } finally {
    globalThis.fetch = oldFetch;
  }
});
