"""Encrypted persisted Playwright session snapshot, in addition to Chrome profile.

Chrome intentionally drops non-persistent session cookies on full exit. Save
cookies/localStorage to encrypted /data state, and restore cookies to the SAME
persistent Chrome context before navigating Facebook. Never log or serialize
secret values into API responses.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from cryptography.fernet import Fernet,InvalidToken

STATE_NAME='facebook-profile-state.enc'

def _cipher(base):
    base=Path(base)
    base.mkdir(parents=True,exist_ok=True)
    path=base/'cookie-encryption.key'
    if not path.exists():
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
        except FileExistsError:
            pass
    return Fernet(path.read_bytes())

def _valid_facebook_cookie(item):
    domain=str(item.get('domain','')).lstrip('.').lower()
    return domain=='facebook.com' or domain.endswith('.facebook.com')

def save_state(context,base):
    """Save state in-memory, then atomically encrypt; no plaintext temp file."""
    state=context.storage_state()
    if not isinstance(state,dict) or not isinstance(state.get('cookies'),list):
        raise RuntimeError('INVALID_BROWSER_STORAGE_STATE')
    # Only Facebook cookies and Facebook localStorage; don't mix unrelated
    # accounts into the snapshot of this dedicated browser.
    state['cookies']=[c for c in state['cookies'] if _valid_facebook_cookie(c)]
    def facebook_origin(item):
        if not isinstance(item,dict):return False
        try:
            u=urlsplit(item.get('origin',''))
            return u.scheme=='https' and _valid_facebook_cookie({'domain':u.hostname or ''})
        except (TypeError,ValueError):return False
    state['origins']=[o for o in state.get('origins',[]) if facebook_origin(o)]
    encrypted=_cipher(base).encrypt(
        json.dumps(state,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    fd,tmp=tempfile.mkstemp(prefix='fb-browser-state-',dir=str(base))
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as f:
            f.write(encrypted)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,Path(base)/STATE_NAME)
    finally:
        try:os.unlink(tmp)
        except FileNotFoundError:pass
    names={c.get('name') for c in state['cookies']}
    return {'c_user','xs'}.issubset(names)

def restore_state(context,base):
    """Reinject session cookies that Chrome drops on a graceful exit."""
    path=Path(base)/STATE_NAME
    if not path.is_file():return False
    try:
        data=json.loads(_cipher(base).decrypt(path.read_bytes()))
        cookies=[dict(c) for c in data.get('cookies',[]) if
                 isinstance(c,dict) and _valid_facebook_cookie(c)]
        for c in cookies:
            if c.get('expires',0) is None or c.get('expires',0)<0:
                c.pop('expires',None)
        if cookies:
            context.add_cookies(cookies)
        return bool(cookies)
    except (InvalidToken,ValueError,TypeError,KeyError,OSError):
        raise RuntimeError('BROWSER_STORAGE_STATE_INVALID') from None
