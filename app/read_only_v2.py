"""Facebook read-only V2 engine.

Full self-contained Playwright scraper, replacing the doc_id-dependent engines
for production jobs. Inspired by the separation of browser/navigation/parsing
in the MIT-licensed fbcommentviewrt project, but purpose-built for public
Reels, videos and posts. No posting or reaction actions are present.

Only returns comments that have a verifiable comment permalink or a verified
comment id+author+body in Facebook's own GraphQL responses.
"""
from __future__ import annotations
import json
import logging
import os
import re
import threading
import time
from html import unescape
from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit
from typing import Any

log=logging.getLogger('fb-engine.v2')
LOCK=threading.Lock()
# Hard resource limits are explicit and independently reported in coverage.
COMMENT_CAP=500
REACTOR_CAP=300
RESPONSE_CAP=160
BODY_CAP=1_500_000
TIME_CAP=150

# Structural identifiers are locale-independent. Text labels below are only
# for opening visible comment panels / loading more, never for extracting data.
# Native-speaker spellings are kept alongside unambiguous original UI labels.
OPEN_REEL={
 'en':('Comment','Comments'),
 'fr':('Commenter','Commentaires'),
 'ar':('تعليق','التعليقات','علّق','التعليق'),
 'hi':('टिप्पणी करें','टिप्पणी','कमेंट करें','कमेंट','टिप्पणियाँ'),
 'ur':('تبصرہ کریں','تبصرہ','تبصرے','کمنٹ کریں'),
 'bn':('মন্তব্য করুন','মন্তব্য','কমেন্ট করুন'),
 'ps':('تبصره وکړئ','تبصرې'),
 'sd':('تبصرو ڪريو','تبصرا'),
 'pa-Arab':('تبصرہ کرو','تبصرے'),
 'ne':('टिप्पणी गर्नुहोस्','टिप्पणीहरू'),
 'or':('ମନ୍ତବ୍ୟ କରନ୍ତୁ','ମନ୍ତବ୍ୟ'),
 'si':('අදහස් දක්වන්න','අදහස්'),
 'my':('မှတ်ချက်ပေး','မှတ်ချက်'),

 'pa':('ਟਿੱਪਣੀ ਕਰੋ','ਟਿੱਪਣੀਆਂ','ਕਮੈਂਟ ਕਰੋ'),
 'ta':('கருத்து தெரிவி','கருத்துகள்','கருத்து'),
 'te':('వ్యాఖ్యానించండి','వ్యాఖ్యలు'),
 'mr':('टिप्पणी करा','टिप्पण्या','कमेंट करा'),
 'gu':('ટિપ્પણી કરો','ટિપ્પણીઓ'),
 'ml':('അഭിപ്രായം രേഖപ്പെടുത്തുക','അഭിപ്രായങ്ങൾ'),
 'kn':('ಕಾಮೆಂಟ್ ಮಾಡಿ','ಕಾಮೆಂಟ್‌ಗಳು'),
 'es':('Comentar','Comentarios'),
 'pt':('Comentar','Comentários'),
 'it':('Commenta','Commenti'),
 'de':('Kommentieren','Kommentare'),
 'tr':('Yorum yap','Yorumlar'),
 'id':('Komentar','Beri komentar'),
 'ru':('Комментировать','Комментарии'),
 'uk':('Коментувати','Коментарі'),
 'ja':('コメントする','コメント'),
 'ko':('댓글 달기','댓글'),
 'zh':('评论','留言'),
 'th':('แสดงความคิดเห็น','ความคิดเห็น'),
 'vi':('Bình luận','Nhận xét'),
 'fa':('نظر دادن','نظرات'),
 'he':('תגובה','תגובות'),
 'sw':('Maoni',),
 'nl':('Reageren','Reacties'),
 'pl':('Komentarz','Komentarze'),
 'sv':('Kommentera','Kommentarer'),
}
MORE={
 'en':('more comments','view comments','see comments','more replies','view replies'),
 'fr':('plus de commentaires','voir les commentaires','réponses','commentaires masqués'),
 'ar':('مزيد من التعليقات','عرض التعليقات','عرض الردود','المزيد من الردود'),
 'hi':('और टिप्पणियाँ','सभी टिप्पणियाँ','टिप्पणियां देखें','और जवाब'),
 'ur':('مزید تبصرے','تمام تبصرے','تبصرے دیکھیں','مزید جوابات'),
 'bn':('আরও মন্তব্য','সব মন্তব্য'),
 'ps':('نورې تبصرې','ټولې تبصرې'),
 'sd':('وڌيڪ تبصرا',),
 'pa-Arab':('ہور تبصرے',),
 'ne':('थप टिप्पणीहरू',),
 'or':('ଅଧିକ ମନ୍ତବ୍ୟ',),
 'si':('තවත් අදහස්',),
 'my':('မှတ်ချက်များ ထပ်ကြည့်ရန်',),

 'pa':('ਹੋਰ ਟਿੱਪਣੀਆਂ','ਸਾਰੀਆਂ ਟਿੱਪਣੀਆਂ'),
 'ta':('மேலும் கருத்துகள்','அனைத்து கருத்துகளும்'),
 'te':('మరిన్ని వ్యాఖ్యలు','అన్ని వ్యాఖ్యలు'),
 'mr':('आणखी टिप्पण्या','सर्व टिप्पण्या'),
 'gu':('વધુ ટિપ્પણીઓ','બધી ટિપ્પણીઓ'),
 'ml':('കൂടുതൽ അഭിപ്രായങ്ങൾ',),
 'kn':('ಇನ್ನಷ್ಟು ಕಾಮೆಂಟ್‌ಗಳು',),
 'es':('más comentarios','ver comentarios','respuestas'),
 'pt':('mais comentários','ver comentários','respostas'),
 'it':('altri commenti','mostra commenti','risposte'),
 'de':('weitere kommentare','kommentare anzeigen','antworten'),
 'tr':('daha fazla yorum','yorumları gör'),
 'id':('lihat komentar','komentar lainnya'),
 'ru':('другие комментарии','показать комментарии','ответы'),
 'uk':('більше коментарів','показати коментарі'),
 'ja':('他のコメント','コメントを表示'),
 'ko':('댓글 더 보기','댓글 보기'),
 'zh':('查看更多评论','更多评论'),
 'th':('ดูความคิดเห็นเพิ่มเติม','ความคิดเห็นทั้งหมด'),
 'vi':('xem thêm bình luận','xem bình luận'),
 'fa':('نمایش نظرات بیشتر',),
 'he':('תגובות נוספות','תגובות הצג'),
 'nl':('meer opmerkingen','reacties bekijken'),
 'pl':('więcej komentarzy','zobacz komentarze'),
}
COMMENT_TOTAL=re.compile(r'^\s*(?:[\d\u0660-\u0669\u06F0-\u06F9,.\s]+)\s*(?:comments?|commentaires|comentarios|comentários|commenti|kommentare|komentar|комментариев|تعليقات|تعليق|टिप्पणि(?:याँ|यां|यों)|कमेंट|تبصرے|تبصرہ|মন্তব্য|评论|댓글|ความคิดเห็น)\s*$',re.I)
ACTION_DENY=re.compile(r'^(like|j.aime|react|follow|share|send|reply|submit|me gusta|curtir|gosto|gefällt mir|أعجبني|إعجاب|مشاركة|إرسال|رد|متابعة|पसंद|लाइक|शेयर|भेजें|لائک|پسند|شیئر|بھیجیں|رد|いいね|좋아요|点赞)\b',re.I)
MORE_TERMS=tuple(t.casefold() for values in MORE.values() for t in values)
REEL_OPEN_TERMS=tuple(t.casefold() for values in OPEN_REEL.values() for t in values)

