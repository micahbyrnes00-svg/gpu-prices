# Limited TollBit analytics

This Worker passes through the original response and sends a background log for GET/HEAD requests to the public homepage, flat HTML pages and selected discovery files. It excludes query strings, referrers, cookies, authorization headers, location fields, API/MCP routes and key pages. Log delivery failure does not change the response.

Keep TOLLBIT_LOG_KEY in a Cloudflare secret binding. Never commit it. The checked-in Wrangler configuration deliberately has no site routes; publish the matching privacy notice with TOLLBIT_ANALYTICS=1 and verify it before attaching public routes. Disable invocation logs to avoid storing full URLs. Use fail-open routes where supported, and stay within the free-plan request quota unless an upgrade is approved.

Run `node --test deploy/tollbit-analytics-worker.test.mjs` before deployment. Verify TollBit receives the reduced schema. Analytics does not activate paid content licenses, rates or payouts; those require separate eligibility and rights checks.
