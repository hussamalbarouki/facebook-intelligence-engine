"""Browser DOM integration smoke — executed inside built Docker with Chromium.

Uses synthetic data: it verifies actual JS locators and comment permalink
extraction in the real installed browser, without any Facebook credentials.
"""
from playwright.sync_api import sync_playwright
from app.browser_engine import _DOM_COMMENT_JS, _safe_page_signals

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
        print('Real Chromium DOM comment extraction and visibility smoke OK')
    finally:
        browser.close()
