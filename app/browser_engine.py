"""Extract verifiable Facebook comments/reactions from browser-rendered data.

This adapter does not synthesize GraphQL document IDs. It observes only the
responses the user's own browser session receives while viewing the requested
post and reads visible comment permalink elements as a fallback.

It never logs, caches or returns raw browser HTML, credentials, GraphQL payloads
or screenshots. Private/login-walled material is not bypassed.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from urllib.parse import urlsplit

logger=logging.getLogger('fb-engine.browser')
_BROWSER_LOCK=threading.Lock()
MAX_RESPONSE_BYTES=2_000_000
MAX_GRAPHQL_RESPONSES=45
MAX_JSON_NODES=8000
MAX_BROWSER_LIMIT=100

def _safe_text(value,limit=25000):
    if isinstance(value,dict):
        value=value.get('text')
    return value[:limit] if isinstance(value,str) else None

def _valid_profile_url(url, comment_permalink=False):
    if not isinstance(url,str) or len(url)>1024:
        return None
    from urllib.parse import parse_qs, urlencode, urlunsplit
    parsed=urlsplit(url)
    host=(parsed.hostname or '').lower()
    if not (parsed.scheme=='https' and (host=='facebook.com' or host.endswith('.facebook.com'))
            and not parsed.username and not parsed.password and parsed.port in (None,443)):
        return None
    query=parse_qs(parsed.query)
    if comment_permalink:
        # Preserve the comment identifier but drop tracking query parameters.
        allowed={k:v[0] for k,v in query.items()
                 if k in ('comment_id','reply_comment_id') and v and re.fullmatch(r'\d{5,30}',v[0])}
    elif parsed.path.rstrip('/').lower()=='/profile.php':
        allowed={'id':query['id'][0]} if query.get('id') and re.fullmatch(r'\d{5,30}',query['id'][0]) else {}
    else:
        allowed={}
    return urlunsplit(('https',host,parsed.path,urlencode(allowed),''))

def _parse_json_fragments(raw):
    if not isinstance(raw,str) or len(raw)>MAX_RESPONSE_BYTES:
        return []
    raw=raw.strip()
    if raw.startswith('for (;;);'):
        raw=raw[9:].lstrip()
    fragments=[]
    try:
        fragments.append(json.loads(raw))
    except (ValueError,TypeError):
        for line in raw.splitlines()[:30]:
            line=line.strip()
            if not line or len(line)>MAX_RESPONSE_BYTES:
                continue
            try:
                fragments.append(json.loads(line))
            except (ValueError,TypeError):
                continue
    return fragments

def _is_comment(node, parent):
    if not isinstance(node,dict):
        return False
    kind=str(node.get('__typename') or node.get('type') or '')
    if kind in ('Comment','FeedbackComment','UFIComment','TopLevelComment'):
        return True
    return 'comment' in parent.lower() and (
        isinstance(node.get('body'),dict) and isinstance(node.get('author'),dict)
        and ('id' in node or 'comment_id' in node))

def _extract_comment(node):
    owner=node.get('author') or node.get('commenter') or node.get('actor')
    if not isinstance(owner,dict):
        return None
    name=_safe_text(owner.get('name') or owner.get('short_name'),160)
    text=_safe_text(node.get('body') or node.get('message') or node.get('text'))
    identifier=node.get('id') or node.get('comment_id')
    if not (name and text and isinstance(identifier,(str,int))):
        return None
    cid=str(identifier)
    if len(cid)>200:
        return None
    profile=_valid_profile_url(owner.get('url') or owner.get('uri') or owner.get('profile_url'))
    link=node.get('url') or node.get('permalink')
    return {'id':cid,'name':name,'profile_url':profile,'text':text,
            'time':node.get('created_time') or node.get('timestamp'),'url':_valid_profile_url(link,comment_permalink=True),
            'replies':[],'reply_count':node.get('reply_count') if isinstance(node.get('reply_count'),int) else 0}

def _extract_reactor(node, parent):
    if 'reactor' not in parent.lower() and 'reaction_profile' not in parent.lower():
        return None
    if not isinstance(node,dict):
        return None
    actor=node.get('profile') or node.get('actor') or node.get('node') or node
    if not isinstance(actor,dict):
        return None
    name=_safe_text(actor.get('name'),160)
    profile=_valid_profile_url(actor.get('url') or actor.get('uri') or actor.get('profile_url'))
    if not (name and profile):
        return None
    typ=node.get('reaction_type') or node.get('reaction_type_id') or node.get('reaction')
    if isinstance(typ,dict):
        typ=typ.get('name') or typ.get('id')
    return {'name':name,'profile_url':profile,'type':str(typ).lower()[:50] if typ else 'unknown'}

def parse_graphql_interactions(raw, comment_limit, reactor_limit):
    """Bounded, shape-tolerant walker. Only emit entries with identifiable evidence."""
    comments={}
    reactors={}
    nodes=0
    stack=[(obj,'') for obj in _parse_json_fragments(raw)]
    while stack and nodes<MAX_JSON_NODES:
        node, parent=stack.pop()
        nodes+=1
        if isinstance(node,dict):
            if len(comments)<comment_limit and _is_comment(node,parent):
                found=_extract_comment(node)
                if found:
                    comments.setdefault(found['id'],found)
            if len(reactors)<reactor_limit:
                found=_extract_reactor(node,parent)
                if found:
                    reactors.setdefault(found['profile_url'],found)
            for key,val in node.items():
                if isinstance(val,(dict,list)):
                    # Keep the immediate context of the nearest named container
                    next_parent=key if any(k in key.lower() for k in ('comment','reactor','reaction')) else parent
                    stack.append((val,next_parent))
        elif isinstance(node,list):
            stack.extend((item,parent) for item in node[:150] if isinstance(item,(dict,list)))
    return list(comments.values())[:comment_limit],list(reactors.values())[:reactor_limit]

def _browser_cookie_entries(cookie_file):
    with open(cookie_file,encoding='utf-8') as f:
        raw=json.load(f)
    clean=[]
    for c in raw:
        if not isinstance(c,dict):
            continue
        name=c.get('name')
        value=c.get('value')
        domain=c.get('domain','.facebook.com')
        path=c.get('path','/')
        if not all(isinstance(v,str) for v in (name,value,domain,path)):
            continue
        host=domain.lstrip('.').lower()
        if not (host=='facebook.com' or host.endswith('.facebook.com')) or not path.startswith('/'):
            continue
        clean.append({'name':name,'value':value,'domain':domain,
                      'path':path,'secure':bool(c.get('secure',True)),
                      'httpOnly':bool(c.get('httpOnly',False))})
    return clean

# This code only reads publicly rendered comment links within the requested
# Facebook page. It does not click Like, Reply, Follow or any write action.
_DOM_COMMENT_JS = r"""() => {
  const results = [];
  const links = [...document.querySelectorAll('a[href*="comment_id="]')].slice(0,300);
  const seen = new Set();
  for (const anchor of links) {
    let id = '';
    try { id = new URL(anchor.href, location.href).searchParams.get('comment_id') || ''; }
    catch (_) { continue; }
    if (!id || !/^\d{5,30}$/.test(id) || seen.has(id)) continue;
    const parent = anchor.closest('[role="article"]') || anchor.parentElement?.parentElement?.parentElement;
    if (!parent) continue;
    const names = [...parent.querySelectorAll('a[href]')].filter(e => {
      try { return new URL(e.href,location.href).hostname.endsWith('facebook.com') &&
         !e.href.includes('comment_id=') && e.innerText?.trim().length > 1; }
      catch (_) { return false; }
    });
    const author = names[0];
    const texts = [...parent.querySelectorAll('[dir="auto"]')]
      .map(e => e.innerText?.trim()).filter(Boolean);
    const text = texts.find(t => t !== author?.innerText?.trim() && t.length >= 2);
    if (!author || !text) continue;
    seen.add(id);
    results.push({ id, name:author.innerText.trim().slice(0,160), text:text.slice(0,25000),
       profile_url:author.href, url:anchor.href, time:null, replies:[] });
  }
  return results;
}"""

_EXPAND_LABELS=re.compile(
    r'(?:view|see|load|show|more)\s+(?:all\s+)?(?:\d+\s+)?(?:more\s+)?(?:comments|replies)'
    r'|(?:عرض|مشاهدة|إظهار|المزيد|تحميل)\s+(?:كل\s+)?(?:التعليقات|الردود|المزيد)'
    r'|(?:voir|afficher)\s+(?:plus|les|tous)\s*(?:de\s+)?(?:commentaires|réponses)'
    r'|(?:mostra|visualizza|altri)\s+(?:commenti|risposte)'
    r'|(?:daha\s+fazla|yorumları\s+gör)',re.I)

def scrape_with_browser(url, comment_limit, reactor_limit, cookies_file):
    if os.getenv('FB_BROWSER_ENABLED','1').strip().lower() in ('0','false','no'):
        raise RuntimeError('BROWSER_DISABLED')
    if not cookies_file:
        raise RuntimeError('BROWSER_COOKIES_REQUIRED')
    if not _BROWSER_LOCK.acquire(blocking=False):
        raise RuntimeError('BROWSER_RESOURCE_BUSY')
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
        from .engine import validate_facebook_url
        validate_facebook_url(url)
        comment_limit=min(max(int(comment_limit),0),MAX_BROWSER_LIMIT)
        reactor_limit=min(max(int(reactor_limit),0),MAX_BROWSER_LIMIT)
        if not (comment_limit or reactor_limit):
            raise RuntimeError('BROWSER_NO_ITEMS_REQUESTED')
        comments={}
        reactors={}
        parsed_responses=0
        start=time.monotonic()
        max_duration=55
        def collect_response(response):
            nonlocal parsed_responses
            if parsed_responses>=MAX_GRAPHQL_RESPONSES or time.monotonic()-start>max_duration:
                return
            try:
                urlparts=urlsplit(response.url)
                if not ((urlparts.hostname or '').lower().endswith('.facebook.com')
                        and '/api/graphql' in urlparts.path):
                    return
                if response.status!=200:
                    return
                headers=response.headers
                if int(headers.get('content-length','0') or '0')>MAX_RESPONSE_BYTES:
                    return
                content=response.text()
                if len(content)>MAX_RESPONSE_BYTES:
                    return
                parsed_responses+=1
                found_comments,found_reactors=parse_graphql_interactions(
                    content,comment_limit,reactor_limit)
                for item in found_comments:
                    comments.setdefault(item['id'],item)
                for item in found_reactors:
                    reactors.setdefault(item['profile_url'],item)
            except Exception:
                return

        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=False,args=[
                '--disable-dev-shm-usage','--disable-background-networking',
                '--disable-extensions','--no-first-run','--disable-gpu'])
            try:
                context=browser.new_context(locale='en-US',viewport={'width':1280,'height':850},
                                            service_workers='block')
                context.set_default_timeout(2500)
                context.add_cookies(_browser_cookie_entries(cookies_file))
                page=context.new_page()
                page.on('response',collect_response)
                # Image/video/font blocking limits RAM and traffic on 4 GB VPS.
                page.route('**/*',lambda route: route.abort()
                           if route.request.resource_type in ('image','media','font')
                           else route.continue_())
                try:
                    page.goto(url,wait_until='domcontentloaded',timeout=22000)
                except PlaywrightTimeout:
                    logger.info('Facebook browser page navigation timed out; checking visible partial data')
                try:
                    validate_facebook_url(page.url)
                except ValueError:
                    raise RuntimeError('BROWSER_LEFT_FACEBOOK_DOMAIN') from None
                path=urlsplit(page.url).path.lower()
                if '/login' in path or '/checkpoint' in path:
                    raise RuntimeError('BROWSER_LOGIN_OR_CHECKPOINT_REQUIRED')
                for round_no in range(5):
                    if time.monotonic()-start>max_duration:
                        break
                    try:
                        visible=page.evaluate(_DOM_COMMENT_JS)
                        if isinstance(visible,list):
                            for item in visible:
                                if not isinstance(item,dict) or not item.get('id') or not item.get('name') or not item.get('text'):
                                    continue
                                key=str(item['id'])
                                comments.setdefault(key,{**item,'profile_url':_valid_profile_url(item.get('profile_url')),
                                                         'url':_valid_profile_url(item.get('url'),comment_permalink=True)})
                    except Exception:
                        pass
                    if (len(comments)>=comment_limit and len(reactors)>=reactor_limit):
                        break
                    # Click only load-more/expand-comment buttons, never any
                    # interaction that could write to or react to Facebook.
                    try:
                        buttons=page.get_by_role('button',name=_EXPAND_LABELS)
                        if buttons.count():
                            buttons.first.click(timeout=1800)
                        else:
                            page.mouse.wheel(0,650)
                    except Exception:
                        try: page.mouse.wheel(0,650)
                        except Exception: pass
                    page.wait_for_timeout(900)
                # Reaction names are loaded by Facebook only after opening its
                # read-only people-who-reacted dialog. Never click a Like or
                # other state-changing action.
                if reactor_limit and len(reactors)<reactor_limit and time.monotonic()-start<max_duration:
                    try:
                        trigger=page.get_by_role('button',name=re.compile(
                            r'see who reacted|people who reacted|view reactions'
                            r'|عرض المتفاعلين|من تفاعل|الأشخاص الذين تفاعلوا'
                            r'|voir les réactions|chi ha reagito|kimler tepki verdi',re.I))
                        if trigger.count():
                            trigger.first.click(timeout=1700)
                            page.wait_for_timeout(1000)
                            dialog=page.locator('[role="dialog"]')
                            if dialog.count():
                                labels=dialog.first.get_attribute('aria-label') or ''
                                heading=dialog.first.locator('[role="heading"]').first
                                if heading.count():
                                    labels+=' '+heading.inner_text(timeout=800)
                                if re.search(r'react|تفاعل|réaction|reazioni|tepki',labels,re.I):
                                    visible=dialog.first.locator('a[href]').evaluate_all(
                                        """items => items.slice(0,250).map(a => ({
                                          name:(a.innerText||'').trim().slice(0,160),
                                          profile_url:a.href
                                        })).filter(x=>x.name.length>1)""")
                                    for item in visible:
                                        profile=_valid_profile_url(item.get('profile_url'))
                                        if profile and item.get('name'):
                                            reactors.setdefault(profile,{'name':item['name'],
                                                                      'profile_url':profile,
                                                                      'type':'unknown'})
                    except Exception as exc:
                        logger.info('Reaction dialog read unavailable: %s',type(exc).__name__)
                context.close()
            finally:
                browser.close()
        logger.info('Facebook browser read-only capture: comments=%d reactors=%d gql_responses=%d',
                    len(comments),len(reactors),parsed_responses)
        if (not comments and not reactors):
            raise RuntimeError('BROWSER_NO_VERIFIABLE_INTERACTIONS')
        return {
            'post':{'id':None,'url':url,'author':None,'text':None,'time':None,
                    'counts':{'comments':None,'likes':None,'shares':None,'reactions_by_type':{}}},
            'comments':list(comments.values())[:comment_limit],
            'reactors':list(reactors.values())[:reactor_limit],
            'coverage':{'comments_returned':min(len(comments),comment_limit),
                        'reactors_returned':min(len(reactors),reactor_limit),
                        'comments_requested':comment_limit,'reactors_requested':reactor_limit,
                        'complete':False,'adapter':'browser',
                        'note':'Only visible or browser-received items were captured. Counts and coverage are not guaranteed.'}}
    finally:
        _BROWSER_LOCK.release()
