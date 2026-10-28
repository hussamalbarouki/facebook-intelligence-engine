"""Local-only VNC browser login manager.

All control traffic runs through authenticated, same-origin FastAPI endpoints.
VNC TCP is bound to 127.0.0.1 inside the container. NoVNC's JS client is
served as static assets; no server credentials are embedded in HTML.
"""
from __future__ import annotations
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time

from .read_only_v2 import LOCK

SESSION_IDLE_SECONDS=20*60
SESSION_MAX_SECONDS=60*60
VNC_PORT=5901

def profile_ready(root: str|Path|None=None)->bool:
    base=Path(root or os.getenv('DATA_DIR','/data'))
    return (base/'facebook-profile-ready.json').is_file() and (base/'facebook-profile').is_dir()

def _tcp_ready():
    try:
        with socket.create_connection(('127.0.0.1',VNC_PORT),timeout=0.3):
            return True
    except OSError:
        return False

class LoginSession:
    def __init__(self,root):
        self.root=Path(root)
        self.lock=threading.RLock()
        self.chrome=None
        self.vnc=None
        self.token=None
        self.expires_at=0.0
        self.hard_expires_at=0.0
        self.last_error=None

    def _active_unlocked(self):
        return self.chrome is not None and self.chrome.poll() is None

    def _end_unlocked(self):
        # A SIGTERM tells the worker to gracefully close its persistent
        # Chromium profile and flush it before the process exits.
        child=self.chrome
        vnc=self.vnc
        self.chrome=None
        self.vnc=None
        self.token=None
        self.expires_at=0
        self.hard_expires_at=0
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=17)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=4)
                self.last_error='BROWSER_CLOSE_TIMEOUT'
        if vnc is not None and vnc.poll() is None:
            vnc.terminate()
            try:vnc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                vnc.kill()
        # Worker's browser is completely closed before the lock is released.
        if getattr(self,'_lock_owned',False):
            LOCK.release()
            self._lock_owned=False

    def _expire_unlocked(self):
        if self.chrome and self.chrome.poll() is not None:
            self.last_error='BROWSER_LOGIN_PROCESS_EXITED'
            self._end_unlocked()
        elif self._active_unlocked() and (time.monotonic()>self.expires_at or
                                          time.monotonic()>self.hard_expires_at):
            self.last_error='BROWSER_LOGIN_TIMEOUT'
            self._end_unlocked()

    def active(self):
        with self.lock:
            self._expire_unlocked()
            return self._active_unlocked()

    def start(self):
        with self.lock:
            self._expire_unlocked()
            if self._active_unlocked():
                # A successful reauthentication with the main admin API key
                # takes over a disconnected controller, without restarting
                # the persistent browser or releasing its profile lock.
                self.token=secrets.token_urlsafe(32)
                self.expires_at=min(self.hard_expires_at,time.monotonic()+SESSION_IDLE_SECONDS)
                return self.token
            if not LOCK.acquire(blocking=False):
                raise RuntimeError('BROWSER_RESOURCE_BUSY')
            self._lock_owned=True
            self.last_error=None
            try:
                env={**os.environ,'DATA_DIR':str(self.root),'DISPLAY':':99'}
                # x11vnc is deliberately not exposed by Docker/Coolify. It
                # listens only on 127.0.0.1 INSIDE this container.
                self.vnc=subprocess.Popen([
                    'x11vnc','-display',':99','-rfbport',str(VNC_PORT),
                    '-localhost','-nopw','-forever','-shared','-noxdamage',
                    '-quiet','-nosel'],env=env,stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(40):
                    if _tcp_ready():break
                    if self.vnc.poll() is not None:
                        raise RuntimeError('VNC_DISPLAY_UNAVAILABLE')
                    time.sleep(0.2)
                else:
                    raise RuntimeError('VNC_DISPLAY_UNAVAILABLE')
                self.chrome=subprocess.Popen(
                    [sys.executable,'-m','app.profile_login_worker'],
                    cwd='/service',env=env,stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                # Catch immediate chromium launch errors.
                time.sleep(0.5)
                if self.chrome.poll() is not None:
                    raise RuntimeError('BROWSER_LOGIN_LAUNCH_FAILED')
                self.token=secrets.token_urlsafe(32)
                self.hard_expires_at=time.monotonic()+SESSION_MAX_SECONDS
                self.expires_at=time.monotonic()+SESSION_IDLE_SECONDS
                return self.token
            except Exception:
                self._end_unlocked()
                raise

    def authorize(self,token,touch=False):
        with self.lock:
            self._expire_unlocked()
            valid=(isinstance(token,str) and bool(self.token)
                   and secrets.compare_digest(token,self.token)
                   and self._active_unlocked())
            if valid and touch:
                self.expires_at=min(self.hard_expires_at,time.monotonic()+SESSION_IDLE_SECONDS)
            return valid

    def status(self, token=None):
        with self.lock:
            self._expire_unlocked()
            authorized=self.authorize(token) if token else False
            return {'profile_saved':profile_ready(self.root),
                    'login_active':self._active_unlocked(),
                    'controller_authorized':authorized,
                    'remaining_seconds':max(0,int(self.expires_at-time.monotonic())) if authorized else 0,
                    'last_error':self.last_error if authorized else None,
                    'note':'Saved browser data are not proof Facebook still accepts this session.'}

    def save(self,token):
        with self.lock:
            if not self.authorize(token):
                raise RuntimeError('BROWSER_CONTROLLER_UNAUTHORIZED')
            self._end_unlocked()
            return {'saved':profile_ready(self.root),
                    'note':'Browser closed and profile flushed; Facebook may later require login again.'}

    def shutdown(self):
        with self.lock:
            self._end_unlocked()

    def sweep(self):
        with self.lock:
            self._expire_unlocked()
