# Server login (prepared; not activated)

Requires `nodejs_compat`; password/file derivation uses the Node crypto API instead of the lower-capped WebCrypto PBKDF2 API. Test CPU limits in the live free-plan runtime before activation.

This optional gateway serves the same dashboard with one owner email/password and HttpOnly sessions. It holds GitHub and data keys on the server. It is not an open multi-user registration system. GitHub Pages continues to work unchanged until the gateway is deployed.

Activation needs a Cloudflare Worker plus a D1 DB binding initialized with schema.sql. The direct dashboard deployment serves the existing GitHub Pages HTML/assets through a fixed upstream; the optional bundled deployment uses an ASSETS binding containing index.html and assets/. Do not include data/, reports/, or secrets in static assets. Secret bindings: AUTH_EMAIL, AUTH_PASSWORD (entered directly as an encrypted runtime secret), or AUTH_PASSWORD_HASH (generated locally with password-hash.mjs), GITHUB_TOKEN (only this repository, Contents/Actions read/write), RADAR_KEY. The owner must enter the password and credentials directly into the service. No credential belongs in this repository. The existing GitHub engine still executes searches and delivers notifications.

Run `node --test gateway/worker.test.mjs`. Before activation, verify in the deployed Worker that legacy 250,000-iteration encrypted files can be opened within its runtime limits, log in/out from two devices, test session expiry, stale-save conflicts, and actual GitHub dispatch permissions. Do not redirect the existing URL before those checks pass. New saves use the same AES-GCM envelope with 250,000 PBKDF2 iterations; existing 250,000-iteration files remain supported by the reader. No password reset/recovery or additional users are enabled.

## Production data key (required)

Cloudflare rejects PBKDF2 above 100,000 rounds (`NotSupportedError`, confirmed in the production logs on 19 Oct 2026), and the data uses 250,000. So the Worker never derives the data key: it reads `RADAR_DATA_KEY` = `<salt>:<key>`, the 250,000-round key for `user.enc`'s salt. Create it on the GitHub Pages dashboard (Settings → إنشاء مفتاح الخادم, signed in with the data password) and store it as a Cloudflare secret. The engine, the dashboard and the Worker all write with that salt, and each engine round moves older files onto it, so one key opens everything. `RADAR_KEY` is then unused by the Worker. `AUTH_PASSWORD_HASH` (600,000 rounds) hits the same cap, so use `AUTH_PASSWORD`.

## Free-plan CPU budget

A free Worker gets about 10 ms of CPU per request; one 250,000-round PBKDF2 costs several times that. The Worker keeps derived data keys per isolate, and the engine, the dashboard and the Worker now reuse the salt of the data they opened when they write (a fresh IV every time), so after the next search round all files share one key and a warm isolate derives it once. The first request on a cold isolate still derives one key; if Cloudflare reports `Exceeded CPU Time Limits`, the dashboard says so and asks to retry. Encryption strength is unchanged.

`gateway/worker.mjs` is the deployed source. After it changes, paste it into the Cloudflare editor for `car-radar-gateway` (Edit code → replace → Deploy); nothing deploys it automatically.

Local end-to-end check before deploying: `node --test gateway/worker.test.mjs` covers large files (engine data and PDFs were failing with a stack overflow before), files over the 1 MB contents-API limit, and salt reuse.
