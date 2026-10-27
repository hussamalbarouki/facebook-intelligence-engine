"""Management-first REST service for a future PHP admin dashboard."""
from __future__ import annotations
import logging
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from .engine import scrape_post, validate_facebook_url
from .secrets import CookieVault
from .storage import JobStore

VERSION='1.0.1'
log=logging.getLogger('fb-engine')
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

class JobRequest(BaseModel):
    url: str = Field(min_length=15,max_length=2048)
    comments_limit: int | None = Field(default=None,ge=0,le=1000)
    reactors_limit: int | None = Field(default=None,ge=0,le=1000)
    client_job_id: str | None = Field(default=None,min_length=1,max_length=128,pattern=r'^[a-zA-Z0-9._:-]+$')

class CookieUpload(BaseModel):
    cookies: dict[str,str] | list[dict[str,Any]]

class SettingsPatch(BaseModel):
    default_comments_limit: int | None = Field(None,ge=0,le=1000)
    default_reactors_limit: int | None = Field(None,ge=0,le=1000)
    max_comments_limit: int | None = Field(None,ge=0,le=1000)
    max_reactors_limit: int | None = Field(None,ge=0,le=1000)
    retention_days: int | None = Field(None,ge=1,le=365)
    request_cooldown_seconds: int | None = Field(None,ge=0,le=3600)
    jobs_enabled: bool | None = None


