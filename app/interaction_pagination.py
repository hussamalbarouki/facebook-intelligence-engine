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
MAX_STALLED_PASSES=10
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
  const scrollable=x => {const st=getComputedStyle(x),r=x.getBoundingClientRect();return x.scrollHeight-x.clientHeight>65 && visible(x) && r.width>80 && r.height>60 &&
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
  if(!unique.length)return {scrolled:false,reason:'no_scrollable_comment_panel',
    visible_comments:anchors.length,scrollable_panels:0};
  // React often nests scroll areas. Try candidates until one ACTUALLY MOVES.
  // Choosing unique[0] repeatedly can stall on a small, already-ended panel.
  let best=null;
  for (const target of unique.slice(0,24)) {
    const before=target.scrollTop,limit=target.scrollHeight-target.clientHeight;
    target.scrollBy({top:Math.min(1100,Math.max(600,target.clientHeight*.85)),behavior:'instant'});
    const after=target.scrollTop,rect=target.getBoundingClientRect();
    const out={scrolled:after>before+2,before:Math.round(before),
      after:Math.round(after),at_end:after>=limit-8,
      visible_comments:anchors.length,scrollable_panels:unique.length,
      center_x:Math.round(Math.max(2,Math.min(innerWidth-2,rect.left+rect.width/2))),
      center_y:Math.round(Math.max(2,Math.min(innerHeight-2,rect.top+rect.height/2)))};
    if(out.scrolled)return out;
    if(!best || (!out.at_end && best.at_end))best=out;
  }
  return best || {scrolled:false,reason:'no_panel_progress',visible_comments:anchors.length};
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
    const tabs=[...d.querySelectorAll('[role="tab"]')].map(t=>(t.getAttribute('aria-label')||t.textContent||'').trim().toLowerCase());
    const hasReactions=tabs.filter(t=>/^(like|love|haha|wow|care|sad|angry|j'aime|me gusta|أعجبني|أحببته|पसंद|لائک)$/.test(t)).length>0;
    return tag.test(title) || (tabs.length>=2 && hasReactions);
  });
  const out=[];
  for(const panel of panels.slice(0,3)){
    for(const a of [...panel.querySelectorAll('a[href]')].slice(0,200)){
      const name=(a.innerText||a.getAttribute('aria-label')||'').trim();
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
    const title=(modal.getAttribute('aria-label')||'')+' '+(heading?.textContent||'');
    const tabs=[...modal.querySelectorAll('[role="tab"]')].map(t=>(t.getAttribute('aria-label')||t.textContent||'').trim().toLowerCase());
    const reactionTab=tabs.length>=2 && tabs.some(t=>/^(like|love|haha|wow|care|sad|angry|j'aime|me gusta|أعجبني|पसंद|لائک)$/.test(t));
    if(!tag.test(title) && !reactionTab)continue;
    // Prefer scrollable ancestors of profile links. Header/tab panes may be
    // scrollable but do not load more people.
    const links=[...modal.querySelectorAll('a[href]')].slice(0,120);
    const candidates=[];
    for(const link of links){
      let node=link;
      for(let depth=0;node&&depth<9;depth++,node=node.parentElement){
        if(!modal.contains(node))break;
        candidates.push(node);
      }
    }
    candidates.push(modal,...[...modal.querySelectorAll('div')].slice(0,240));
    let fallback=null;
    for(const element of [...new Set(candidates)].slice(0,320)){
      const r=element.getBoundingClientRect(), css=getComputedStyle(element);
      if(r.height<40||r.width<100)continue;
      if(element.scrollHeight-element.clientHeight>70 &&
         /(scroll|auto|overlay)/.test(css.overflowY)){
        const before=element.scrollTop;
        element.scrollBy({top:900,behavior:'instant'});
        const out={scrolled:element.scrollTop>before+2,
                at_end:element.scrollTop>=element.scrollHeight-element.clientHeight-8,
                center_x:Math.round(r.left+r.width/2),
                center_y:Math.round(r.top+r.height/2)};
        if(out.scrolled)return out;
        if(!fallback || (!out.at_end && fallback.at_end))fallback=out;
      }
    }
    if(fallback)return fallback;
  }
  return {scrolled:false,reason:'no_moving_reaction_panel'};
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


ALL_COMMENT_LABELS=(
    'All comments','Tous les commentaires','جميع التعليقات','كل التعليقات',
    'सभी टिप्पणियाँ','تمام تبصرے','সব মন্তব্য','सभी कमेंट',
    'Todos los comentarios','Todos os comentários','Tutti i commenti',
    'Alle Kommentare','Tüm yorumlar','Все комментарии','所有评论',
    'すべてのコメント','모든 댓글','Semua komentar')
SORT_OPTION_LABELS=(
    'Most relevant','Relevant','Les plus pertinents','الأكثر صلة','الأكثر ملاءمة',
    'सबसे प्रासंगिक','سب سے متعلقہ','Más relevantes','Mais relevantes',
    'Più pertinenti','Relevanteste','En alakalı','Самые актуальные')

def select_all_comments(page):
    """Optional read-only Facebook sorting, without clicking post actions.

    Only open an explicit relevance filter; only select an explicit All
    Comments menu item. Never treats the comment composer as a filter.
    """
    import re
    def exact_label(text):
        return re.compile(r'^\s*'+re.escape(text)+r'\s*$',re.I)
    for label in SORT_OPTION_LABELS:
        for role in ('button','link'):
            try:
                target=page.get_by_role(role,name=exact_label(label))
                if not target.count() or not target.first.is_visible():continue
                if target.first.get_attribute('aria-pressed') is not None:continue
                target.first.click(timeout=1200)
                page.wait_for_timeout(250)
                for choice in ALL_COMMENT_LABELS:
                    for choice_role in ('menuitem','option','button','link'):
                        item=page.get_by_role(choice_role,name=exact_label(choice))
                        if not item.count() or not item.first.is_visible():continue
                        if item.first.get_attribute('type')=='submit':continue
                        item.first.click(timeout=1300)
                        return True
                # Do not click random items when sorting option is absent.
                return False
            except Exception:
                continue
    return False


def select_all_reactions(page):
    """Select the 'All' tab ONLY inside an identified reactions dialog."""
    all_names=('All','Tout','Tous','الكل','सभी','سب','سبھی','Todos',
               'Todas','Tutti','Alle','Все','全部','すべて','모두','Semua')
    dialog=page.locator('[role="dialog"]')
    for n in range(min(dialog.count(),4)):
        try:
            root=dialog.nth(n)
            if not root.is_visible():continue
            title=(root.get_attribute('aria-label') or '')
            heading=root.locator('[role="heading"],h1,h2,h3')
            if heading.count():
                title+=' '+(heading.first.inner_text(timeout=500) or '')
            tabs=root.locator('[role="tab"]')
            labels=[(_candidate_label(tabs.nth(k)) or '').casefold()
                    for k in range(min(tabs.count(),15))]
            known_reactions={'like','love','haha','wow','care','sad','angry',
                             "j'aime",'me gusta','أعجبني','पसंद','لائک'}
            recognized=(bool(REACTION_DIALOG.search(title))
                        or (len(labels)>=2 and any(t in known_reactions for t in labels)))
            if not recognized:continue
            for k in range(min(tabs.count(),15)):
                button=tabs.nth(k)
                if not button.is_visible():continue
                if _candidate_label(button).casefold() not in {t.casefold() for t in all_names}:continue
                if button.get_attribute('aria-selected')=='true':
                    return True
                button.click(timeout=1400)
                return True
        except Exception:
            continue
    return False
