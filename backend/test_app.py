import io
import re
import pytest
from PIL import Image
from werkzeug.security import generate_password_hash
from app import create_app

BASE = 'https://media.l3gh.com'


@pytest.fixture
def client(tmp_path):
    app = create_app(dict(TESTING=True, DATA=str(tmp_path), SECRET_KEY='s' * 40,
                          PASSWORD_HASH=generate_password_hash('test-only-passphrase')))
    return app.test_client()


def token(client):
    r = client.get('/fabi/admin/login', base_url=BASE)
    return re.search(r'name="csrf" value="([^"]+)"', r.text)[1]


def login(client, username='zavvrel'):
    csrf = token(client)
    return client.post('/fabi/admin/login', base_url=BASE, headers={'Origin': BASE},
                       data=dict(csrf=csrf, username=username, password='test-only-passphrase'))


def state(client):
    doc = client.get('/fabi/api/content', base_url=BASE).json
    with client.session_transaction(base_url=BASE) as s:
        csrf = s['csrf']
    return doc['document'], doc['revision'], csrf


def test_auth_and_session_security(client):
    assert client.get('/fabi/admin/login', base_url=BASE).headers['Referrer-Policy'] == 'same-origin'
    assert client.get('/fabi/admin', base_url=BASE).status_code == 302
    assert client.post('/fabi/admin/save', base_url=BASE).status_code == 403
    assert login(client, 'outsider').status_code == 200
    r = login(client)
    assert r.status_code == 302
    cookie = r.headers['Set-Cookie']
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
    assert client.get('/fabi/admin', base_url=BASE).status_code == 200


def test_both_accounts(client):
    assert login(client, 'l3gh').status_code == 302


def test_save_origin_csrf_and_conflict(client):
    login(client)
    doc, revision, csrf = state(client)
    form = dict(csrf=csrf, revision=revision, section='page', title='For you', intro='line one\nline two', signature='fabi', hint='tap')
    assert client.post('/fabi/admin/save', base_url=BASE, data=form, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/fabi/admin/save', base_url=BASE, data={**form, 'csrf': 'wrong'}, headers={'Origin': BASE}).status_code == 403
    assert client.post('/fabi/admin/save', base_url=BASE, data=form, headers={'Origin': BASE}).status_code == 302
    assert state(client)[0]['title'] == 'For you'
    r = client.post('/fabi/admin/save', base_url=BASE, data={**form, 'title': 'My unsaved words'}, headers={'Origin': BASE})
    assert r.status_code == 400 and 'My unsaved words' in r.text
    assert state(client)[0]['title'] == 'For you'


def test_unsafe_link_retains_words(client):
    login(client)
    doc, revision, csrf = state(client)
    form = dict(csrf=csrf, revision=revision, section='0', title='My letter', text='Keep my words', link='javascript:alert(1)', link_label='hello')
    r = client.post('/fabi/admin/save', base_url=BASE, data=form, headers={'Origin': BASE})
    assert r.status_code == 400 and 'Keep my words' in r.text
    assert state(client)[0]['drawers'][0]['link'] == ''


def test_upload_caption_remove_and_reject_nonimage(client):
    login(client)
    _, revision, csrf = state(client)
    r = client.post('/fabi/admin/upload/1', base_url=BASE, headers={'Origin': BASE},
                    data=dict(csrf=csrf, revision=revision, photo=(io.BytesIO(b'not image'), 'x.jpg')))
    assert r.status_code == 400
    stream = io.BytesIO()
    Image.new('RGB', (30, 20), 'pink').save(stream, 'PNG')
    stream.seek(0)
    r = client.post('/fabi/admin/upload/1', base_url=BASE, headers={'Origin': BASE},
                    data=dict(csrf=csrf, revision=revision, photo=(stream, 'photo.png')))
    assert r.status_code == 302
    doc, revision, csrf = state(client)
    photo = doc['drawers'][1]['photos'][0]['id']
    assert client.get('/fabi/media/' + photo + '.webp', base_url=BASE).mimetype == 'image/webp'
    r = client.post('/fabi/admin/save', base_url=BASE, headers={'Origin': BASE}, data={
        'csrf': csrf, 'revision': revision, 'section': '1', 'title': 'Memories', 'text': 'hello',
        'caption_' + photo: 'Our memory', 'alt_' + photo: 'Two people', 'remove': photo})
    assert r.status_code == 302
    assert client.get('/fabi/media/' + photo + '.webp', base_url=BASE).status_code == 404


def test_logout_and_throttling(client):
    login(client)
    _, _, csrf = state(client)
    assert client.post('/fabi/admin/logout', base_url=BASE, headers={'Origin': BASE}, data={'csrf': csrf}).status_code == 302
    assert client.get('/fabi/admin', base_url=BASE).status_code == 302
    csrf = token(client)
    for _ in range(16):
        r = client.post('/fabi/admin/login', base_url=BASE, headers={'Origin': BASE},
                        data={'csrf': csrf, 'username': 'zavvrel', 'password': 'wrong'})
    assert r.status_code == 429
