// Draft: deploy only after approval of log sharing and the matching privacy notice.
const PUBLIC_HOSTS = new Set(['orbitbymicah.com', 'www.orbitbymicah.com']);
const PUBLIC_PAGE = /^\/(?:[a-z0-9]+(?:-[a-z0-9]+)*\.html|robots\.txt|sitemap\.xml|llms(?:-full)?\.txt)?$/;

export function logEvent(request, response) {
  const url = new URL(request.url);
  if (!PUBLIC_HOSTS.has(url.hostname) || !['GET', 'HEAD'].includes(request.method)
      || !PUBLIC_PAGE.test(url.pathname)) return null;
  return {
    timestamp: new Date().toISOString(),
    ip_address: request.headers.get('cf-connecting-ip'),
    host: url.hostname,
    url: url.pathname,
    request_method: request.method,
    request_protocol: request.cf?.httpProtocol ?? null,
    request_user_agent: request.headers.get('user-agent'),
    request_latency: null,
    request_referer: null,
    response_state: null,
    response_status: response.status,
    response_reason: response.statusText,
    response_body_size: response.headers.get('content-length'),
  };
}

async function sendLog(entry, key) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2000);
  try {
    const response = await fetch('https://log.tollbit.com/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', TollbitKey: key },
      body: JSON.stringify(entry) + '\n',
      signal: controller.signal,
    });
    if (!response.ok) console.warn('TollBit log delivery status:', response.status);
  } catch {
    console.warn('TollBit log delivery failed');
  } finally {
    clearTimeout(timeout);
  }
}

export default {
  async fetch(request, env, ctx) {
    if (!PUBLIC_HOSTS.has(new URL(request.url).hostname)) {
      return new Response('Not found', { status: 404 });
    }
    const response = await fetch(request);
    const entry = logEvent(request, response);
    if (entry && env.TOLLBIT_LOG_KEY) ctx.waitUntil(sendLog(entry, env.TOLLBIT_LOG_KEY));
    return response;
  },
};
