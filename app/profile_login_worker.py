"""Runs the interactive Facebook login in its own process.

Playwright's persistent Chrome profile is exclusively held by this worker
while the login session is open. SIGTERM requests graceful close so Chromium
flushes cookies, IndexedDB and local storage to the durable /data volume.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import time

from playwright.sync_api import sync_playwright

BASE=Path(os.environ.get('DATA_DIR','/data'))
PROFILE=BASE/'facebook-profile'
MARKER=BASE/'facebook-profile-ready.json'
STOP=False

def stop(_signal,_frame):
    global STOP
    STOP=True

signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)

def main():
    PROFILE.mkdir(mode=0o700,parents=True,exist_ok=True)
    PROFILE.chmod(0o700)
    with sync_playwright() as pw:
        context=pw.chromium.launch_persistent_context(
            str(PROFILE),headless=False,viewport={'width':1270,'height':800},
            args=['--disable-dev-shm-usage','--no-first-run',
                  '--no-default-browser-check','--disable-gpu'])
        try:
            page=context.pages[0] if context.pages else context.new_page()
            try:page.goto('https://www.facebook.com/',wait_until='domcontentloaded',timeout=20000)
            except Exception:pass
            while not STOP:
                time.sleep(0.3)
            cookies=context.cookies(['https://www.facebook.com/'])
            names={c.get('name') for c in cookies}
            authenticated={'c_user','xs'}.issubset(names)
        finally:
            context.close()
    # Write readiness ONLY after the browser fully exits. A marker alone is
    # not proof Facebook accepts the session, and must never contain secrets.
    if authenticated:
        tmp=BASE/'facebook-profile-ready.tmp'
        tmp.write_text(json.dumps({'saved':True,'format':1}),encoding='utf-8')
        tmp.chmod(0o600)
        tmp.replace(MARKER)
    elif MARKER.exists():
        MARKER.unlink()
    print('Facebook browser profile saved; required login cookies present:',authenticated,flush=True)

if __name__=='__main__':
    main()