def _clean_url(raw:str|None, permalink:bool=False)->str|None:
    if not raw or not isinstance(raw,str) or len(raw)>2100:
        return None
    try:p=urlsplit(unescape(raw))
    except Exception:return None
    host=(p.hostname or '').lower()
    if p.scheme!='https' or not (host=='facebook.com' or host.endswith('.facebook.com')) or p.username or p.password:
        return None
    q=parse_qs(p.query)
    allowed={}
    if permalink:
        for key in ('comment_id','reply_comment_id'):
            if q.get(key) and re.fullmatch(r'\d{5,30}',q[key][0]):
                allowed[key]=q[key][0]
    elif p.path.rstrip('/')=='/profile.php':
        if q.get('id') and re.fullmatch(r'\d{5,30}',q['id'][0]):
            allowed['id']=q['id'][0]
    return urlunsplit(('https',host,p.path,urlencode(allowed),''))

def _is_safe_open_label(label:str,*,video:bool)->bool:
    if not isinstance(label,str):
        return False
    label=' '.join(label.split()).strip()
    if not label or len(label)>100 or ACTION_DENY.search(label):
        return False
    folded=label.casefold()
    if COMMENT_TOTAL.fullmatch(label):
        return True
    if any(term in folded for term in MORE_TERMS):
        return True
    # Single word "Comment" is only used as a read-only comments drawer
    # opener on some reels. No text-entry controls are eligible.
    if video and any(folded==term for term in REEL_OPEN_TERMS):
        return True
    return False

