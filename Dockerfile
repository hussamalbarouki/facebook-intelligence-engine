FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 DATA_DIR=/data \
    FB_BROWSER_ENABLED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    HOME=/home/engine XDG_CONFIG_HOME=/home/engine/.config \
    XDG_CACHE_HOME=/home/engine/.cache
WORKDIR /service
# Chromium's crashpad and profile startup require user-owned writable HOME/XDG paths.
RUN groupadd --system engine && useradd --system --gid engine --create-home --home-dir /home/engine engine \
    && mkdir -p /data /home/engine/.config /home/engine/.cache \
    && chown -R engine:engine /data /home/engine \
    && chmod 700 /home/engine/.config /home/engine/.cache
RUN apt-get update && apt-get install -y --no-install-recommends git xvfb xauth && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Build must fail if the scraper cannot import (unit tests use a fake scraper).
RUN python -m pip check && python -c "from facebook_scraper import get_posts; from facebook_gql_scraper import FacebookContext,Post; print('Both scraper adapters import successfully')"
# This installs the browser together with OS libraries; no browser is downloaded
# on Coolify startup, and the runtime user never executes a browser installer.
RUN python -m playwright install --with-deps chromium && chmod -R a+rX /opt/pw-browsers

COPY app ./app
USER engine
# Smoke test the *runtime* browser during image build, as the unprivileged
# engine user. A published image is not released if Chrome cannot launch.
RUN python -c 'import os; assert all(os.access(p,os.W_OK) for p in (os.environ["HOME"],os.environ["XDG_CONFIG_HOME"],os.environ["XDG_CACHE_HOME"])); print("Chromium writable user paths OK")' \
    && xvfb-run -a -s "-screen 0 1280x900x24" python -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=False,args=["--disable-dev-shm-usage"]); page=b.new_page(); page.goto("data:text/html,<h1>browser-ready</h1>"); assert page.locator("h1").inner_text()=="browser-ready"; b.close(); p.stop(); print("headed Chromium smoke test OK")'
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/healthz",timeout=3)' || exit 1
# A virtual display lets Chromium run in normal headed mode even on a VPS.
# No web UI is publicly exposed. Python API remains single worker.
CMD ["xvfb-run", "-a", "-s", "-screen 0 1280x900x24", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]