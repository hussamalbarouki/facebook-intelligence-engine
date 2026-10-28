"""Docker acceptance test of real headed Chromium profile persistence.

No Facebook request/account is involved. Exits/fully reopens Chromium and
confirms cookies survive as files on the mounted user-data directory.
"""
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory(prefix='fb-profile-test-') as d:
    profile=str(Path(d)/'profile')
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(
            profile,headless=False,args=['--no-first-run','--disable-dev-shm-usage'])
        ctx.add_cookies([{'name':'test_persist','value':'persistent-no-real-account',
                         'domain':'.facebook.com','path':'/','secure':True}])
        before=ctx.cookies(['https://www.facebook.com/'])
        assert any(c['name']=='test_persist' for c in before),before
        ctx.close()
    # A completely new Playwright process & browser must read the same file.
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(
            profile,headless=False,args=['--no-first-run','--disable-dev-shm-usage'])
        after=ctx.cookies(['https://www.facebook.com/'])
        assert any(c['name']=='test_persist' and
                   c['value']=='persistent-no-real-account' for c in after),after
        ctx.close()
    assert any(Path(profile).iterdir())
print('Headed Chromium durable profile save/restart/reopen smoke OK')
