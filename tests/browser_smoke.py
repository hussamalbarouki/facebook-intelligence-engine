"""Browser DOM integration smoke — executed inside built Docker with Chromium.

Uses synthetic data: it verifies actual JS locators and comment permalink
extraction in the real installed browser, without any Facebook credentials.
"""
from playwright.sync_api import sync_playwright
from app.read_only_v2 import READ_COMMENTS_JS,UI_SIGNALS_JS,_read_only_open,_assess_login
from app.browser_engine import (_DOM_COMMENT_JS, _safe_page_signals,
                                _visible_comment_entry_buttons, _scroll_visible_dialog,
                                _browser_page_classification)

HTML="""<!doctype html><html lang="en-US"><head><title>Test comments</title></head><body>
<div role="article">
 <a href="https://www.facebook.com/real-profile">Example Commenter</a>
 <div dir="auto">Comment visible in the DOM.</div>
 <a href="https://www.facebook.com/example/posts/1234567890?comment_id=9876543210">Yesterday</a>
</div>
<button type="button" aria-label="View more comments">View more comments</button>
</body></html>"""

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--disable-dev-shm-usage','--no-first-run'])
    try:
        page=browser.new_page()
        page.set_content(HTML,wait_until='domcontentloaded')
        data=page.evaluate(_DOM_COMMENT_JS)
        assert len(data)==1, data
        assert data[0]['id']=='9876543210', data
        assert data[0]['name']=='Example Commenter', data
        assert data[0]['text']=='Comment visible in the DOM.',data
        report=_safe_page_signals(page)
        assert report['comment_permalink_links']==1, report
        assert report['comment_articles']==1, report
        assert report['lang']=='en-US',report
        assert report['comment_entry_candidates']>=1,report
        # Mimics Facebook's custom role=button comments entry. The
        # original scraper did not open this UI and consequently observed
        # GraphQL counts with no comment nodes.
        page.set_content("""<html><body>
          <div role="button" tabindex="0" onclick="document.getElementById('comments').style.display='block'">
            View all 12 comments
          </div>
          <div id="comments" style="display:none">
            <div role="article">
              <a href="https://www.facebook.com/example-user">Test Writer</a>
              <div dir="auto">Visible only after opening the list.</div>
              <a href="https://www.facebook.com/example/posts/1234567890?comment_id=76543210">Now</a>
            </div>
          </div>
        </body></html>""",wait_until='domcontentloaded')
        assert _browser_page_classification(page)['comment_entry_candidates']>=1
        assert _visible_comment_entry_buttons(page), 'custom comments entry did not click'
        assert page.locator('#comments').is_visible()
        found=page.evaluate(_DOM_COMMENT_JS)
        assert len(found)==1 and found[0]['text']=='Visible only after opening the list.', found
        # The scroll target must be the dialog's scrollable pane, not
        # the page body or a child outside the dialog.
        page.set_content("""<div role="dialog">
            <div id="pane" style="height:100px; overflow-y:auto">
              <div style="height:1600px">Long comment list</div>
            </div>
          </div>""",wait_until='domcontentloaded')
        assert _scroll_visible_dialog(page)
        assert page.locator('#pane').evaluate('(el)=>el.scrollTop')>0
        # Replica of the VERIFIED French reel flow, not an invented
        # English group-post control. The Like button must not be touched.
        page.set_content("""<html lang="fr"><body>
          <button id="like" onclick="this.dataset.toggled='yes'">J'aime</button>
          <button id="comment" onclick="document.querySelector('#drawer').hidden=false">Commenter</button>
          <section id="drawer" hidden>
            <div role="article">
              <a href="https://www.facebook.com/profile.php?id=100023993619471">عبدالله صالح</a>
              <span dir="auto">اختبار تعليق वास्तविक اردو</span>
              <a href="https://www.facebook.com/reel/1418347453748116/?comment_id=2319889195441081">Mardi</a>
            </div>
          </section>
        </body></html>""",wait_until="domcontentloaded")
        selfcheck=page.locator('#like').get_attribute('data-toggled')
        assert _read_only_open(page,True)=='Commenter'
        assert page.locator('#drawer').is_visible()
        assert page.locator('#like').get_attribute('data-toggled')==selfcheck
        reel=page.evaluate(READ_COMMENTS_JS)
        assert len(reel)==1,reel
        assert reel[0]['name']=="عبدالله صالح",reel
        assert reel[0]['id']=="2319889195441081",reel
        assert reel[0]['text']=="اختبار تعليق वास्तविक اردو",reel
        sig=page.evaluate(UI_SIGNALS_JS)
        assert sig['visible_comment_links']==1,sig
        # A public Reel may show a visible login form while the URL stays
        # /reel/: this MUST NOT be confused with a /login redirect.
        page.set_content("""<html><body>
          <form><input name="email"><input name="pass" type="password"></form>
          <button id="comments" onclick="this.dataset.opened='yes'">Commenter</button>
          <button id="like" onclick="this.dataset.liked='yes'">J'aime</button>
        </body></html>""",wait_until='domcontentloaded')
        auth_signals=page.evaluate(UI_SIGNALS_JS)
        assert auth_signals['login_fields'], auth_signals
        assert _assess_login('/reel/1418347453748116',auth_signals,{
            'c_user_for_target':True,'xs_for_target':True
        })=='visible_login_overlay_on_content'
        assert _read_only_open(page,True)=='Commenter'
        assert page.locator('#comments').get_attribute('data-opened')=='yes'
        assert page.locator('#like').get_attribute('data-liked') is None
        page.locator('form').evaluate('(f)=>f.style.display="none"')
        assert not page.evaluate(UI_SIGNALS_JS)['login_fields']
        print('V2 login-overlay classification and read-only control smoke OK')
        print('V2 French Reel comments, Unicode extraction and Like safety smoke OK')
        print('Real Chromium DOM comment extraction, controls and scroll smoke OK')
    finally:
        browser.close()