def _cookie_entries(file_path):
    with open(file_path,encoding='utf-8') as f: data=json.load(f)
    if not isinstance(data,list): return []
    out=[]
    for row in data:
        if not isinstance(row,dict):continue
        d=row.get('domain','.facebook.com')
        if not isinstance(d,str) or not (d.lstrip('.').lower()=='facebook.com' or d.lower().endswith('.facebook.com')):
            continue
        name,value=row.get('name'),row.get('value')
        if not (isinstance(name,str) and isinstance(value,str) and name):
            continue
        path=row.get('path','/')
        if not isinstance(path,str) or not path.startswith('/'):continue
        cookie={'name':name,'value':value,'domain':d,'path':path,
                'secure':bool(row.get('secure',True)),'httpOnly':bool(row.get('httpOnly',False))}
        if isinstance(row.get('expires'),(int,float)) and row['expires']>0:
            cookie['expires']=row['expires']
        out.append(cookie)
    return out

def _json_docs(raw):
    if not isinstance(raw,str) or len(raw)>BODY_CAP: return []
    raw=raw.strip()
    if raw.startswith('for (;;);'):raw=raw[len('for (;;);'):].strip()
    try:return [json.loads(raw)]
    except (ValueError,TypeError):
        result=[]
        for line in raw.splitlines()[:35]:
            try:result.append(json.loads(line))
            except (ValueError,TypeError):pass
        return result

def _text(raw):
    for _ in range(4):
        if not isinstance(raw,dict):break
        raw=raw.get('text') or raw.get('message') or raw.get('content')
    return raw[:25000].strip() if isinstance(raw,str) and raw.strip() else None

