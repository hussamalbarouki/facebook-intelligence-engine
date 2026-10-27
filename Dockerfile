FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 DATA_DIR=/data
WORKDIR /service
RUN groupadd --system engine && useradd --system --gid engine --home-dir /service engine && mkdir -p /data && chown engine:engine /data
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Build must fail if the scraper cannot import (unit tests use a fake scraper).
RUN python -m pip check && python -c "from facebook_scraper import get_posts; from requests_html import HTMLSession; print('facebook-scraper import smoke test OK')"
COPY app ./app
USER engine
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/healthz",timeout=3)' || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]