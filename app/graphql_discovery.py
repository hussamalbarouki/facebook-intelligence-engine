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
MAX_SCRIPTS=96
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
    # rsrc.php is a shared Facebook asset path: it serves CSS as well as JS.
    # Accepting the path alone allowed .css bodies into the JS VM and caused
    # enormous SyntaxError tracebacks. Only JavaScript assets are eligible.
    if (not path.endswith(('.js','.mjs')) or
            any(path.endswith(ext) for ext in ('.css','.map','.png','.jpg','.jpeg','.webp','.svg','.json'))):
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


class RedactUpstreamEvaluationError(logging.Filter):
    """Prevent V8 from printing full downloaded asset bodies in tracebacks."""
    def filter(self, record):
        if (record.name == 'facebook_gql_scraper.facebookOperationDiscovery'
                and isinstance(record.msg,str)
                and record.msg.startswith('Could not evaluate Facebook script')):
            reason=(record.exc_info[0].__name__ if record.exc_info else 'UnknownError')
            record.msg='Facebook JS asset evaluation failed: %s'
            record.args=(reason,)
            record.exc_info=None
            record.exc_text=None
        return True


def extend_discovery(context, page_url):
    """Patch only this context's discovery instance, retaining upstream V8 logic."""
    discovery=getattr(context,'operation_discovery',None)
    if discovery is None or not hasattr(discovery,'_get_javascript_links'):
        return
    # The upstream logger uses exc_info=True; a syntax error embeds the entire
    # response (hundreds of KB of JS/CSS) in log output. Apply once per process.
    upstream_logger=logging.getLogger('facebook_gql_scraper.facebookOperationDiscovery')
    if not any(isinstance(f,RedactUpstreamEvaluationError) for f in upstream_logger.filters):
        upstream_logger.addFilter(RedactUpstreamEvaluationError())
    original=discovery._get_javascript_links
    def upgraded(text):
        upstream=original(text)
        sources=find_javascript_sources(text,page_url,upstream)
        discovery.last_candidate_count=len(sources)
        discovery.last_css_excluded=sum(
            1 for src in upstream
            if isinstance(src,str) and (urlsplit(src).path or '').lower().endswith('.css'))
        discovery.last_reached_limit=len(sources)>=MAX_SCRIPTS
        logger.info('Facebook GraphQL JS discovery: candidate_scripts=%d css_excluded=%d capped=%s',
                    len(sources),discovery.last_css_excluded,discovery.last_reached_limit)
        return sources
    discovery._get_javascript_links=upgraded
    discovery.last_candidate_count=0
    discovery.last_css_excluded=0
    discovery.last_reached_limit=False
