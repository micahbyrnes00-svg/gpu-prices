# Limited TollBit analytics

The live Worker passes through the original response and sends a background log for GET/HEAD requests to 202 exact public URLs: the homepage, public HTML pages from the October 29 sitemap, and robots.txt, sitemap.xml, llms.txt and llms-full.txt. API/MCP/key/checkout routes are outside its invocation routes. Query strings, referrers, cookies, authorization headers and location fields are excluded from payloads. Exact Cloudflare routes do not match query-string variants; those requests bypass this analytics Worker.

TOLLBIT_LOG_KEY is an encrypted Cloudflare secret, never source code. TOLLBIT_ANALYTICS=1 on themachine enables the matching public privacy disclosure. Worker invocation logs and workers.dev/preview URLs are disabled; delivery-status warnings contain no visitor payloads. All routes must use origin fallback for quota failures. Background delivery failures do not change the site response.

TollBit verified log streaming on October 29 and reports it is ingesting logs/configuring the dashboard, which can take 24–48 hours. This technical verification does not confirm licensing eligibility or activate rates, licenses or payouts. An eligibility/reduced-schema inquiry has been sent to TollBit.

## Updating the deployment

1. Run `node --test deploy/tollbit-analytics-worker.test.mjs`.
2. Review `deploy/wrangler-tollbit.jsonc`; retain exact public routes only. Do not replace them with a broad `/*` route. Add new public pages deliberately; exclude API/MCP/key/checkout/private paths.
3. Run `wrangler deploy --config deploy/wrangler-tollbit.jsonc` with the authorized profile.
4. Immediately run `python3 deploy/tollbit-route-safety.py --apply` with the same Wrangler profile. Set WRANGLER_BIN if Wrangler is not on PATH. Wrangler deployment resets request_limit_fail_open; this helper restores and verifies it for every exact reviewed route. It does not create/delete routes or touch other Workers.
5. Verify public responses and TollBit ingestion. Keep the site on the free plan unless a paid upgrade is authorized.

To disable collection, remove only this Worker's routes and set TOLLBIT_ANALYTICS=0 before regenerating/publishing privacy.html. Preserve other Workers, site data and DNS.
