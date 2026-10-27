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
    """Match the minimal Requests headers that succeeded on this VPS.

    The upstream GraphQL client sends web.facebook.com Origin/Referer and a
    synthetic browser fingerprint. Those extra headers are not present in the
    successful authenticated preflight, so avoid carrying them over.
    """
    session.headers.clear()
    session.headers.update(requests.utils.default_headers())
    session.headers['Accept-Language'] = 'en-US,en;q=0.8'
    return session


def apply_facebook_cookies(session, cookies):
    """Load validated browser cookie scopes into RequestsCookieJar, not a dict."""
    for item in cookies:
        if not isinstance(item,dict):
            continue
        name, value = item.get('name'), item.get('value')
        domain = item.get('domain') or '.facebook.com'
        path = item.get('path') or '/'
        host = domain.lstrip('.').lower() if isinstance(domain,str) else ''
        if (not isinstance(name,str) or not isinstance(value,str)
                or not (host == 'facebook.com' or host.endswith('.facebook.com'))
                or not isinstance(path,str) or not path.startswith('/')):
            continue
        session.cookies.set(name,value,domain=domain,path=path,
                            secure=item.get('secure',True) is True)


def _post_response_report(response):
    """Sanitized classification of a single Facebook response, never its body."""
    from urllib.parse import urlsplit
    raw_location = response.headers.get('Location', '')
    parsed_location = urlsplit(raw_location)
    path = (parsed_location.path or '').lower()
    location_host = (parsed_location.hostname or '').lower()
    if '/checkpoint' in path or '/two_step_verification' in path:
        redirect_kind = 'checkpoint'
    elif '/login' in path or '/recover' in path:
        redirect_kind = 'login'
    elif location_host and location_host not in ('facebook.com','www.facebook.com','web.facebook.com','m.facebook.com'):
        redirect_kind = 'external'
    elif raw_location:
        redirect_kind = 'facebook_or_relative'
    else:
        redirect_kind = 'none'
    set_cookie = response.headers.get('set-cookie','').lower()
    set_login = response.headers.get('set-login','').lower()
    cookie_deleted = bool(re.search(r'(?:^|[,\s])c_user=deleted(?:[;,]|$)',set_cookie))
    login_rejected = 'logged-out' in set_login
    body = response.text[:50000].lower()
    login_form = ('name="email"' in body and 'name="pass"' in body)
    code = response.status_code
    if cookie_deleted or login_rejected:
        classification = 'facebook_rejected_login_cookie'
    elif redirect_kind == 'checkpoint':
        classification = 'checkpoint_redirect'
    elif redirect_kind == 'login' or login_form:
        classification = 'login_required_or_wall'
    elif code in (403,429):
        classification = 'request_restricted'
    elif code >= 400:
        classification = 'http_error'
    elif 300 <= code < 400:
        classification = 'redirect'
    elif code == 200:
        classification = 'html_received_not_proof_of_post_access'
    else:
        classification = 'unrecognized'
    return {
        'http_status': code,
        'classification': classification,
        'redirect_kind': redirect_kind,
        'cookie_deletion_requested': cookie_deleted,
        'set_login_logged_out': login_rejected,
        'login_form_seen': login_form,
        'fb_dtsg_in_page': bool(extract_dtsg(response.text[:250000])),
        'content_type': response.headers.get('content-type','').split(';')[0].lower(),
    }


def probe_post_access(cookie_path: str | None, post_url: str):
    """Compare minimal versus upstream HTML Accept request on an existing job URL.

    Does not follow redirects or expose Facebook page text, response headers,
    cookie values, tokens, query parameters, or raw redirect destinations.
    Each probe uses a fresh session to avoid cross-request cookie mutations.
    """
    if not cookie_path:
        return {'status':'cookies_not_configured'}
    try:
        with open(cookie_path,encoding='utf-8') as stream:
            cookies = json.load(stream)
        if not isinstance(cookies,list):
            return {'status':'cookies_format_invalid'}
    except (OSError, ValueError, TypeError):
        return {'status':'cookies_format_invalid'}
    results = {}
    variants = {
        'minimal': None,
        'html_accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
    }
    for name, accept in variants.items():
        try:
            with requests.Session() as session:
                configure_facebook_session(session)
                apply_facebook_cookies(session,cookies)
                headers = {'Accept':accept} if accept else None
                response = session.get(post_url,timeout=(5,15),allow_redirects=False,headers=headers)
                results[name] = _post_response_report(response)
        except requests.RequestException as error:
            results[name] = {'classification':'connection_error','exception_type':type(error).__name__}
    return {'status':'diagnostic_complete', 'variants':results,
            'note':'HTTP 200 or a CSRF token does not prove access to the requested post. No secrets or page bodies are returned.'}


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
            apply_facebook_cookies(session,raw)
            result,_=inspect_session(lambda url:session.get(url,timeout=(4,12),allow_redirects=True))
            result['cookie_count']=cookie_count
            if cookie_count<=2 and not result['token_available']:
                result['hint']='Export the complete Facebook cookie JSON from your authenticated browser; c_user and xs alone may not be enough.'
            return result
    except (ValueError,TypeError,OSError):
        return {'status':'cookies_format_invalid','token_available':False}