def _capture_graphql(raw, comments:dict,reactors:dict,limits):
    counts={'documents':0,'comment_shapes':0,'reaction_shapes':0,
            'graphql_errors':0,'page_cursors':0,'has_next_page':0}
    stack=_json_docs(raw);counts['documents']=len(stack);limit=0
    while stack and limit<10000:
        item,parent=stack.pop() if isinstance(stack[-1],tuple) else (stack.pop(),'')
        limit+=1
        if isinstance(item,list):
            stack.extend((x,parent) for x in item[:300] if isinstance(x,(list,dict)))
        elif isinstance(item,dict):
            if item.get('errors'):counts['graphql_errors']+=1
            info=item.get('page_info') or item.get('pageInfo')
            if isinstance(info,dict) and 'comment' in parent.lower():
                if isinstance(info.get('end_cursor') or info.get('endCursor'),str):
                    counts['page_cursors']+=1
                if info.get('has_next_page') is True or info.get('hasNextPage') is True:
                    counts['has_next_page']+=1
            typ=str(item.get('__typename') or '')
            author=item.get('author') or item.get('commenter')
            body=_text(item.get('body') or item.get('message') or item.get('text'))
            cid=item.get('id') or item.get('comment_id')
            if ('comment' in typ.lower() or 'comment' in parent.lower()) and isinstance(author,dict) and body and isinstance(cid,(str,int)):
                name=_text(author.get('name') or author.get('short_name'))
                if name and len(comments)<limits[0]:
                    key=str(cid)
                    comments.setdefault(key,{'id':key,'name':name[:160],'text':body,
                        'profile_url':_clean_url(author.get('url') or author.get('uri')),
                        'url':_clean_url(item.get('url') or item.get('permalink'),True),
                        'time':item.get('created_time') or item.get('timestamp'),'replies':[]})
                    counts['comment_shapes']+=1
            if 'reactor' in parent.lower() or 'reaction_profile' in parent.lower():
                actor=item.get('actor') or item.get('profile') or item.get('node') or item
                if isinstance(actor,dict):
                    name=_text(actor.get('name'))
                    uri=_clean_url(actor.get('url') or actor.get('uri'))
                    aid=actor.get('id')
                    key=uri or (str(aid) if isinstance(aid,(str,int)) else None)
                    if name and key and len(reactors)<limits[1]:
                        reactors.setdefault(key,{'id':str(aid) if aid else None,
                          'name':name[:160],'profile_url':uri,'type':'unknown'})
                        counts['reaction_shapes']+=1
            for key,value in item.items():
                if isinstance(value,(dict,list)):
                    next_path=key if ('comment' in key.lower() or 'react' in key.lower()) else parent
                    stack.append((value,next_path))
    return counts

# Comment timestamp permalink is the identity source. HTML text is used
# for locale-independent extraction; the original Unicode is preserved.
READ_COMMENTS_JS=r"""() => {
 const result=[], seen=new Set();
 for (const a of [...document.querySelectorAll('a[href*="comment_id="]')].slice(0,700)) {
  let id;try{id=new URL(a.href,location.href).searchParams.get('reply_comment_id') ||
     new URL(a.href,location.href).searchParams.get('comment_id');}catch(_){continue;}
  if(!id || !/^\d{5,30}$/.test(id) || seen.has(id))continue;
  // Never associate a comment with another comment's author: choose
  // the closest container containing exactly ONE comment permalink.
  let parent=null;
  let cur=a.parentElement;
  for(let n=0;cur&&n<10;n++,cur=cur.parentElement){
    const links=cur.querySelectorAll('a[href*="comment_id="]');
    if(links.length>1)break;
    if(links.length===1 && cur.querySelectorAll('a[href]').length>=2 &&
       cur.querySelector('[dir="auto"]')){
      parent=cur;break;
    }
  }
  if(!parent)continue;
  const anchors=[...parent.querySelectorAll('a[href]')].filter(x=>{
    let u;try{u=new URL(x.href,location.href);}catch(_){return false;}
    return (u.hostname==='facebook.com'||u.hostname.endsWith('.facebook.com')) &&
      !u.searchParams.has('comment_id') && !u.pathname.includes('/reel/') &&
      !u.pathname.includes('/videos/') && (x.innerText||'').trim().length>1;
  });
  const author=anchors[0];if(!author)continue;
  const name=(author.innerText||'').trim();
  const blocks=[...parent.querySelectorAll('[dir="auto"]')]
     .filter(x=>!x.querySelector('[dir="auto"]'))
     .map(x=>(x.innerText||'').trim())
     .filter(x=>x.length>0 && x!==name && x.length<25000);
  const body=blocks.find(x=>x.length>1);if(!body)continue;
  seen.add(id);
  result.push({id,name:name.slice(0,160),text:body.slice(0,25000),
   url:a.href,profile_url:author.href,time:null,replies:[]});
 }
 return result;
}"""

