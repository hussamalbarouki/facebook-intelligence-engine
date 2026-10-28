"""Same-origin protected noVNC endpoints.

The administrative key is only sent via X-API-Key in a POST request. A short
HttpOnly, Secure, SameSite=Strict cookie controls both the VNC websocket and
the Save & Close button. Neither the key nor a session token appears in URLs.
"""
from __future__ import annotations
import asyncio
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from fastapi import FastAPI, Depends, HTTPException, Request, Response, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect
from .browser_login import LoginSession,profile_ready,VNC_PORT

COOKIE_NAME='fb_browser_controller'

def _origin_allowed(origin,host):
    if not origin or not host:return False
    try:
        o=urlsplit(origin)
        return (o.hostname or '').lower()==host.split(':')[0].lower() and (
            o.scheme=='https' or
            (o.scheme=='http' and o.hostname in ('localhost','127.0.0.1','testserver')))
    except ValueError:return False

def _cookie(request):
    return request.cookies.get(COOKIE_NAME,'')

def install(app:FastAPI,manager:LoginSession,authorize):
    directory=Path(__file__).resolve().parent/'ui'
    app.mount('/browser-ui',StaticFiles(directory=str(directory)),name='browser-ui')
    app.mount('/browser-assets',StaticFiles(directory='/usr/share/novnc',check_dir=False),name='browser-assets')

    @app.get('/browser-login',response_class=HTMLResponse,include_in_schema=False)
    def browser_login():
        page=(directory/'login.html').read_text(encoding='utf-8')
        return HTMLResponse(page,headers={
            'Cache-Control':'no-store',
            'Referrer-Policy':'no-referrer',
            'X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' wss: ws:; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            'X-Frame-Options':'DENY'})

    @app.post('/v1/browser-session/start',dependencies=[Depends(authorize)])
    def start_session(request:Request,response:Response):
        if not _origin_allowed(request.headers.get('origin'),request.headers.get('host')):
            raise HTTPException(status_code=403,detail='Same-origin admin page required')
        try:token=manager.start()
        except RuntimeError as ex:raise HTTPException(status_code=409,detail=str(ex)) from None
        response.set_cookie(COOKIE_NAME,token,max_age=3600,secure=True,
                            httponly=True,samesite='strict',path='/')
        response.headers['Cache-Control']='no-store'
        return {'active':True,'profile_saved':profile_ready(manager.root),
                'remaining_seconds':1200}

    @app.get('/v1/browser-session/status')
    def session_status(request:Request):
        token=_cookie(request)
        if not manager.authorize(token,touch=True):
            raise HTTPException(status_code=401,detail='Browser admin session not active')
        return manager.status(token)

    @app.post('/v1/browser-session/save')
    def session_save(request:Request,response:Response):
        if not _origin_allowed(request.headers.get('origin'),request.headers.get('host')):
            raise HTTPException(status_code=403,detail='Invalid origin')
        try:
            out=manager.save(_cookie(request))
        except RuntimeError:
            raise HTTPException(status_code=401,detail='Browser admin session not active') from None
        response.delete_cookie(COOKIE_NAME,path='/',secure=True,samesite='strict')
        response.headers['Cache-Control']='no-store'
        return out

    @app.websocket('/v1/browser-session/stream')
    async def stream_vnc(ws:WebSocket):
        origin=ws.headers.get('origin')
        host=ws.headers.get('host')
        token=ws.cookies.get(COOKIE_NAME,'')
        if not _origin_allowed(origin,host) or not manager.authorize(token,touch=True):
            await ws.close(code=1008)
            return
        try:
            reader,writer=await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1',VNC_PORT),timeout=3)
        except (OSError,asyncio.TimeoutError):
            await ws.close(code=1011)
            return
        await ws.accept()
        async def vnc_to_browser():
            while True:
                chunk=await reader.read(65536)
                if not chunk:break
                if not manager.authorize(token,touch=True):break
                await ws.send_bytes(chunk)
        async def browser_to_vnc():
            while True:
                message=await ws.receive()
                if message['type']=='websocket.disconnect':break
                if not manager.authorize(token,touch=True):break
                data=message.get('bytes')
                if data is None:
                    text=message.get('text')
                    data=text.encode('latin-1') if text else b''
                if data:
                    writer.write(data)
                    await writer.drain()
        tasks=[asyncio.create_task(vnc_to_browser()),
               asyncio.create_task(browser_to_vnc())]
        try:
            done,pending=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
        finally:
            writer.close()
            try:await writer.wait_closed()
            except Exception:pass
            try:await ws.close()
            except Exception:pass
