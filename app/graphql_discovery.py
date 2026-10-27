"""Bounded GraphQL JS bundle discovery for currently visible Facebook pages.

The vendored upstream discovery sees JSON-root bootloader data or literal
<script src> elements; some Comet pages embed rsrcMap JSON inside HTML instead.
Only Facebook and Facebook CDN JavaScript may be downloaded, and no doc IDs
are fabricated or persisted without exact operation-name matching.
"""
from __future__ import annotations

import html
import json
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

logger=logging.getLogger('fb-engine.discovery')
MAX_SCRIPTS=64
MAX_BODY_CHARS=2_000_000
_SRC_JSON=re.compile(r'"src"\s*:\s*"((?:\\.|[^"\\]){5,2048})"', re.I)

class ScriptReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag.lower()=='script' and attrs.get('src'):
            self.urls.append(attrs['src'])
        if tag.lower()=='link' and attrs.get('rel','').lower() in ('modulepreload','preload') and attrs.get('as','').lower()=='script' and attrs.get('href'):
            self.urls.append(attrs['href'])


def _decode_js_string(raw):
    if not isinstance(raw,str) or len(raw)>2048:
        return ''
    try:
        val=json.loads('"'+raw+'"')
    except (ValueError,TypeError):
        val=raw
    # Facebook may encode separators when embedding JSON in HTML scripts.
    return html.unescape(val).replace(r'\/','/').replace(r'\u002F','/').replace(r'\u002f','/').replace(r'\u003A',':')


def allowed_js_url(raw, base_url):
    if not isinstance(raw,str):
        return None
    url=urljoin(base_url,_decode_js_string(raw))
    parts=urlsplit(url)
    hostname=(parts.hostname or '').lower()
    valid_host=(hostname=='facebook.com' or hostname.endswith('.facebook.com') or
                hostname=='fbcdn.net' or hostname.endswith('.fbcdn.net'))
    if (parts.scheme!='https' or not valid_host or parts.username or parts.password
            or parts.port not in (None,443) or len(url)>2048):
        return None
    path=parts.path.lower()
    if not (path.endswith('.js') or '/rsrc.php/' in path):
        return None
    return url


def find_javascript_sources(source, base_url, upstream_urls=(), limit=MAX_SCRIPTS):
    """Read literal script tags and embedded (potentially escaped) rsrcMap.src."""
    content=source[:MAX_BODY_CHARS] if isinstance(source,str) else ''
    parser=ScriptReferences()
    parser.feed(content)
    normalized=(content.replace(r'\"','"').replace(r'\u0022','"')
                        .replace(r'\u002F','/').replace(r'\u002f','/'))
    candidates=list(upstream_urls or [])+parser.urls
    candidates.extend(_SRC_JSON.findall(normalized))
    seen=set()
    urls=[]
    for raw in candidates:
        url=allowed_js_url(raw,base_url)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
            if len(urls)>=limit:
                break
    return urls


def alias_operation_id(operations, operation_name):
    """Choose only an exact matching operation's published, numeric doc id."""
    if not isinstance(operations,dict) or not operation_name.endswith('_facebookRelayOperation'):
        return None
    basename=operation_name.removesuffix('_facebookRelayOperation')
    variants=(operation_name,basename+'.graphql',basename+'$Parameters')
    matches={v for key in variants if isinstance((v:=operations.get(key)),str) and re.fullmatch(r'\d{10,30}',v)}
    return next(iter(matches)) if len(matches)==1 else None


def extend_discovery(context, page_url):
    """Patch only this context's discovery instance, retaining upstream V8 logic."""
    discovery=getattr(context,'operation_discovery',None)
    if discovery is None or not hasattr(discovery,'_get_javascript_links'):
        return
    original=discovery._get_javascript_links
    def upgraded(text):
        upstream=original(text)
        sources=find_javascript_sources(text,page_url,upstream)
        discovery.last_candidate_count=len(sources)
        logger.info('Facebook GraphQL JS discovery: candidate_scripts=%d',len(sources))
        return sources
    discovery._get_javascript_links=upgraded
    discovery.last_candidate_count=0
