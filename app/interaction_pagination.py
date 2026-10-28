"""Bounded, read-only pagination of visible Facebook comment/reaction panels.

Clicks are restricted to explicit comment-page expansion, never Like, Share,
Reply, Follow or Send. Uses structural DOM scrolling first; React virtualized
lists are collected incrementally across scroll passes.
"""
from __future__ import annotations
import re
import time
from .read_only_v2 import MORE_TERMS, ACTION_DENY

MAX_SCROLL_PASSES=80
MAX_STALLED_PASSES=5
MORE_COUNT=re.compile(
    r'(?:view|see|show|load)\s+(?:(?:all|the|more|another)\s+)?(?:\d+\s+)?'
    r'(?:more\s+)?(?:comments|replies)'
    r'|(?:عرض|إظهار|تحميل|مشاهدة)\s+(?:المزيد من\s+|كل\s+)?(?:التعليقات|الردود)'
    r'|(?:voir|afficher)\s+(?:plus de\s+|tous les\s+)?(?:commentaires|réponses)',
    re.I)
REACTION_LIST_LABEL=re.compile(
    r'(?:see who reacted|people who reacted|view (?:all )?reactions|'
    r'view (?:all )?likes|(?:\d[\d,\s.KMB]*)\s+(?:reactions|likes)|'
    r'voir (?:les )?réactions|personnes? (?:qui ont )?réagi|'
    r'عرض (?:كل )?المتفاعلين|الأشخاص الذين تفاعلوا|'
    r'(?:\d[\d,\s.]*)\s+(?:تفاعل|تفاعلات|réactions|reaksi|reacciones))',re.I)
BAD_ACTION=re.compile(
    r'(?:^|\s)(?:like|liked|j.aime|me gusta|send|share|follow|'
    r'react|reaction button|reply|commenter|comment|submit|'
    r'أعجبني|إعجاب|إرسال|متابعة|مشاركة|رد|تعليق|लाइक|पसंद|'
    r'شیئر|بھیجیں|تبصرہ)(?:\s|$)',re.I)
REACTION_DIALOG=re.compile(
    r'(?:reactions?|reacted|likes|people who|réactions|personnes? '
    r'|المتفاعلين|التفاعلات|تفاعل|reaksi|reacciones|gefällt)',re.I)

SCROLL_JS=r"""() => {
  const visible = x => {let r=x.getBoundingClientRect();return r.width>3&&r.height>3
    &&r.bottom>0&&r.top<innerHeight};
  const scrollable=x => {const st=getComputedStyle(x),r=x.getBoundingClientRect();return
    x.scrollHeight-x.clientHeight>65 && visible(x) && r.width>80 && r.height>60 &&
    /(auto|scroll|overlay)/.test(st.overflowY)};
  const anchors=[...document.querySelectorAll('a[href*="comment_id="]')].filter(visible);
  const roots=[...document.querySelectorAll('[role="dialog"],[role="complementary"]')].filter(visible);
  const candidates=[];
  for(const a of anchors.slice(0,30)){
    let e=a;for(let i=0;e&&i<12;i++,e=e.parentElement){
      if(scrollable(e))candidates.push(e);
    }
  }
  for(const root of roots.slice(0,6)){
    for(const e of [root,...root.querySelectorAll('div')].slice(0,280)){
      if(scrollable(e))candidates.push(e);
    }
  }
  const unique=[...new Set(candidates)];
  // Prefer the closest scrollable ancestor of a visible comment. This avoids
  // scrolling the feed/reel carousel instead of the comments drawer.
  const target=unique[0]||null;
  if(!target)return {scrolled:false,reason:'no_scrollable_comment_panel',
    visible_comments:anchors.length,scrollable_panels:0};
  const before=target.scrollTop,limit=target.scrollHeight-target.clientHeight;
  target.scrollBy({top:Math.min(1100,Math.max(600,target.clientHeight*.85)),behavior:'instant'});
  const after=target.scrollTop;
  const rect=target.getBoundingClientRect();
  return {scrolled:after>before+2,before:Math.round(before),
    after:Math.round(after),at_end:after>=limit-8,
    visible_comments:anchors.length,scrollable_panels:unique.length,
    center_x:Math.round(Math.max(2,Math.min(innerWidth-2,rect.left+rect.width/2))),
    center_y:Math.round(Math.max(2,Math.min(innerHeight-2,rect.top+rect.height/2)))};
}"""

PANEL_SIGNATURE_JS=r"""() => {
  const vis=e=>{let r=e.getBoundingClientRect();return r.width>40&&r.height>10};
  const links=[...document.querySelectorAll('a[href*="comment_id="]')].filter(vis);
  const ids=new Set();
  for(const a of links){
    try{const u=new URL(a.href,location.href);
      const id=u.searchParams.get('comment_id')||u.searchParams.get('reply_comment_id');
      if(id)ids.add(id);
    }catch(_){}
  }
  return {visible_comment_links:links.length,unique_visible_ids:ids.size,
    dialog_count:[...document.querySelectorAll('[role="dialog"]')].filter(vis).length};
}"""

