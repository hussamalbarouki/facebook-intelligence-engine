"""Real Chromium acceptance test: comments beyond first 20 and safe reactors.

All data are synthetic local HTML, with no Facebook network connection.
"""
from playwright.sync_api import sync_playwright
from app.read_only_v2 import READ_COMMENTS_JS
from app.interaction_pagination import (
    _explicit_more,scroll_comment_panel,click_more_comments,
    click_reaction_list,extract_reaction_dialog,scroll_reaction_panel)

HTML=r"""<!doctype html><html lang="en"><body>
<button id="like" onclick="this.dataset.clicked='true'">Like</button>
<button id="reaction-count" onclick="document.getElementById('reactions').hidden=false">See who reacted</button>
<div role="dialog" aria-label="Comments" style="width:400px;height:270px">
  <div id="comments" style="height:180px;overflow-y:auto">
    <div id="rows"></div>
  </div>
  <button id="more" onclick="window.appendComments(20);this.hidden=true">View more comments</button>
</div>
<div id="reactions" role="dialog" aria-label="People who reacted" hidden
     style="width:300px;height:130px;overflow-y:auto">
 <h2>People who reacted</h2>
 <a href="https://www.facebook.com/profile.php?id=123456789">Reacting User</a>
 <div style="height:600px"></div>
</div>
<script>
 window.count=0;
 window.appendComments=n=>{
  const root=document.getElementById('rows');
  for(let i=0;i<n;i++){
   const id=1000000000+(++window.count);
   const e=document.createElement('div');
   e.setAttribute('role','article');
   e.innerHTML='<a href="https://www.facebook.com/profile.php?id='+id+'">Writer '+i+'</a>'+
       '<div dir="auto">A unique comment '+id+'</div>'+
       '<a href="https://www.facebook.com/reel/1418347453748116/?comment_id='+id+'">Time</a>';
   root.append(e);
  }
 };
 window.appendComments(20);
 const comments=document.getElementById('comments');
 let loaded=false;
 comments.addEventListener('scroll',()=>{
  if(loaded)return;
  if(comments.scrollTop+comments.clientHeight>=comments.scrollHeight-2){
   loaded=true;
   window.appendComments(20);
  }
 });
</script>
</body></html>"""

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--disable-dev-shm-usage'])
    try:
        page=browser.new_page(viewport={'width':1000,'height':720})
        page.set_content(HTML,wait_until='domcontentloaded')
        collected={}
        initial=page.evaluate(READ_COMMENTS_JS)
        assert len(initial)==20,len(initial)
        for item in initial:collected[item['id']]=item
        for _ in range(8):
            scroll_comment_panel(page)
            page.wait_for_timeout(130)
            for item in page.evaluate(READ_COMMENTS_JS):
                collected[item['id']]=item
            if len(collected)>=40:break
        assert len(collected)>=40, len(collected)
        assert click_more_comments(page)
        page.wait_for_timeout(70)
        for item in page.evaluate(READ_COMMENTS_JS):
            collected[item['id']]=item
        assert len(collected)>=60,len(collected)
        assert page.locator('#like').get_attribute('data-clicked') is None
        assert _explicit_more('View more comments')
        assert not _explicit_more('Send comment')
        assert click_reaction_list(page)
        assert page.locator('#reactions').is_visible()
        found={}
        evidence=extract_reaction_dialog(page,found,10)
        assert evidence['recognized_dialogs']==1,evidence
        assert len(found)==1 and list(found.values())[0]['name']=='Reacting User',found
        scroll_reaction_panel(page)
        assert page.locator('#like').get_attribute('data-clicked') is None
        print('Real Chromium pagination >20, verified reaction dialog, Like safety smoke OK')
    finally:
        browser.close()
