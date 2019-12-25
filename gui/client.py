import asyncio
import json
import traceback

import aiohttp
from kivy.logger import Logger

from common.const import COOKIE_LOGIN, COOKIE_USERID
from common.playlist import PlaylistMessage
from common.timer import Timer


class PlsClientJob:
    def __init__(self, msg, callback, waitfor):
        self.msg = msg
        self.callback = callback
        self.waitfor = waitfor

    async def call(self, client, m):
        if self.callback:
            await self.callback(client, self.msg, m)


class PlsClient:
    def __init__(self, host=None, port=None, username=None, password=None, timeout=None, retry=None):
        self.host = "127.0.0.1"
        self.port = 8080
        self.username = ""
        self.password = ""
        self.timeout = 60
        self.retry = 3
        self.set_pars(host, port, username, password, timeout, retry)
        self.login_h = None
        self.user_h = None
        self.login_t = None
        self.ws_queue = []
        self.stopped = True
        self.on_login = None
        self.ws_event = asyncio.Event()

    def set_pars(self, host=None, port=None, username=None, password=None, timeout=None, retry=None):
        if host:
            self.host = host
        if port:
            self.port = port
        if username:
            self.username = username
        if password:
            self.password = password
        if timeout is not None:
            self.timeout = timeout
        if retry is not None:
            self.retry = retry

    def enqueue(self, msg, callback, waitfor=True):
        self.ws_queue.append(PlsClientJob(msg, callback, waitfor))
        self.ws_event.set()

    def start_login_process(self, on_login=None):
        self.on_login = on_login
        self.timer_login()

    def timer_login(self):
        if not self.login_t:
            self.login_t = Timer(10, self.timer_login_callback)

    async def on_login_caller(self, rv, **kwargs):
        self.login_t = None
        if self.on_login:
            await self.on_login(self, rv, **kwargs)

    async def timer_login_callback(self):
        if not await self.register(urlpart='login', callback=self.on_login_caller):
            self.timer_login()

    async def logout(self, on_logout=None):
        url = 'http://%s:%d/%s' % (
            self.host,
            self.port,
            'logout'
        )
        if self.login_h is not None:
            cookie = dict()
            cookie[COOKIE_LOGIN] = self.login_h
        elif on_logout:
            on_logout(self, 0)
            return True
        try:
            async with aiohttp.ClientSession(cookies=cookie) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        self.login_h = None
                        self.user_h = None
                        # self.timer_login()
                        # toast("Logout OK")
                        if on_logout:
                            on_logout(self, 0)
                        return True
        except Exception:
            Logger.error(traceback.format_exc())
        if on_logout:
            on_logout(self, "Cannot connect")
        return False

    def m3u_lnk(self, name):
        import urllib.parse
        url = 'http://%s:%d/%s?' % (
            self.host,
            self.port,
            "m3u"
        )
        params = dict(username=self.username, name=name)
        return url + urllib.parse.urlencode(params)

    async def register(self, urlpart='register', callback=None):
        payload = dict(
            form=dict(
                username=self.username,
                password=self.password
            )
        )
        url = 'http://%s:%d/%s' % (
            self.host,
            self.port,
            urlpart
        )
        try:
            if self.login_h is not None:
                cookie = dict()
                cookie[COOKIE_LOGIN] = self.login_h
            else:
                cookie = None
            async with aiohttp.ClientSession(cookies=cookie) as session:
                async with session.post(url, data=payload) as resp:
                    if resp.status == 200:
                        if self.login_h is None:
                            self.login_h = resp.cookies.get(COOKIE_LOGIN)
                        if self.user_h is None:
                            self.user_h = resp.cookies.get(COOKIE_USERID)
                        # cookies = {'cookies_are': 'working'}
                        # async with ClientSession(cookies=cookies) as session:
                        Logger.info("l = %s, u = %s", str(self.login_h), str(self.user_h))
                        if self.login_h is not None and self.user_h is not None:
                            # toast("Registration OK")
                            if callback:
                                await callback(self, 0, userid=self.user_h)
                            return True
                        elif callback:
                            await callback(self, "Invalid conection cookies")
                    elif callback:
                        await callback(self, "Registration Failed: username taken?")
        except Exception:
            if callback:
                await callback(self, "Registration network error")
            Logger.error(traceback.format_exc())
        return False

        async def single_action(self, ws, job):
            await ws.send_str(json.dumps(job.msg))
            if job.waitfor:
                return PlaylistMessage(None, json.loads(await ws.receive()))
            else:
                return None

        def stop(self):
            self.stopped = True
            self.ws_event.set()

        async def process_queue(self, ws):
            if len(self.ws_queue):
                it = self.ws_queue[0]
                rv = None
                for i in range(self.retry):
                    try:
                        rv = await asyncio.wait_for(self.single_action(ws, it), self.timeout)
                        break
                    except asyncio.TimeoutError:
                        Logger.error(traceback.format_exc())
                    except json.decoder.JSONDecodeError:
                        Logger.error(traceback.format_exc())
                del self.ws_queue[0]
                await it.call(self, rv)
            else:
                self.ws_event.clear()
                await self.ws_event.wait()

        async def estabilish_connection(self):
            if self.login_t or not self.login_h or not self.user_h:
                return False
            else:
                url = 'http://%s:%d/%s' % (
                    self.host,
                    self.port,
                    'ws'
                )
                self.stopped = False
                cookie = dict()
                cookie[COOKIE_LOGIN] = self.login_h
                timeout = aiohttp.ClientTimeout(total=0, connect=30, sock_connect=30)
                while not self.stopped:
                    try:
                        async with aiohttp.ClientSession(cookies=cookie, timeout=timeout) as session:
                            async with session.ws_connect(url) as ws:
                                while not self.stopped:
                                    await self.process_queue(ws)

                    except Exception:
                        Logger.error(traceback.format_exc())