REACTION_DOM_JS=r"""() => {
  // A reaction-list overlay must identify itself as such, otherwise
  // Facebook's normal comment authors must never be confused with reactors.
  const tag=/reactions?|reacted|likes|réactions|تفاعل|المتفاعلين|reaksi|reacciones|gefällt/i;
  const panels=[...document.querySelectorAll('[role="dialog"]')].filter(d=>{
    const h=d.querySelector('[role="heading"],h1,h2,h3');
    const title=(d.getAttribute('aria-label')||'')+' '+(h?.textContent||'');
    return tag.test(title);
  });
  const out=[];
  for(const panel of panels.slice(0,3)){
    for(const a of [...panel.querySelectorAll('a[href]')].slice(0,200)){
      const name=(a.innerText||'').trim();
      let u;try{u=new URL(a.href,location.href)}catch(_){continue}
      if(!name||name.length>160||!(u.hostname==='facebook.com'||u.hostname.endsWith('.facebook.com')))continue;
      if(u.searchParams.has('comment_id') || /\/(?:reel|videos|watch|posts)\//.test(u.pathname))continue;
      // Prefer actual profile links; exclude tabs / reaction names.
      if(/^(?:all|like|love|haha|wow|care|sad|angry|tout|j'aime|الكل|أعجبني)$/i.test(name))continue;
      if(!u.pathname.includes('profile.php') && !/^\/(?:people|user)\//.test(u.pathname) &&
         !/^\/[A-Za-z0-9._%-]{2,100}\/?$/.test(u.pathname))continue;
      out.push({name:name.slice(0,160),profile_url:a.href});
    }
  }
  return {recognized_dialogs:panels.length,profiles:out};
}"""

def _candidate_label(el):
    try:
        label=(el.get_attribute('aria-label',timeout=250) or el.inner_text(timeout=300) or '')
        return ' '.join(label.split())[:140]
    except Exception:
        return ''

def _explicit_more(label):
    if not label or len(label)>110 or ACTION_DENY.search(label):
        return False
    case=label.casefold()
    return MORE_COUNT.search(label) is not None or any(t in case for t in MORE_TERMS)

def click_more_comments(page):
    """Only inspect inside the comments drawer, never composer buttons."""
    scope=page.locator('[role="dialog"],[role="complementary"]')
    try:
        for root_index in range(min(scope.count(),5)):
            root=scope.nth(root_index)
            if not root.is_visible():continue
            candidates=root.locator('button,a,[role="button"]')
            for i in range(min(candidates.count(),140)):
                el=candidates.nth(i)
                if not el.is_visible():continue
                label=_candidate_label(el)
                if not _explicit_more(label):continue
                if (el.get_attribute('type') or '').lower()=='submit':continue
                if el.locator('input,textarea,[contenteditable]').count():continue
                el.click(timeout=1400)
                return True
    except Exception:
        pass
    return False

def scroll_comment_panel(page):
    """Returns motion details; falls back to wheel inside the panel."""
    result=page.evaluate(SCROLL_JS)
    if result.get('scrolled'):return result
    if 'center_x' in result and 'center_y' in result:
        page.mouse.move(result['center_x'],result['center_y'])
        page.mouse.wheel(0,880)
        result['wheel_requested']=True
    return result

REACTION_SCROLL_JS=r"""() => {
  const tag=/reactions?|reacted|likes|réactions|تفاعل|المتفاعلين|reaksi|reacciones|gefällt/i;
  for(const modal of document.querySelectorAll('[role="dialog"]')){
    const heading=modal.querySelector('[role="heading"],h1,h2,h3');
    if(!tag.test((modal.getAttribute('aria-label')||'')+' '+(heading?.textContent||'')))continue;
    const all=[modal,...modal.querySelectorAll('div')];
    for(const element of all.slice(0,300)){
      const r=element.getBoundingClientRect(), css=getComputedStyle(element);
      if(r.height<40||r.width<100)continue;
      if(element.scrollHeight-element.clientHeight>70 &&
         /(scroll|auto|overlay)/.test(css.overflowY)){
        const before=element.scrollTop;
        element.scrollBy(0,900);
        return {scrolled:element.scrollTop>before+2,
                center_x:Math.round(r.left+r.width/2),
                center_y:Math.round(r.top+r.height/2)};
      }
    }
  }
  return {scrolled:false};
}"""

def scroll_reaction_panel(page):
    result=page.evaluate(REACTION_SCROLL_JS)
    if not result.get('scrolled') and 'center_x' in result:
        page.mouse.move(result['center_x'],result['center_y'])
        page.mouse.wheel(0,760)
        result['wheel_requested']=True
    return result


def click_reaction_list(page):
    """Only explicit 'view reaction people' or numeric reaction count controls."""
    # Not the reel's generic Like/Reaction toggle (previously caused a write).
    for selector in ('a[href*="/ufi/reaction/profile/browser"]',
                     'a[href*="/reaction/profile/browser"]',
                     '[role="button"]','button','a[href]'):
        try:
            loc=page.locator(selector)
            for i in range(min(loc.count(),140)):
                el=loc.nth(i)
                if not el.is_visible():continue
                label=_candidate_label(el)
                if selector.startswith('a[href*='):
                    # Browser routing URL explicitly identifies the
                    # Facebook people-who-reacted list.
                    pass
                elif not REACTION_LIST_LABEL.search(label):
                    continue
                if BAD_ACTION.fullmatch(label):
                    continue
                # aria-pressed is characteristic of toggle controls such as
                # Like/Unlike; we must never change a user's Facebook state.
                if el.get_attribute('aria-pressed') is not None:
                    continue
                if el.locator('textarea,[contenteditable],input').count():
                    continue
                if (el.get_attribute('type') or '').lower()=='submit':
                    continue
                el.click(timeout=1400)
                return True
        except Exception:
            continue
    return False

def extract_reaction_dialog(page,reactors,limit):
    data=page.evaluate(REACTION_DOM_JS)
    for profile in data.get('profiles',[]):
        if len(reactors)>=limit:break
        from .read_only_v2 import _clean_url
        uri=_clean_url(profile.get('profile_url'))
        name=profile.get('name')
        if uri and name:
            reactors.setdefault(uri,{'name':name,'profile_url':uri,'type':'unknown'})
    return {'recognized_dialogs':data.get('recognized_dialogs',0),
            'names_added':len(reactors)}
