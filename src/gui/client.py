import asyncio
import json
import traceback
from functools import partial

import aiohttp
from common.const import CMD_PING, COOKIE_LOGIN, COOKIE_USERID
from common.playlist import PlaylistMessage
from common.timer import Timer
from common.utils import MyEncoder
from kivy.logger import Logger


class PlsClientJob:
    def __init__(self, msg, callback, waitfor):
        self.msg = msg
        self.callback = callback
        self.waitfor = waitfor
        self.timer = None

    def stop(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

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
        self.single_action_task = None
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
        if timeout is not None and timeout > 0:
            self.timeout = timeout
        if retry is not None and retry >= 1:
            self.retry = retry

    def enqueue(self, msg, callback, waitfor=True):
        self.ws_queue.append(PlsClientJob(msg, callback, waitfor))
        self.ws_event.set()

    def start_login_process(self, on_login=None):
        self.on_login = on_login
        self.timer_login(delay=2)

    def timer_login(self, delay=5):
        if not self.login_t:
            self.login_t = Timer(delay, self.timer_login_callback)

    def is_logged_in(self):
        return self.login_t is None and self.login_h is not None and\
            self.user_h is not None

    async def on_login_caller(self, client, rv, **kwargs):
        Logger.debug("Client: Onlogin: %s" % str(rv))
        self.login_t = None
        if self.on_login:
            await self.on_login(self, rv, **kwargs)

    async def timer_login_callback(self):
        Logger.debug("Client: Trying to login: %s@%s:%d" % (self.username, self.host, self.port))
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
            Logger.error("Client: " + traceback.format_exc())
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
            username=self.username,
            password=self.password
        )
        url = 'http://%s:%d/%s' % (
            self.host,
            self.port,
            urlpart
        )
        Logger.debug("Client: Let's conect to url %s: callback = %s" % (url, str(callback)))
        try:
            if self.login_h is not None:
                cookie = dict()
                cookie[COOKIE_LOGIN] = self.login_h
            else:
                cookie = None
            async with aiohttp.ClientSession(cookies=cookie) as session:
                async with session.post(url, data=payload, allow_redirects=False) as resp:
                    Logger.debug("Client: Resp received: status = %d Cookies = %s" % (resp.status, str(resp.cookies)))
                    # Logger.debug("Client: Cookies = [%s] = %s, [%s] = %s" % (COOKIE_LOGIN, resp.cookies.get(COOKIE_LOGIN).value, COOKIE_USERID, resp.cookies.get(COOKIE_USERID).value))
                    for cookie in session.cookie_jar:
                        Logger.debug("Client: cookie.key = %s %s" % (str(cookie.key), str(cookie)))
                    if resp.status == 302 or resp.status == 200:
                        if self.login_h is None:
                            c = resp.cookies.get(COOKIE_LOGIN)
                            if c:
                                self.login_h = c.value
                        if self.user_h is None:
                            c = resp.cookies.get(COOKIE_USERID)
                            if c:
                                self.user_h = int(c.value)
                        # cookies = {'cookies_are': 'working'}
                        # async with ClientSession(cookies=cookies) as session:
                        # Logger.debug("Client: Cookies = %s Body %s" % (str(resp.cookies), await resp.text()))
                        Logger.info("Client: l = %s, u = %s", str(self.login_h), str(self.user_h))
                        if urlpart != "login" or (self.login_h is not None and self.user_h is not None):
                            # toast("Registration OK")
                            if callback:
                                await callback(self, 0, userid=self.user_h)
                            return True
                        elif callback:
                            await callback(self, "Invalid conection cookies")
                    elif callback:
                        Logger.debug("Client: calling calback 1")
                        await callback(self, "%s failed: %d received" % (urlpart, resp.status))
        except Exception:
            if callback:
                await callback(self, "Registration network error")
            Logger.error("Client: " + traceback.format_exc())
        Logger.debug("Client: exiting %s" % urlpart)
        return False

    async def _re_queue(self, job):
        self.enqueue(job.msg, job.callback, job.waitfor)

    async def single_action(self, ws, job, send=True):
        if send:
            Logger.debug("Client: Sending %s" % job.msg)
            await ws.send_str(json.dumps(job.msg, cls=MyEncoder))
        if job.waitfor:
            resp = await ws.receive()
            Logger.debug("Client: Received {}".format(resp.data))
            p = PlaylistMessage(None, json.loads(resp.data))
            Logger.debug("Client: Converted {}".format(str(p)))
            waitv = p.f('wait')
            if waitv and not self.stopped:
                Logger.debug(f'I have to wait {waitv}')
                job.timer = Timer(waitv, partial(self._re_queue, job))
            return waitv if waitv else p
        else:
            return None

    async def stop(self):
        self.stopped = True
        for it in self.ws_queue:
            await it.call(self, None)
        del self.ws_queue[:]
        self.ws_event.set()
        if self.single_action_task:
            self.single_action_task.cancel()
            try:
                await self.single_action_task
            except asyncio.CancelledError:
                pass
            self.single_action_task = None
        if self.login_t:
            self.login_t.cancel()
            self.login_t = None
        self.login_h = None
        self.user_h = None

    async def process_queue(self, ws):
        if len(self.ws_queue):
            it = self.ws_queue[0]
            rv = None
            i = 0
            while i < self.retry:
                send = True
                i += 1
                while True:
                    if self.stopped:
                        return
                    try:
                        self.single_action_task = asyncio.ensure_future(self.single_action(ws, it, send=send))
                        rv = await asyncio.wait_for(self.single_action_task, self.timeout)
                        self.single_action_task = None
                        if isinstance(rv, int) or not rv.c(CMD_PING):
                            i = self.retry
                            break
                        else:
                            Logger.debug("Ping received: waiting")
                            send = False
                    except (asyncio.TimeoutError, json.decoder.JSONDecodeError):
                        self.single_action_task = None
                        Logger.error("Client: " + traceback.format_exc())
                        break
            del self.ws_queue[0]
            if not isinstance(rv, int):
                await it.call(self, rv)
        elif not self.stopped:
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
                except asyncio.CancelledError:
                    break
                except Exception:
                    await self.stop()
                    self.timer_login()
                    Logger.error("Client: " + traceback.format_exc())
                    break
