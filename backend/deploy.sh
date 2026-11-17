#!/bin/sh
set -eu
# Run on the existing VPS, after copying backend/ to /opt/fabi-content.
id fabi-content >/dev/null 2>&1 || useradd --system --home /var/lib/fabi-content --shell /usr/sbin/nologin fabi-content
install -d -o fabi-content -g fabi-content -m 750 /var/lib/fabi-content
python3 -m venv /opt/fabi-content/.venv
/opt/fabi-content/.venv/bin/pip -q install -r /opt/fabi-content/requirements.txt
chmod -R a+rX /opt/fabi-content
if [ ! -f /etc/fabi-content.env ]; then
  python3 - <<'PY'
import os, secrets
fd = os.open('/etc/fabi-content.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write('FABI_SESSION_SECRET=' + secrets.token_urlsafe(48) + '\nFABI_DATA=/var/lib/fabi-content\n')
PY
fi
cat >/etc/systemd/system/fabi-content.service <<'UNIT'
[Unit]
Description=Fabi gift site content editor
After=network.target
[Service]
User=fabi-content
Group=fabi-content
WorkingDirectory=/opt/fabi-content
EnvironmentFile=/etc/fabi-content.env
ExecStart=/opt/fabi-content/.venv/bin/gunicorn --bind 127.0.0.1:7200 --workers 2 --threads 2 --timeout 45 --access-logfile /dev/null app:create_app()
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/fabi-content
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl reset-failed fabi-content || true
systemctl enable --now fabi-content
systemctl restart fabi-content
python3 - <<'PY'
from pathlib import Path
import shutil
p = Path('/etc/caddy/Caddyfile')
s = p.read_text()
s = s.replace('request_body { max_size 9MB }', 'request_body {\n            max_size 9MB\n        }')
marker = 'media.l3gh.com {\n'
route = '''    handle /fabi/* {
        request_body {
            max_size 9MB
        }
        reverse_proxy 127.0.0.1:7200 {
            header_up X-Real-IP {remote_host}
        }
    }
'''
if 'reverse_proxy 127.0.0.1:7200' not in s:
    if marker not in s:
        raise SystemExit('Expected media site block not found; no Caddy changes made')
    shutil.copy2(p, '/etc/caddy/Caddyfile.before-fabi')
    s = s.replace(marker, marker + route, 1)
p.write_text(s)
PY
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
cat >/etc/systemd/system/fabi-content-backup.service <<'UNIT'
[Unit]
Description=Back up Fabi gift site content and photos
[Service]
Type=oneshot
ExecStart=/opt/fabi-content/.venv/bin/python /opt/fabi-content/backup.py
UMask=0077
UNIT
cat >/etc/systemd/system/fabi-content-backup.timer <<'UNIT'
[Unit]
Description=Daily Fabi gift site backup
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now fabi-content-backup.timer
