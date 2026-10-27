"""Encrypted cookie storage. Key lives ONLY in /data, never the public image/repository."""
from __future__ import annotations
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken


def _normalize_cookies(raw):
    if isinstance(raw, dict):
        if 'cookies' in raw and isinstance(raw['cookies'], list):
            raw = raw['cookies']
        else:
            raw = [{'name':k,'value':v,'domain':'.facebook.com'} for k,v in raw.items()]
    if not isinstance(raw, list) or len(raw)>150:
        raise ValueError('Cookies must be a JSON object or an array of up to 150 cookies')
    cleaned = []
    for item in raw:
        if not isinstance(item,dict): raise ValueError('Cookie entries must be objects')
        name, value = item.get('name'),item.get('value')
        domain = item.get('domain') or '.facebook.com'
        if not isinstance(name,str) or not name or len(name)>128 or not isinstance(value,str) or len(value)>4096:
            raise ValueError('Invalid cookie name or value')
        if domain.lstrip('.').lower() not in ('facebook.com','www.facebook.com','m.facebook.com'):
            raise ValueError('Only Facebook cookies are accepted')
        cleaned.append({'name':name,'value':value,'domain':'.facebook.com','path':'/','secure':True})
    names = {c['name'] for c in cleaned}
    if not {'c_user','xs'}.issubset(names):
        raise ValueError('Facebook login cookies c_user and xs are required')
    return cleaned


class CookieVault:
    def __init__(self, storage, data_dir):
        self.store = storage
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True,exist_ok=True)
        path = self.dir/'cookie-encryption.key'
        if not path.exists():
            # Exclusive creation avoids unsafe overwrites on simultaneous startup.
            try:
                fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as f: f.write(Fernet.generate_key())
            except FileExistsError: pass
        key = path.read_bytes()
        self.fernet = Fernet(key)

    def status(self):
        row=self.store.get_secret('facebook_cookies')
        return {'configured':row is not None,'updated_at':row['updated_at'] if row else None,
                'validated_with_facebook':False,
                'message':'Credentials are stored, but validity at Facebook is not verified.' if row else 'Upload c_user and xs through the admin API.'}

    def save(self, raw):
        clean = _normalize_cookies(raw)
        encrypted = self.fernet.encrypt(json.dumps(clean,ensure_ascii=False).encode())
        self.store.store_secret('facebook_cookies',encrypted)
        return self.status()

    def delete(self):
        self.store.delete_secret('facebook_cookies')
        return self.status()

    @contextmanager
    def temporary_cookie_file(self):
        row=self.store.get_secret('facebook_cookies')
        if not row:
            yield None
            return
        try:
            cookies=json.loads(self.fernet.decrypt(row['encrypted_value']))
        except (InvalidToken,ValueError):
            raise RuntimeError('COOKIE_STORAGE_ERROR') from None
        # facebook-scraper accepts JSON Netscape-structured cookies via path.
        # Store only for duration of scraping; never return cookie values via API.
        fd,path=tempfile.mkstemp(prefix='fb-session-',suffix='.json',dir=self.dir)
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(cookies,f)
            yield path
        finally:
            try: os.unlink(path)
            except FileNotFoundError: pass