UI_SIGNALS_JS=r"""() => {
 const visible = el => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
 const email = document.querySelector('input[name="email"]');
 const pass = document.querySelector('input[name="pass"]');
 const anchors=document.querySelectorAll('a[href*="comment_id="]').length;
 const dialogs=document.querySelectorAll('[role="dialog"]').length;
 const articles=document.querySelectorAll('[role="article"]').length;
 return {visible_comment_links:anchors,dialogs,articles,
   login_fields:visible(email)&&visible(pass),
   login_fields_present:!!(email&&pass),
   comment_widgets:document.querySelectorAll('[role="button"],button').length,
   page_language:(document.documentElement.lang||'').slice(0,16)};
}"""

def _candidate_text(element):
    try:
        aria=element.get_attribute('aria-label',timeout=500)
        return (aria or element.inner_text(timeout=500) or '').strip()
    except Exception:return ''

def _read_only_open(page,video:bool):
    # Strictly button/link/role=button. Not a contenteditable field,
    # form submit, Like, Follow, Share or Reply.
    for selector in ('button','a[role="button"]','[role="button"]','a[href]'):
        try:
            items=page.locator(selector)
            for i in range(min(items.count(),130)):
                el=items.nth(i)
                if not el.is_visible():continue
                label=_candidate_text(el)
                if not _is_safe_open_label(label,video=video):continue
                if (el.get_attribute('type') or '').lower()=='submit':continue
                if el.locator('input,textarea,[contenteditable="true"]').count():continue
                el.click(timeout=1500)
                return label[:64]
        except Exception:
            continue
    return None

def _scroll_actual_panel(page):
    try:
        return page.evaluate(r"""() => {
          const dialogs=[...document.querySelectorAll('[role="dialog"]')];
          const panels=[...dialogs,...document.querySelectorAll('[role="complementary"]')];
          for(const panel of panels){
            for(const node of [panel,...panel.querySelectorAll('div')].slice(0,220)){
              const style=getComputedStyle(node);
              if(node.scrollHeight>node.clientHeight+100 && /(auto|scroll)/.test(style.overflowY)){
                node.scrollBy(0,700);return true;
              }
            }
          }
          return false;
        }""")
    except Exception:return False

def _assess_login(path,signals,scope):
    """Classify browser evidence without guessing that all forms mean logout."""
    path=(path or '').lower()
    if '/checkpoint' in path or '/two_step_verification' in path:
        return 'checkpoint_redirect'
    if '/login' in path:
        return 'login_redirect'
    if not (scope.get('c_user_for_target') and scope.get('xs_for_target')):
        return 'cookie_domain_path_mismatch'
    if signals.get('login_fields'):
        return 'visible_login_overlay_on_content'
    return 'no_visible_login_overlay'