def create_app(data_dir: str | None=None, api_key: str | None=None, scraper=None):
    key = api_key if api_key is not None else os.getenv('API_KEY','')
    if len(key)<32: raise RuntimeError('Set a random API_KEY with 32+ characters in Coolify')
    root=Path(data_dir or os.getenv('DATA_DIR','/data'))
    root.mkdir(parents=True,exist_ok=True)
    store=JobStore(str(root/'jobs.sqlite3'))
    vault=CookieVault(store,root)
    scraper=scraper or scrape_post
    stop=threading.Event()
    api_header=APIKeyHeader(name='X-API-Key',auto_error=False)

    def authorize(token: str | None=Depends(api_header)):
        if not token or not secrets.compare_digest(token,key):
            raise HTTPException(status_code=401,detail='Invalid API key')
        return True

    def worker():
        last_run=0.0
        last_cleanup=0.0
        while not stop.is_set():
            now=time.monotonic()
            if now-last_cleanup>3600:
                try:store.cleanup(store.settings()['retention_days'])
                except Exception:log.exception('Housekeeping failed')
                last_cleanup=now
            if not store.settings()['jobs_enabled']:
                stop.wait(1);continue
            row=store.claim()
            if not row:
                stop.wait(0.7);continue
            try:
                wait=max(0,store.settings()['request_cooldown_seconds']-(time.monotonic()-last_run))
                if wait:stop.wait(wait)
                if stop.is_set():break
                with vault.temporary_cookie_file() as cookie_path:
                    result=scraper(row['url'],row['comment_limit'],row['reactor_limit'],cookie_path)
                last_run=time.monotonic()
                store.finish(row['id'],result=result)
            except ImportError as exc:
                # A dependency failure is not a Facebook login failure. Log the traceback
                # on the server so the precise missing import can be diagnosed.
                log.exception('Scraper dependency import failed for job %s', row['id'])
                store.finish(row['id'], error='DEPENDENCY_IMPORT_ERROR')
            except Exception as exc:
                # Safe public error; secrets and third-party URLs never logged.
                log.warning('Scraper error for job %s: %s',row['id'],type(exc).__name__)
                code='COOKIE_STORAGE_ERROR' if str(exc)=='COOKIE_STORAGE_ERROR' else 'SCRAPE_FAILED'
                store.finish(row['id'],error=code)

    @asynccontextmanager
    async def lifespan(app:FastAPI):
        stop.clear()
        t=threading.Thread(target=worker,name='fb-engine-worker',daemon=True)
        t.start()
        yield
        stop.set()
        t.join(timeout=4)

    app=FastAPI(title='Facebook Intelligence Engine',version=VERSION,description='Self-hosted extraction API. Facebook scraping results can be incomplete.',lifespan=lifespan)
    app.state.store=store;app.state.vault=vault

    @app.get('/healthz',include_in_schema=False)
    def health():return {'ok':True,'service':'facebook-intelligence-engine','version':VERSION}

    @app.get('/v1/capabilities',dependencies=[Depends(authorize)])
    def capabilities():
        return {'version':VERSION,'adapter':'kevinzg/facebook-scraper','supports':['posts','comments','comment_replies','reactors','reaction_types','cookie_management','jobs','pagination'],
                'limits':{'comments':1000,'reactors':1000},'known_limitations':['Facebook may require cookies or block scraping','Reaction lists may be partial','No live Facebook test is performed in CI']}

    @app.get('/v1/status',dependencies=[Depends(authorize)])
    def status():
        return {'ok':True,'version':VERSION,'adapter':'kevinzg/facebook-scraper',
                'cookies':vault.status(),'settings':store.settings(),'queue':store.metrics()}

    @app.get('/v1/settings',dependencies=[Depends(authorize)])
    def get_settings():return store.settings()

    @app.patch('/v1/settings',dependencies=[Depends(authorize)])
    def patch_settings(patch:SettingsPatch):
        updates=patch.model_dump(exclude_none=True)
        merged={**store.settings(),**updates}
        if merged['default_comments_limit']>merged['max_comments_limit'] or merged['default_reactors_limit']>merged['max_reactors_limit']:
            raise HTTPException(status_code=422,detail='Default limits must not exceed maximum limits')
        return store.update_settings(updates)

    @app.get('/v1/facebook/cookies',dependencies=[Depends(authorize)])
    def cookies_status():return vault.status()

    @app.put('/v1/facebook/cookies',dependencies=[Depends(authorize)])
    def cookies_put(body:CookieUpload):
        try:return vault.save(body.cookies)
        except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from None

    @app.delete('/v1/facebook/cookies',dependencies=[Depends(authorize)])
    def cookies_delete():return vault.delete()

    @app.post('/v1/jobs',status_code=202,dependencies=[Depends(authorize)])
    def submit(body:JobRequest):
        settings=store.settings()
        if not settings['jobs_enabled']:raise HTTPException(status_code=503,detail='Engine job submission is disabled')
        try: url=validate_facebook_url(body.url)
        except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from None
        n_comments=body.comments_limit if body.comments_limit is not None else settings['default_comments_limit']
        n_reactors=body.reactors_limit if body.reactors_limit is not None else settings['default_reactors_limit']
        if n_comments>settings['max_comments_limit'] or n_reactors>settings['max_reactors_limit']:
            raise HTTPException(status_code=422,detail='Requested extraction exceeds configured maximum')
        try: jid,reused=store.create(url,n_comments,n_reactors,body.client_job_id)
        except OverflowError as exc:raise HTTPException(status_code=429,detail=str(exc)) from None
        except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from None
        return {'job_id':jid,'status':store.get(jid)['status'],'reused':reused}

    @app.get('/v1/jobs',dependencies=[Depends(authorize)])
    def list_jobs(status:Literal['queued','running','completed','failed','canceled']|None=None,limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0)):
        return store.list(status,limit,offset)

    @app.get('/v1/jobs/{job_id}',dependencies=[Depends(authorize)])
    def get_job(job_id:str):
        row=store.get(job_id)
        if not row:raise HTTPException(status_code=404,detail='Job not found')
        return row

    @app.post('/v1/jobs/{job_id}/retry',dependencies=[Depends(authorize)])
    def retry(job_id:str):
        row=store.get(job_id)
        if not row:raise HTTPException(status_code=404,detail='Job not found')
        if not store.retry(job_id):raise HTTPException(status_code=409,detail='Only failed jobs can be retried')
        return {'job_id':job_id,'status':'queued'}

    @app.post('/v1/jobs/{job_id}/cancel',dependencies=[Depends(authorize)])
    def cancel(job_id:str):
        row=store.get(job_id)
        if not row:raise HTTPException(status_code=404,detail='Job not found')
        if not store.cancel(job_id):raise HTTPException(status_code=409,detail='Job cannot be canceled in this state')
        return {'job_id':job_id,'status':'canceled','note':'A request already running against Facebook may finish before it stops.'}

    @app.get('/v1/jobs/{job_id}/result',dependencies=[Depends(authorize)])
    def results(job_id:str,comments_offset:int=Query(0,ge=0),reactors_offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500)):
        row=store.get(job_id,True)
        if not row:raise HTTPException(status_code=404,detail='Job not found')
        if row['status']!='completed':raise HTTPException(status_code=409,detail='Job not completed')
        r=row['result']; comments=r.get('comments',[]); reactors=r.get('reactors',[])
        return {'job_id':job_id,'post':r.get('post',{}),'coverage':r.get('coverage',{}),
                'comments':comments[comments_offset:comments_offset+limit],
                'reactors':reactors[reactors_offset:reactors_offset+limit],
                'pagination':{'comments_total_returned':len(comments),'reactors_total_returned':len(reactors),
                              'comments_next_offset':comments_offset+limit if comments_offset+limit<len(comments) else None,
                              'reactors_next_offset':reactors_offset+limit if reactors_offset+limit<len(reactors) else None}}

    @app.get('/v1/metrics',dependencies=[Depends(authorize)])
    def metrics():return store.metrics()

    @app.get('/v1/events',dependencies=[Depends(authorize)])
    def events(limit:int=Query(30,ge=1,le=100)):return {'items':store.events(limit)}

    return app

app=create_app()