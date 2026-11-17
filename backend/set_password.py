"""Root-only password setup. Read a secret from stdin; never print it."""
import os
import secrets
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash

password = sys.stdin.read().rstrip('\r\n')
if len(password) < 12 or len(password) > 256 or '\n' in password or '\r' in password:
    raise SystemExit('Use a single-line passphrase between 12 and 256 characters.')
path = Path('/etc/fabi-content.env')
values = dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)
values['FABI_PASSWORD_HASH'] = generate_password_hash(password)
values['FABI_SESSION_SECRET'] = secrets.token_urlsafe(48)
temporary = path.with_suffix('.env.new')
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    for key, value in values.items():
        f.write(key + '=' + value + '\n')
os.chmod(temporary, 0o600)
os.replace(temporary, path)
print('Editor password configured; existing sessions revoked.')
