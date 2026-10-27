"""Conservative, redacted Facebook session diagnostics and token bootstrap.

This module never stores raw Facebook response bodies, session cookies or CSRF
values in API responses/logs. A successful preflight is not proof that every
GraphQL query, post, or reaction list is accessible.
"""
from __future__ import annotations
import html as html_module
import json
import re
from urllib.parse import urlsplit

import requests

# Facebook changes its hydration format; do not assume one legacy pattern.
_JSON_STRING = r'((?:\\.|[^"\\]){8,512})'
_TOKEN_PATTERNS = (
    re.compile(r'\{"name":"fb_dtsg","value":"' + _JSON_STRING + r'"'),
    re.compile(r'\["DTSGInitialData",\[\],\{"token":"' + _JSON_STRING + r'"'),
    re.compile(r'\["DTSGInitData",\[\],\{"token":"' + _JSON_STRING + r'"'),
    re.compile(r'"DTSGInitialData".{0,500}?"token"\s*:\s*"' + _JSON_STRING + r'"', re.S),
    re.compile(r'"DTSGInitData".{0,500}?"token"\s*:\s*"' + _JSON_STRING + r'"', re.S),
    re.compile(r'\bname=["\']fb_dtsg["\'][^>]{0,400}\bvalue=["\']([^"\']{8,512})["\']', re.I),
    re.compile(r'\bvalue=["\']([^"\']{8,512})["\'][^>]{0,400}\bname=["\']fb_dtsg["\']', re.I),
)
BOOTSTRAP_URLS = (
    'https://www.facebook.com/',
    'https://web.facebook.com/',
    'https://www.facebook.com/settings/',
)


def extract_dtsg(html: str) -> str | None:
    if not isinstance(html, str):
        return None
    for pattern in _TOKEN_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        raw = match.group(1)
        try:
            token = json.loads('"' + raw + '"')
        except (ValueError, TypeError):
            token = html_module.unescape(raw)
        if isinstance(token, str) and 8 <= len(token) <= 512 and not any(c.isspace() for c in token):
            return token
    return None


def _page_status(response) -> str:
    url = str(getattr(response, 'url', '')).lower()
    text = str(getattr(response, 'text', ''))
    low = text[:100000].lower()
    code = int(getattr(response, 'status_code', 0) or 0)
    if code == 400:
        return 'facebook_http_bad_request'
    if code in (401, 403, 429):
        return 'facebook_access_restricted'
    if '/checkpoint/' in url or '/two_step_verification/' in url or 'checkpoint' in url:
        return 'facebook_checkpoint'
    if '/login' in url or ('name="email"' in low and 'name="pass"' in low):
        return 'facebook_login_required'
    if 'security check' in low and 'facebook' in low:
        return 'facebook_checkpoint'
    return 'token_not_found'


def inspect_session(request_get):
    """Return (sanitized report, secret token). Never expose the latter via API."""
    observations = []
    for url in BOOTSTRAP_URLS:
        try:
            response = request_get(url)
            code = int(getattr(response, 'status_code', 0) or 0)
            if code > 0:
                token = extract_dtsg(getattr(response, 'text', ''))
                state = 'token_found' if token else _page_status(response)
                observations.append({'source':urlsplit(url).hostname,'http_status':code,'state':state})
                if token:
                    return ({'status':'token_available','token_available':True,'checked':observations,
                             'note':'This does not guarantee post/comment/reaction access.'}, token)
            else:
                observations.append({'source':urlsplit(url).hostname,'state':'invalid_response'})
        except requests.RequestException:
            observations.append({'source':urlsplit(url).hostname,'state':'connection_error'})
        except Exception as exc:
            if type(exc).__name__ == 'SessionExpiredError':
                observations.append({'source':urlsplit(url).hostname,'state':'facebook_login_required'})
                continue
            # Never put exception text into API response: some libraries include request data.
            observations.append({'source':urlsplit(url).hostname,'state':'bootstrap_error'})
    states = [o['state'] for o in observations]
    for typ in ('facebook_checkpoint','facebook_access_restricted','facebook_login_required'):
        if typ in states:
            return ({'status':typ,'token_available':False,'checked':observations},None)
    if states and all(s in ('connection_error','bootstrap_error','invalid_response') for s in states):
        return ({'status':'facebook_connection_error','token_available':False,'checked':observations},None)
    return ({'status':'fb_dtsg_unavailable','token_available':False,'checked':observations},None)


def configure_facebook_session(session):
    """Use the Requests default User-Agent confirmed to receive HTTP 200.

    The legacy GraphQL adapter sends a fabricated Chrome identity with browser
    client hints; this VPS's Facebook responses reject the tested Chrome UA.
    Do not pretend to be another browser or mix inconsistent sec-ch headers.
    """
    for name in list(session.headers):
        if name.lower().startswith(('sec-ch-ua', 'sec-fetch-')) or name.lower() == 'priority':
            session.headers.pop(name, None)
    session.headers['User-Agent'] = requests.utils.default_headers()['User-Agent']
    session.headers['Accept-Language'] = 'en-US,en;q=0.8'
    return session


def probe_cookie_file(cookie_path: str | None):
    if not cookie_path:
        return {'status':'cookies_not_configured','token_available':False}
    try:
        with open(cookie_path,encoding='utf-8') as handle:
            raw=json.load(handle)
        if not isinstance(raw,list):
            return {'status':'cookies_format_invalid','token_available':False}
        names={x.get('name') for x in raw if isinstance(x,dict)}
        if not {'c_user','xs'}.issubset(names):
            return {'status':'cookies_missing_required_names','token_available':False}
        cookie_count=len(raw)
        with requests.Session() as session:
            configure_facebook_session(session)
            for cookie in raw:
                name, value = cookie.get('name'), cookie.get('value')
                if not isinstance(name,str) or not isinstance(value,str):
                    continue
                session.cookies.set(name,value,domain='.facebook.com',path='/')
            result,_=inspect_session(lambda url:session.get(url,timeout=(4,12),allow_redirects=True))
            result['cookie_count']=cookie_count
            if cookie_count<=2 and not result['token_available']:
                result['hint']='Export the complete Facebook cookie JSON from your authenticated browser; c_user and xs alone may not be enough.'
            return result
    except (ValueError,TypeError,OSError):
        return {'status':'cookies_format_invalid','token_available':False}