def run(url,comment_limit,reactor_limit,cookies_file,diagnostic_only=False):
    """Complete browser session, page navigation, collection, pagination and parsing."""
    if os.getenv('FB_BROWSER_ENABLED','1').lower() in ('0','false','no'):
        raise RuntimeError('BROWSER_DISABLED')
    from .browser_login import profile_ready
    use_saved_profile=profile_ready()
    if not cookies_file and not use_saved_profile:
        raise RuntimeError('FACEBOOK_COOKIES_REQUIRED')
    if not LOCK.acquire(blocking=False):raise RuntimeError('BROWSER_RESOURCE_BUSY')
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        parsed=urlsplit(url)
        if not _clean_url(url) or parsed.scheme!='https':
            raise RuntimeError('FACEBOOK_URL_INVALID')
        maxc=min(max(0,int(comment_limit)),COMMENT_CAP)
        maxr=min(max(0,int(reactor_limit)),REACTOR_CAP)
        comments,reactors={},{}
        stats={'adapter':'read_only_v2','observed_graphql':0,'parsed_documents':0,
               'comment_shapes':0,'reaction_shapes':0,'graphql_errors':0,
               'page_cursors':0,'has_next_page':0,
               'comment_opened':False,'comment_entry_label_language_independent':True,
               'ui_before':{},'ui_after':{},'ui_final':{},
               'comments_extracted':0,'reactors_extracted':0,'status':'running',
               'cookie_scope':{'c_user_for_target':False,'xs_for_target':False},
               'navigation':'not_started','login_classification':'not_checked',
               'comment_pagination':{'attempted':0,'successful_expansion_clicks':0,
                   'scroll_moves':0,'stalled_passes':0,'last_visible_ids':0,
                   'stop_reason':'not_started'},
               'reactor_pagination':{'attempted':False,'dialog_opened':False,
                   'verified_names':0,'stop_reason':'not_started'}}
        begin=time.monotonic()
        def on_response(response):
            if time.monotonic()-begin>TIME_CAP or stats['observed_graphql']>=RESPONSE_CAP:return
            try:
                p=urlsplit(response.url)
                if response.status!=200 or not (p.hostname or '').endswith('.facebook.com') or '/api/graphql' not in p.path:return
                stats['observed_graphql']+=1
                if int(response.headers.get('content-length','0') or '0')>BODY_CAP:return
                raw=response.text()
                for name,count in _capture_graphql(raw,comments,reactors,(maxc,maxr)).items():
                    if name=='documents':stats['parsed_documents']+=count
                    else:stats[name]+=count
            except Exception:return
        with sync_playwright() as pw:
            browser=None
            context=None
            try:
                if use_saved_profile:
                    # Actual Chrome user profile from the interactive VPS
                    # browser login. Same DISPLAY, same data dir, same Chrome
                    # revision; no cookie export/import or separate session.
                    profile=os.path.join(os.getenv('DATA_DIR','/data'),'facebook-profile')
                    context=pw.chromium.launch_persistent_context(
                        profile,headless=False,viewport={'width':1365,'height':910},
                        service_workers='block',
                        args=['--disable-dev-shm-usage','--no-first-run','--disable-gpu'])
                    from .profile_state import restore_state,save_state
                    restore_state(context,os.getenv('DATA_DIR','/data'))
                    entries=[]
                else:
                    # Legacy manual-cookie fallback, used until an interactive
                    # profile has been saved for the first time.
                    browser=pw.chromium.launch(headless=True,args=[
                        '--disable-dev-shm-usage','--disable-gpu','--no-first-run'])
                    context=browser.new_context(viewport={'width':1365,'height':910},
                                                service_workers='block')
                    entries=_cookie_entries(cookies_file)
                    context.add_cookies(entries)
                scoped={item.get('name') for item in context.cookies([url])}
                stats['session_source']='saved_browser_profile' if use_saved_profile else 'manual_cookies'
                stats['cookie_scope']={
                   'c_user_for_target':'c_user' in scoped,
                   'xs_for_target':'xs' in scoped,
                   'cookie_entries_accepted':len(entries),
                   'cookie_entries_for_target':len(scoped)}
                page=context.new_page()
                page.on('response',on_response)
                page.route('**/*',lambda route: route.abort() if route.request.resource_type in ('image','media','font') else route.continue_())
                try:page.goto(url,wait_until='domcontentloaded',timeout=18000)
                except PWTimeout:pass
                page.wait_for_timeout(1500)
                if not _clean_url(page.url):raise RuntimeError('FACEBOOK_LEFT_DOMAIN')
                path=urlsplit(page.url).path.lower()
                video=('/reel/' in path or '/videos/' in path or '/watch/' in path)
                stats['page_kind']='reel' if '/reel/' in path else 'video' if video else 'post'
                stats['ui_before']=page.evaluate(UI_SIGNALS_JS)
                stats['navigation']='facebook_page'
                stats['login_classification']=_assess_login(
                    path,stats['ui_before'],stats['cookie_scope'])
                log.info('V2 auth classification: state=%s c_user_at_target=%s xs_at_target=%s',
                         stats['login_classification'],
                         stats['cookie_scope']['c_user_for_target'],
                         stats['cookie_scope']['xs_for_target'])
                if stats['login_classification']=='checkpoint_redirect':
                    stats['navigation']='checkpoint'
                    stats['status']='facebook_checkpoint_required'
                    if diagnostic_only:return stats
                    raise RuntimeError('FACEBOOK_CHECKPOINT_REQUIRED')
                if stats['login_classification']=='login_redirect':
                    stats['navigation']='login'
                    stats['status']='facebook_login_required'
                    if diagnostic_only:return stats
                    raise RuntimeError('FACEBOOK_LOGIN_REQUIRED')
                if stats['login_classification']=='cookie_domain_path_mismatch':
                    stats['status']='cookie_scope_mismatch'
                    if diagnostic_only:return stats
                    raise RuntimeError('FACEBOOK_COOKIES_SCOPE_MISMATCH')
                # A visible login overlay on a non-login Reel URL is not in
                # itself proof of an expired session: inspect comment UI first.
                if maxc:
                    clicked=_read_only_open(page,video)
                    stats['comment_opened']=bool(clicked)
                    # Do not return UI text; may be user-generated.
                    page.wait_for_timeout(900)
                stats['ui_after']=page.evaluate(UI_SIGNALS_JS)
                from .interaction_pagination import (
                    MAX_SCROLL_PASSES, MAX_STALLED_PASSES, PANEL_SIGNATURE_JS,
                    click_more_comments, scroll_comment_panel, click_reaction_list,
                    extract_reaction_dialog, scroll_reaction_panel)
                pagination=stats['comment_pagination']
                if maxc:
                    pagination['stop_reason']='in_progress'
                    previous_count=-1
                    stalled=0
                    # Distinguish reading the initial Facebook batch from
                    # successfully fetching additional unique comments.
                    for attempt in range(MAX_SCROLL_PASSES):
                        if time.monotonic()-begin>TIME_CAP:
                            pagination['stop_reason']='time_budget_exhausted'
                            break
                        pagination['attempted']+=1
                        try:
                            for c in page.evaluate(READ_COMMENTS_JS) or []:
                                if not isinstance(c,dict):continue
                                ident=c.get('id')
                                if not (isinstance(ident,str) and re.fullmatch(r'\d{5,30}',ident)):continue
                                if not c.get('name') or not c.get('text'):continue
                                if len(comments)>=maxc:break
                                comments.setdefault(ident,{'id':ident,'name':c['name'],'text':c['text'],
                                    'profile_url':_clean_url(c.get('profile_url')),
                                    'url':_clean_url(c.get('url'),True),'time':None,'replies':[]})
                            visible=page.evaluate(PANEL_SIGNATURE_JS)
                            pagination['last_visible_ids']=visible.get('unique_visible_ids',0)
                        except Exception as exc:
                            log.info('Comment batch read unavailable: %s',type(exc).__name__)
                        if len(comments)>=maxc:
                            pagination['stop_reason']='requested_or_hard_limit_reached'
                            break
                        total=len(comments)
                        if total>previous_count:
                            stalled=0
                            previous_count=total
                        else:
                            stalled+=1
                        pagination['stalled_passes']=stalled
                        if stalled>=MAX_STALLED_PASSES:
                            pagination['stop_reason']='no_new_comments_after_retries'
                            break
                        expanded=click_more_comments(page)
                        if expanded:
                            pagination['successful_expansion_clicks']+=1
                        motion=scroll_comment_panel(page)
                        if motion.get('scrolled') or motion.get('wheel_requested'):
                            pagination['scroll_moves']+=1
                        page.wait_for_timeout(950 if expanded else 720)
                    else:
                        pagination['stop_reason']='scroll_pass_limit_reached'
                else:
                    pagination['stop_reason']='comments_not_requested'

                reactor_diag=stats['reactor_pagination']
                if maxr:
                    reactor_diag['attempted']=True
                    if len(reactors)>=maxr:
                        reactor_diag['stop_reason']='requested_or_hard_limit_reached'
                    elif time.monotonic()-begin>TIME_CAP:
                        reactor_diag['stop_reason']='time_budget_exhausted'
                    else:
                        # Read-only UI controls only; never click Like/React.
                        reactor_diag['dialog_opened']=click_reaction_list(page)
                        if reactor_diag['dialog_opened']:
                            page.wait_for_timeout(900)
                            reactor_last=-1
                            stalled=0
                            for _ in range(35):
                                if time.monotonic()-begin>TIME_CAP:break
                                info=extract_reaction_dialog(page,reactors,maxr)
                                reactor_diag['verified_names']=len(reactors)
                                reactor_diag['recognized_dialogs']=info.get('recognized_dialogs',0)
                                if len(reactors)>=maxr:
                                    reactor_diag['stop_reason']='requested_or_hard_limit_reached'
                                    break
                                if len(reactors)==reactor_last:
                                    stalled+=1
                                else:
                                    stalled=0
                                    reactor_last=len(reactors)
                                if stalled>=5:
                                    reactor_diag['stop_reason']='no_new_reactors_after_retries'
                                    break
                                scroll_reaction_panel(page)
                                page.wait_for_timeout(730)
                            if reactor_diag['stop_reason']=='not_started':
                                reactor_diag['stop_reason']='reaction_scroll_limit_reached'
                        else:
                            reactor_diag['stop_reason']='no_verified_reactor_list_control'
                else:
                    reactor_diag['stop_reason']='reactors_not_requested'
                stats['ui_final']=page.evaluate(UI_SIGNALS_JS)
                stats['comments_extracted']=len(comments)
                stats['reactors_extracted']=len(reactors)
                # A persistent visible login overlay is a *different* failure
                # from "no identifiable comments" or a /login redirect.
                stats['status']='data_found' if (comments or reactors) else (
                    'facebook_login_overlay_visible' if (
                        stats['ui_final']['login_fields'] or stats['ui_after']['login_fields'])
                    else 'comment_panel_not_opened' if maxc and not stats['comment_opened']
                    else 'no_verifiable_interactions')
            finally:
                if context is not None:
                    if use_saved_profile:
                        # Encrypt and persist refreshed session cookies after
                        # each scrape, before closing the SAME profile.
                        try:
                            from .profile_state import save_state
                            save_state(context,os.getenv('DATA_DIR','/data'))
                        except Exception as exc:
                            log.warning('Could not persist refreshed browser session: %s',
                                        type(exc).__name__)
                    try:context.close()
                    except Exception:pass
                if browser is not None:
                    try:browser.close()
                    except Exception:pass
        log.info('V2 result: kind=%s comments=%d/%d reactors=%d/%d gql=%d opened=%s pagination=%s reactions=%s status=%s',
                 stats.get('page_kind'),len(comments),maxc,len(reactors),maxr,stats['observed_graphql'],
                 stats['comment_opened'],stats['comment_pagination']['stop_reason'],
                 stats['reactor_pagination']['stop_reason'],stats['status'])
        if diagnostic_only:return stats
        if not comments and not reactors:
            if stats['status']=='facebook_login_overlay_visible':
                raise RuntimeError('FACEBOOK_LOGIN_WALL_VISIBLE')
            raise RuntimeError('BROWSER_NO_VERIFIABLE_INTERACTIONS')
        return {
            'post':{'id':None,'url':url,'author':None,'text':None,'time':None,
                    'counts':{'comments':None,'likes':None,'shares':None,'reactions_by_type':{}}},
            'comments':list(comments.values())[:maxc],
            'reactors':list(reactors.values())[:maxr],
            'coverage':{'comments_requested':int(comment_limit),
                        'reactors_requested':int(reactor_limit),
                        'comments_effective_limit':maxc,'reactors_effective_limit':maxr,
                        'comments_returned':min(len(comments),maxc),
                        'reactors_returned':min(len(reactors),maxr),
                        'comments_stop_reason':stats['comment_pagination']['stop_reason'],
                        'reactors_stop_reason':stats['reactor_pagination']['stop_reason'],
                        'comment_scroll_passes':stats['comment_pagination']['attempted'],
                        'comment_expansion_clicks':stats['comment_pagination']['successful_expansion_clicks'],
                        'reactions_list_opened':stats['reactor_pagination']['dialog_opened'],
                        'complete':False,'adapter':'read_only_v2',
                        'note':'Only verifiable visible or received records. Counts and names depend on Facebook availability.'}
        }
    finally:
        LOCK.release()
