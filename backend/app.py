"""Isolated content service. Runtime data and credentials must stay outside Git."""
import copy
import io
import json
import os
import secrets
import sqlite3
import time
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, redirect, render_template, request, session, send_file
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash

PREFIX = '/fabi'
DEFAULT = dict(title='For Nati', intro='A few little things, just for you.\nTap a drawer to look inside.',
               signature='With love, fabi ♡', hint='Tap an open drawer again to close it.', drawers=[
    dict(title='A letter for you', text='Dear Nati,\nThis little corner of the internet is for you.\n\nExample text for now. Your own letter will go here.', link='', link_label='Open link', photos=[]),
    dict(title='Our little memories', text='A place for your favourite moments. We can add your own words and photos here.', link='', link_label='Open link', photos=[]),
    dict(title='Things I love about you', text='Your own list will go here. These drawer names can change too.', link='', link_label='Open link', photos=[]),
    dict(title='A little gift for you', text='A little collection of songs to keep.', gift_heading='A playlist, just for you', link='', link_label='Listen on Spotify', placeholder='Playlist coming soon', photos=[]),
])


def create_app(config=None):
    app = Flask(__name__, static_url_path=PREFIX + '/static')
    app.config.update(SECRET_KEY=os.environ.get('FABI_SESSION_SECRET', ''),
                      DATA=os.environ.get('FABI_DATA', '/var/lib/fabi-content'),
                      PASSWORD_HASH=os.environ.get('FABI_PASSWORD_HASH', ''),
                      ORIGIN='https://media.l3gh.com', SITE='https://zavrel.vercel.app',
                      MAX_CONTENT_LENGTH=9 * 1024 * 1024, MAX_FORM_PARTS=200,
                      SESSION_COOKIE_NAME='__Host-fabi', SESSION_COOKIE_SECURE=True,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    if config:
        app.config.update(config)
    if len(app.config['SECRET_KEY']) < 32:
        raise RuntimeError('A private session secret of at least 32 characters is required')
    data = Path(app.config['DATA'])
    data.mkdir(parents=True, exist_ok=True)
    (data / 'images').mkdir(exist_ok=True)

    def db():
        c = sqlite3.connect(data / 'content.sqlite', timeout=20)
        c.row_factory = sqlite3.Row
        return c

    with db() as c:
        c.executescript('CREATE TABLE IF NOT EXISTS content(id INTEGER PRIMARY KEY, revision INTEGER, document TEXT);'
                       'CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY, start INTEGER, count INTEGER);')
        c.execute('INSERT OR IGNORE INTO content VALUES(1,1,?)', (json.dumps(DEFAULT),))
    dummy_hash = generate_password_hash(secrets.token_urlsafe(32))

    def read():
        with db() as c:
            row = c.execute('SELECT * FROM content WHERE id=1').fetchone()
        return json.loads(row['document']), row['revision']

    def save(document, revision):
        with db() as c:
            result = c.execute('UPDATE content SET document=?,revision=revision+1 WHERE id=1 AND revision=?',
                               (json.dumps(document), revision))
            if result.rowcount != 1:
                raise ValueError('Someone saved a newer change. Your words are still below. Copy them, reload this page, then try again.')

    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        return session['csrf']

    def rate(key, maximum, seconds):
        now = int(time.time())
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM limits WHERE start<?', (now - 86400,))
            row = c.execute('SELECT * FROM limits WHERE key=?', (key,)).fetchone()
            start, count = (row['start'], row['count'] + 1) if row and row['start'] > now - seconds else (now, 1)
            c.execute('INSERT OR REPLACE INTO limits VALUES(?,?,?)', (key, start, count))
        if count > maximum:
            abort(429)

    @app.before_request
    def security():
        if request.path.startswith(PREFIX + '/admin'):
            if request.method == 'POST':
                if request.headers.get('Origin') != app.config['ORIGIN']:
                    abort(403)
                if not session.get('csrf') or not secrets.compare_digest(request.form.get('csrf', ''), session['csrf']):
                    abort(403)
            if request.path != PREFIX + '/admin/login' and session.get('user') not in ('l3gh', 'zavvrel'):
                return redirect(PREFIX + '/admin/login') if request.method == 'GET' else ('Please sign in again.', 401)

    @app.after_request
    def headers(response):
        response.headers.update({'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'same-origin' if request.path.startswith(PREFIX + '/admin') else 'no-referrer',
                                 'X-Frame-Options': 'DENY', 'Cache-Control': 'no-store',
                                 'Content-Security-Policy': "default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    @app.errorhandler(413)
    def too_large(error):
        return 'That photo is too large. Choose a photo under 8 MB, go back, and try again.', 413

    @app.errorhandler(429)
    def too_many(error):
        return 'Too many attempts. Please wait 15 minutes before trying again.', 429

    @app.get(PREFIX + '/health')
    def health():
        read()
        return jsonify(status='ok')

    @app.route(PREFIX + '/admin/login', methods=['GET', 'POST'])
    def login():
        error = None
        if request.method == 'POST':
            # Caddy forwards a sanitized peer header; direct clients only reach loopback.
            peer = request.headers.get('X-Real-IP', request.remote_addr)
            rate('login:' + peer, 15, 900)
            user = request.form.get('username', '').strip().lower()
            configured_hash = app.config['PASSWORD_HASH']
            valid = check_password_hash(configured_hash or dummy_hash, request.form.get('password', ''))
            if configured_hash and valid and user in ('l3gh', 'zavvrel'):
                session.clear()
                session['user'] = user
                session.permanent = True
                csrf()
                return redirect(PREFIX + '/admin')
            error = 'The username or password did not match. Please try again.'
        return render_template('login.html', error=error, csrf=csrf(), prefix=PREFIX)

    def editor(document=None, revision=None, error=None, saved=None, selected=None):
        if document is None:
            document, revision = read()
        selected = selected or request.form.get('section') or request.args.get('section', 'page')
        if selected not in ('page', '0', '1', '2', '3'):
            selected = 'page'
        return render_template('editor.html', doc=document, revision=revision, error=error, saved=saved, selected=selected,
                               csrf=csrf(), prefix=PREFIX, user=session['user'], site=app.config['SITE'])

    @app.get(PREFIX + '/admin', strict_slashes=False)
    def admin():
        return editor(saved=request.args.get('saved'))

    def text(name, maximum, required=False):
        value = request.form.get(name, '').strip()
        if len(value) > maximum or (required and not value):
            raise ValueError('Please fill in the required fields and keep text within the shown limits.')
        return value

    def url(value):
        if not value:
            return ''
        p = urlsplit(value)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or any(ord(ch) < 33 for ch in value) or '\\' in value:
            raise ValueError('Links must start with https:// and be a complete website address.')
        return value

    @app.post(PREFIX + '/admin/save')
    def edit():
        document, current_revision = read()
        revision = request.form.get('revision', type=int)
        section = request.form.get('section', '')
        try:
            if section == 'page':
                for key, maximum in [('title', 120), ('intro', 1000), ('signature', 160), ('hint', 200)]:
                    document[key] = text(key, maximum, key == 'title')
            elif section in ('0', '1', '2', '3'):
                drawer = document['drawers'][int(section)]
                for key, maximum in [('title', 120), ('text', 30000), ('link', 2048), ('link_label', 100)]:
                    drawer[key] = text(key, maximum, key == 'title')
                # Retain entered values if URL validation fails.
                drawer['link'] = url(drawer['link'])
                if int(section) == 3:
                    drawer['gift_heading'] = text('gift_heading', 160)
                    drawer['placeholder'] = text('placeholder', 100)
                photos = drawer['photos']
                for photo in photos:
                    photo['caption'] = text('caption_' + photo['id'], 1000)
                    photo['alt'] = text('alt_' + photo['id'], 500)
                remove = set(request.form.getlist('remove'))
                drawer['photos'] = [p for p in photos if p['id'] not in remove]
            else:
                abort(400)
            save(document, revision)
        except (ValueError, TypeError) as exc:
            return editor(document, revision or current_revision, str(exc)), 400
        return redirect(PREFIX + '/admin?saved=' + section + '&section=' + section)

    @app.post(PREFIX + '/admin/upload/<int:index>')
    def upload(index):
        if not 0 <= index < 4:
            abort(404)
        document, revision = read()
        rate('upload:' + session['user'], 60, 3600)
        if len(document['drawers'][index]['photos']) >= 20:
            return editor(error='This drawer already has 20 photos. Remove one before adding another.', selected=str(index)), 400
        f = request.files.get('photo')
        path = None
        try:
            if not f or not f.filename:
                raise ValueError('Choose a photo first.')
            raw = f.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError('Choose a photo under 8 MB.')
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 16_000_000 or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Choose a still JPG, PNG or WebP photo under 16 megapixels.')
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((2000, 2000))
                ident = uuid.uuid4().hex
                path = data / 'images' / (ident + '.webp')
                if sum(p.stat().st_size for p in (data / 'images').glob('*.webp')) > 512 * 1024 * 1024:
                    raise ValueError('Photo storage is full. Ask Dani for help.')
                image.save(path, 'WEBP', quality=86)
            document['drawers'][index]['photos'].append(dict(id=ident, caption='', alt=''))
            save(document, request.form.get('revision', type=int))
        except (ValueError, TypeError, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            if path and path.exists():
                path.unlink()
            message = str(exc) if isinstance(exc, ValueError) else 'That photo could not be read. Choose a JPG, PNG or WebP photo.'
            return editor(error=message, selected=str(index)), 400
        return redirect(PREFIX + '/admin?saved=' + str(index) + '&section=' + str(index))

    @app.post(PREFIX + '/admin/logout')
    def logout():
        session.clear()
        return redirect(PREFIX + '/admin/login')

    @app.get(PREFIX + '/api/content')
    def content():
        document, revision = read()
        response = jsonify(document=document, revision=revision)
        return response

    @app.get(PREFIX + '/media/<ident>.webp')
    def media(ident):
        if len(ident) != 32 or any(ch not in '0123456789abcdef' for ch in ident):
            abort(404)
        document, revision = read()
        if not any(p['id'] == ident for d in document['drawers'] for p in d['photos']):
            abort(404)
        return send_file(data / 'images' / (ident + '.webp'), mimetype='image/webp', conditional=True)

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=7200)
