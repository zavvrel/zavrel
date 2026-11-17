"""Daily local backup. Image files are immutable and retained after removal."""
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

os.umask(0o077)
source = Path('/var/lib/fabi-content')
root = Path('/var/backups/fabi-content')
root.mkdir(mode=0o700, parents=True, exist_ok=True)
destination = root / datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
destination.mkdir(mode=0o700)
with sqlite3.connect(source / 'content.sqlite') as original:
    with sqlite3.connect(destination / 'content.sqlite') as target:
        original.backup(target)
shutil.copytree(source / 'images', destination / 'images')
for old in sorted(root.iterdir(), reverse=True)[7:]:
    if old.is_dir() and old.parent == root and len(old.name) == 15:
        shutil.rmtree(old)
