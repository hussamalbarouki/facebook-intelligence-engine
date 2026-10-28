"""Browser DOM integration smoke — executed inside built Docker with Chromium.

Uses synthetic data: it verifies actual JS locators and comment permalink
extraction in the real installed browser, without any Facebook credentials.
"""
from playwright.sync_api import sync_playwright
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
        print('Real Chromium DOM comment extraction, controls and scroll smoke OK')
    finally:
        browser.close()
