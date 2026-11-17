# Gift-site content service

Runs separately from Dani's media app on the same VPS. Public content and images are under `https://media.l3gh.com/fabi/`. The gift site's Vercel config proxies content/images and redirects `/admin` to the private editor.

The login usernames are `l3gh` and `zavvrel`. Both use a separate site-editor password, not a GitHub password. This is password authentication, not GitHub identity verification. The password hash and random Flask signing secret live only in root-readable `/etc/fabi-content.env`. Neither is sent to the public site. Set `FABI_PASSWORD_HASH` to a Werkzeug scrypt password hash; blank/missing disables login. Changing the signing secret revokes all existing sessions.

Service `fabi-content` binds only `127.0.0.1:7200` as its own Unix user. Caddy routes `/fabi/*` to it and overwrites X-Real-IP for login throttling. It does not grant access to Dani's existing owner-only admin or database.

Persistent content: `/var/lib/fabi-content/content.sqlite`; images: `/var/lib/fabi-content/images`. Keep runtime state, credentials and backups out of Git and Vercel. Back up the directory with SQLite's backup API for the database and copy images. Removed photos are no longer publicly served but remain on disk for recovery. Do not restore an old database over newer edits casually.

The deployed `fabi-content-backup.timer` runs a daily local backup to `/var/backups/fabi-content`, retaining seven snapshots. There is no off-server backup configured.

Each section saves immediately and requires the current document revision. Conflicting saves retain entered form text. Save unsaved text before uploading a photo or switching sections. Photos are re-encoded to WebP, stripped of metadata, bounded to 2000 pixels and limited to 8 MB / 16 megapixels at upload. Each drawer supports 20 photos; total image storage is capped at 512 MiB. Public content is intentionally visible to anyone who can visit the gift site. Only editing requires sign-in.

Deploy tracked backend files to `/opt/fabi-content`, then run `deploy.sh` as root. It preserves runtime data and existing environment configuration. It adds only a scoped Caddy route, with a before-change backup, and validates configuration before reload. Frontend changes go through the upstream gift repository's PR and Vercel deployment.

Validation: `python -m pytest -q` from backend/. Tests use temporary data and test-only credentials. They do not verify a real production password login.

Deployment verification on 2026-11-17: six backend tests passed on Linux and Windows; both editor usernames signed in successfully over real HTTPS. Following a temporary VPS outage, service health and both logins were reverified. A real Chromium browser signed in to production and checked all five editor tabs on a phone viewport. Optional browser regression passed at 390/1440px with a temporary backend and intercepted HTTP: active sections, unsaved-word warning, form save, photo upload and caption save, public text escaping, playlist rendering and touch drawers. No production content was changed in these tests. Admin uses same-origin referrer policy so browser POST Origin checks work; public responses use no-referrer. The frontend Vercel connection is proposed through a PR, not merged by this deployment. Never report the public gift page as connected until that PR is merged and verified.
