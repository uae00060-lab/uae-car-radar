# Server login (prepared; not activated)

Requires `nodejs_compat`; password/file derivation uses the Node crypto API instead of the lower-capped WebCrypto PBKDF2 API. Test CPU limits in the live free-plan runtime before activation.

This optional gateway serves the same dashboard with one owner email/password and HttpOnly sessions. It holds GitHub and data keys on the server. It is not an open multi-user registration system. GitHub Pages continues to work unchanged until the gateway is deployed.

Activation needs a Cloudflare Worker plus a D1 DB binding initialized with schema.sql. The direct dashboard deployment serves the existing GitHub Pages HTML/assets through a fixed upstream; the optional bundled deployment uses an ASSETS binding containing index.html and assets/. Do not include data/, reports/, or secrets in static assets. Secret bindings: AUTH_EMAIL, AUTH_PASSWORD_HASH (generated locally with password-hash.mjs), GITHUB_TOKEN (only this repository, Contents/Actions read/write), RADAR_KEY. The owner must enter the password and credentials directly into the service. No credential belongs in this repository. The existing GitHub engine still executes searches and delivers notifications.

Run `node --test gateway/worker.test.mjs`. Before activation, verify in the deployed Worker that legacy 250,000-iteration encrypted files can be opened within its runtime limits, log in/out from two devices, test session expiry, stale-save conflicts, and actual GitHub dispatch permissions. Do not redirect the existing URL before those checks pass. New saves use the same AES-GCM envelope with 250,000 PBKDF2 iterations; existing 250,000-iteration files remain supported by the reader. No password reset/recovery or additional users are enabled.
