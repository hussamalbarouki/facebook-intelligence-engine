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
from .engine import scrape_post, validate_facebook_url, ExtractionError, parse_post_reference, is_share_link
from .facebook_session import probe_cookie_file, probe_post_access
from .secrets import CookieVault
from .storage import JobStore
from .browser_login import LoginSession,profile_ready
from .browser_login_routes import install as install_browser_login

VERSION='2.1.1'
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
    login_manager=LoginSession(root)
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
            # Never read an in-use Chrome user profile. Jobs stay queued
            # while the administrator is entering or saving a login.
            login_manager.sweep()
            if login_manager.active():
                stop.wait(1);continue
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
            except ExtractionError as exc:
                log.warning('Extraction failed for job %s: %s',row['id'],exc.code)
                store.finish(row['id'],error=exc.code)
            except ImportError as exc:
                log.exception('Dependency import failed for job %s',row['id'])
                store.finish(row['id'],error='DEPENDENCY_IMPORT_ERROR')
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
        login_manager.shutdown()
        t.join(timeout=4)

    def facebook_credentials_status():
        c=vault.status()
        if profile_ready(root):
            return {**c,'configured':True,'source':'saved_browser_profile',
                    'message':'Persistent Chrome profile saved; Facebook may require reauthentication.'}
        return {**c,'source':'manual_cookies' if c['configured'] else 'none'}

    app=FastAPI(title='Facebook Intelligence Engine',version=VERSION,description='Self-hosted extraction API. Facebook scraping results can be incomplete.',lifespan=lifespan)
    app.state.store=store;app.state.vault=vault
    app.state.login_manager=login_manager
    install_browser_login(app,login_manager,authorize)

    @app.get('/healthz',include_in_schema=False)
    def health():return {'ok':True,'service':'facebook-intelligence-engine','version':VERSION}

    @app.get('/v1/capabilities',dependencies=[Depends(authorize)])
    def capabilities():
        return {'version':VERSION,'adapter':'read-only-v2-playwright-engine','supports':['session_diagnostics','posts','comments','comment_replies','reactors','reaction_types','cookie_management','jobs','pagination'],
                'limits':{'comments':1000,'reactors':1000},'known_limitations':['Facebook may require cookies or block scraping','Reaction lists may be partial','No live Facebook extraction test is performed in CI','Accessible sessions do not guarantee all posts are readable','Playwright browser results are partial and capped at 100 interactions per kind per attempt','Browser fallback can be disabled with FB_BROWSER_ENABLED=0']}

    @app.get('/v1/status',dependencies=[Depends(authorize)])
    def status():
        return {'ok':True,'version':VERSION,'adapter':'read-only-v2-playwright-engine',
                'cookies':facebook_credentials_status(),'saved_browser_profile':profile_ready(root),
                'browser_login_active':login_manager.active(),
                'settings':store.settings(),'queue':store.metrics()}

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
    def cookies_status():return facebook_credentials_status()

    @app.put('/v1/facebook/cookies',dependencies=[Depends(authorize)])
    def cookies_put(body:CookieUpload):
        try:return vault.save(body.cookies)
        except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from None

    @app.delete('/v1/facebook/cookies',dependencies=[Depends(authorize)])
    def cookies_delete():return vault.delete()

    @app.get('/v1/facebook/session-check',dependencies=[Depends(authorize)])
    def session_check():
        if profile_ready(root):
            return {'status':'browser_profile_saved','browser_profile_saved':True,
                    'token_available':False,
                    'note':'Chrome profile exists; acceptance by Facebook is checked during extraction.'}
        with vault.temporary_cookie_file() as cookie_path:
            return probe_cookie_file(cookie_path)

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

    @app.get('/v1/jobs/{job_id}/diagnostics',dependencies=[Depends(authorize)])
    def diagnose_job(job_id:str):
        """Read-only session diagnosis of the stored post URL; never expose cookies."""
        row=store.get(job_id)
        if not row:raise HTTPException(status_code=404,detail='Job not found')
        # URL was validated at creation, and is never accepted as arbitrary host.
        kind=parse_post_reference(row['url'])
        with vault.temporary_cookie_file() as cookie_path:
            result=probe_post_access(cookie_path,row['url'])
        return {'job_id':job_id,'reference_kind':kind[0] if kind else 'opaque_share' if is_share_link(row['url']) else 'unsupported','graphql_candidate':bool(kind) or is_share_link(row['url']),**result}

    @app.post('/v1/jobs/{job_id}/browser-diagnostics',dependencies=[Depends(authorize)])
    def diagnose_browser_job(job_id:str):
        """Run a read-only browser inspection on the same job URL and stored session.

        Returns aggregate structure/visibility counters only. No page HTML,
        comments, names, Facebook response bodies, CSRF tokens or cookies.
        """
        row=store.get(job_id)
        if not row:raise HTTPException(status_code=404,detail='Job not found')
        try:
            with vault.temporary_cookie_file() as cookie_path:
                saved=profile_ready(root)
                if not cookie_path and not saved:
                    raise HTTPException(status_code=409,detail='No stored Facebook browser profile or cookies')
                from .engine import resolve_share_link
                from .read_only_v2 import run as scrape_with_browser
                url=row['url']
                if is_share_link(url) and not saved:
                    url,_=resolve_share_link(url,cookie_path)
                diagnostics=scrape_with_browser(
                    url,min(row['comment_limit'],10),min(row['reactor_limit'],10),
                    cookie_path,diagnostic_only=True)
                return {'job_id':job_id,**diagnostics}
        except HTTPException:
            raise
        except Exception as exc:
            code=str(exc) if type(exc) is RuntimeError else type(exc).__name__
            if code not in ('BROWSER_RESOURCE_BUSY','BROWSER_DISABLED',
                            'FACEBOOK_LOGIN_REQUIRED','FACEBOOK_LOGIN_WALL_VISIBLE',
                            'FACEBOOK_COOKIES_SCOPE_MISMATCH','FACEBOOK_CHECKPOINT_REQUIRED',
                            'FACEBOOK_SHARE_LINK_UNRESOLVED'):
                code='BROWSER_DIAGNOSTIC_UNAVAILABLE'
            return {'job_id':job_id,'status':'diagnostic_failed','code':code}

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