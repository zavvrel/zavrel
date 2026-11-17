"""Optional browser QA with temporary content and mocked HTTP, no production writes.

Run with BROWSER_EXECUTABLE pointing to an existing Chromium/Edge installation.
Requires the optional playwright Python package. Screenshots go outside the repo.
"""
import json
import os
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from app import DEFAULT, create_app

root = Path(__file__).resolve().parent
output = Path(tempfile.mkdtemp(prefix='fabi-browser-'))
app = create_app(dict(TESTING=True, DATA=str(output / 'data'), SECRET_KEY='test-only-secret' * 3))
client = app.test_client()
with client.session_transaction(base_url='https://media.l3gh.com') as session:
    session['user'] = 'zavvrel'

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('BROWSER_EXECUTABLE'), headless=True)
    page = browser.new_page(viewport={'width': 390, 'height': 844}, has_touch=True)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))

    def admin_route(route):
        from urllib.parse import urlsplit
        url = urlsplit(route.request.url)
        response = client.open(url.path + ('?' + url.query if url.query else ''), base_url='https://media.l3gh.com',
                               method=route.request.method, data=route.request.post_data_buffer, follow_redirects=True,
                               headers={k: v for k, v in route.request.headers.items() if k.lower() in ('origin', 'content-type')})
        route.fulfill(status=response.status_code, body=response.data,
                      headers={k: v for k, v in response.headers if k.lower() not in ('set-cookie', 'content-length')})

    page.route('https://media.l3gh.com/**', admin_route)
    for width in (390, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        for section in ('page', '0', '1', '2', '3'):
            page.goto('https://media.l3gh.com/fabi/admin?section=' + section)
            assert page.locator('main > section').count() == 1
            assert page.locator('nav [aria-current=page]').count() == 1
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(output / f'editor-{width}.png'), full_page=True)
    page.locator('textarea[name=text]').fill('Not saved yet')
    dialogs = []
    def dismiss(dialog):
        dialogs.append(dialog.type)
        dialog.dismiss()
    page.on('dialog', dismiss)
    page.get_by_role('link', name='Page text', exact=True).click()
    assert dialogs == ['beforeunload']
    assert page.locator('textarea[name=text]').input_value() == 'Not saved yet'
    page.get_by_role('button', name='Save drawer 4', exact=True).click()
    page.get_by_role('status').wait_for()
    assert client.get('/fabi/api/content', base_url='https://media.l3gh.com').json['document']['drawers'][3]['text'] == 'Not saved yet'
    page.goto('https://media.l3gh.com/fabi/admin?section=1')
    import io
    from PIL import Image
    photo = io.BytesIO()
    Image.new('RGB', (30, 20), 'pink').save(photo, 'PNG')
    page.locator('input[type=file]').set_input_files(dict(name='test.png', mimeType='image/png', buffer=photo.getvalue()))
    page.get_by_role('button', name='Upload photo to drawer 2', exact=True).click()
    page.get_by_role('status').wait_for()
    assert page.locator('.photo img').count() == 1
    page.locator('textarea[name^=caption_]').fill('A browser-tested memory')
    page.get_by_role('button', name='Save drawer 2', exact=True).click()
    page.get_by_role('status').wait_for()
    assert client.get('/fabi/api/content', base_url='https://media.l3gh.com').json['document']['drawers'][1]['photos'][0]['caption'] == 'A browser-tested memory'
    page.close(run_before_unload=False)

    public = browser.new_page(viewport={'width': 390, 'height': 844}, has_touch=True)
    public.on('pageerror', lambda error: errors.append(str(error)))
    doc = json.loads(json.dumps(DEFAULT))
    doc['drawers'][0]['text'] = 'A letter\n<script>alert(1)</script>'
    doc['drawers'][3]['link'] = 'https://open.spotify.com/playlist/example'

    def public_route(route):
        path = route.request.url.split('demo.invalid', 1)[-1].split('?', 1)[0]
        if path == '/api/content':
            route.fulfill(json={'document': doc, 'revision': 1})
        elif path == '/content.js':
            route.fulfill(path=str(root.parent / 'content.js'), content_type='application/javascript')
        else:
            route.fulfill(path=str(root.parent / 'index.html'), content_type='text/html')

    public.route('https://demo.invalid/**', public_route)
    public.goto('https://demo.invalid/')
    public.get_by_text('Listen on Spotify', exact=True).wait_for(state='attached')
    public.locator('summary').first.tap()
    assert public.get_by_text('<script>alert(1)</script>', exact=False).count() == 1
    assert public.locator('script').count() == 1
    public.locator('summary').last.tap()
    assert public.get_by_role('link', name='Listen on Spotify').get_attribute('href').startswith('https://open.spotify.com/')
    assert public.evaluate('document.documentElement.scrollWidth <= innerWidth')
    public.screenshot(path=str(output / 'public-390.png'), full_page=True)
    assert not errors, errors
    browser.close()
print('Browser QA passed: five tabs at 390/1440px, unsaved-word warning, save, photo upload/caption, text escaping, playlist link and touch drawers.')
print('Screenshots:', output)
