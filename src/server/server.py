import argparse
import asyncio
import glob
import logging
import logging.config
import os
import platform
import signal
import traceback
from datetime import datetime, timedelta
from functools import partial
from os.path import basename, dirname, isfile, join, splitext

import aiohttp_cors
import aiosqlite
import certifi
from aiohttp import web
from aiohttp_security import setup as setup_security
from aiohttp_session import setup as setup_session
from redis import asyncio as aioredis

from common.const import COOKIE_LOGIN, COOKIE_SID, COOKIE_USERID
from common.utils import asyncio_graceful_shutdown
from server.dict_auth_policy import DictAuthorizationPolicy
from server.pls.refreshmessageprocessor import RefreshMessageProcessor
from server.redis_storage import RedisKeyStorage
from server.session_cookie_identity import SessionCookieIdentityPolicy
from server.telegram_bot import start_telegram_bot, stop_telegram_bot
from server.webhandlers import (download, img_link, index, login, login_g, logout,
                                modify_pw, playlist_m3u, pls_h,
                                redirect_till_last, register, remote_command,
                                telegram_command, twitch_redir_do,
                                youtube_dl_do, youtube_redir_do)

__prog__ = "mfz-playlist-manager"

_LOGGER = logging.getLogger(__name__)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'local': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        }
    },
    'handlers': {
        'console2': {
            'class': 'logging.StreamHandler',
            'formatter': 'local',
            'stream': 'ext://sys.stdout'
        },
    },
    'root': {
        'handlers': ['console2'],
    },
    # 'loggers': {
    #     'server': {
    #         'handlers': ['console2']
    #     },
    #     'webhandlers': {
    #         'handlers': ['console2']
    #     },
    #     'sqliteauth': {
    #         'handlers': ['console2']
    #     },
    #     'common': {
    #         'handlers': ['console2']
    #     },
    #     'pls': {
    #         'handlers': ['console2']
    #     },
    # }
}

# https://github.com/AndreMiras/p4a-service-sticky/blob/develop/main.py
# https://github.com/kivy/kivy/wiki/Background-Service-using-P4A-android.service


class Executor:
    """In most cases, you can just use the 'execute' instance as a
    function, i.e. y = await execute(f, a, b, k=c) => run f(a, b, k=c) in
    the executor, assign result to y. The defaults can be changed, though,
    with your own instantiation of Executor, i.e. execute =
    Executor(nthreads=4)"""
    def __init__(self, loop=None, nthreads=1):
        from concurrent.futures import ThreadPoolExecutor
        self._ex = ThreadPoolExecutor(nthreads)
        self._loop = loop

    def halt(self):
        try:
            self._ex.shutdown(cancel_futures=True)
        except (Exception, asyncio.CancelledError):
            pass

    def __call__(self, f, *args, **kw):
        return self._loop.run_in_executor(self._ex, partial(f, *args, **kw))


CREATE_DB_IF_NOT_EXIST = [
    '''
    CREATE TABLE IF NOT EXISTS user(
        rowid INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        conf TEXT,
        tg TEXT
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS type(
        rowid INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS playlist(
        rowid INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        user INTEGER NOT NULL,
        type INTEGER NOT NULL,
        dateupdate INTEGER,
        autoupdate INTEGER NOT NULL DEFAULT 0,
        conf TEXT,
        FOREIGN KEY (user)
            REFERENCES user (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE,
        FOREIGN KEY (type)
            REFERENCES type (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE,
        UNIQUE(name,user)
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS playlist_item(
        rowid INTEGER PRIMARY KEY,
        title TEXT,
        img TEXT,
        datepub DATETIME,
        link TEXT NOT NULL,
        uid TEXT NOT NULL,
        playlist INTEGER NOT NULL,
        dur INTEGER NOT NULL,
        conf TEXT,
        dl TEXT,
        seen DATETIME,
        iorder INTEGER NOT NULL,
        UNIQUE(uid, playlist),
        UNIQUE(playlist, iorder),
        FOREIGN KEY (playlist)
            REFERENCES playlist (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    )
    ''',
    '''
    CREATE INDEX IF NOT EXISTS playlist_item_iorder
        ON playlist_item (iorder)
    ''',
    '''
    PRAGMA foreign_keys = ON
    '''
]


async def _init_db(app, create_db=False):
    db = await aiosqlite.connect(app.p.args['dbfile'])
    processors = dict()
    if not isinstance(db, aiosqlite.Connection):
        db = None
    else:
        db.row_factory = aiosqlite.Row
        if create_db:
            for q in CREATE_DB_IF_NOT_EXIST:
                await db.execute(q)
            await db.commit()
        import importlib
        modules = glob.glob(join(dirname(__file__), "pls", "*.py*"))
        pls = [splitext(basename(f))[0] for f in modules if isfile(f)]
        for x in pls:
            if x not in processors:
                try:
                    m = importlib.import_module("server.pls." + x)
                    cla = getattr(m, "MessageProcessor")
                    if cla:
                        dct = dict()
                        for k, v in app.p.args.items():
                            if k.startswith(x + '_'):
                                k2 = k[len(x) + 1:]
                                if k2:
                                    dct[k2] = v
                            else:
                                dct[k] = v
                        processors[x] = cla(db, **dct)
                        if x != "common" and create_db:
                            await db.execute("INSERT OR IGNORE INTO type(name) VALUES (?)", (x,))
                except Exception:
                    _LOGGER.warning(traceback.format_exc())
        if create_db:
            await db.commit()
    return db, processors


async def init_db(app):
    app.p.db, app.p.processors = await _init_db(app, True)
    app.p.db2, app.p.processors2 = await _init_db(app, False)


def init_auth(app):
    app.p.redis = aioredis.from_url(app.p.args['redis'], encoding="utf-8", decode_responses=False)
    term = f'_{app.p.args["sid"]}'
    csid = COOKIE_SID + term
    storage = RedisKeyStorage(cookie_name=csid, httponly=True, redis_pool=app.p.redis)
    setup_session(app, storage)

    policy = SessionCookieIdentityPolicy(sid_key=csid, login_key=COOKIE_LOGIN + term, user_key=COOKIE_USERID + term)
    setup_security(app, policy, DictAuthorizationPolicy())


async def wait_until(dt):
    # sleep until the specified datetime
    now = datetime.now()
    await asyncio.sleep((dt - now).total_seconds())


async def run_at(dt, coro):
    olddate = dt if dt else datetime.now()
    if dt:
        _LOGGER.info(f'I will wait till {dt.strftime("%d/%m/%Y, %H:%M:%S")}')
        await wait_until(dt)
    await coro()
    asyncio.create_task(run_at(olddate + timedelta(days=1), coro))


async def do_auto_refresh(app):
    for k, p in app.p.processors.items():
        _LOGGER.debug(f'Checking {k}')
        if isinstance(p, RefreshMessageProcessor):
            await p.processAutoRefresh(app.p.executor)


async def start_app(app):
    cors = aiohttp_cors.setup(app)
    _LOGGER.info("Setting up")
    init_auth(app)
    runner = web.AppRunner(app)
    app.p.myrunners.append(runner)
    app.p.executor = Executor(loop=app.p.loop, nthreads=app.p.args["executors"])
    if app.p.args["static"] is not None:
        app.router.add_static('/static', app.p.args["static"], follow_symlinks=True)
    app.router.add_route('GET', '/', index)
    app.router.add_route('GET', '/rcmd/{hex:[a-fA-F0-9]+}', remote_command)
    app.router.add_route('GET', '/telegram/{hex:[a-fA-F0-9]+}', telegram_command)
    app.router.add_route('POST', '/login_g', login_g)
    app.router.add_route('POST', '/login', login)
    app.router.add_route('get', '/dl/{rowid:[0-9]+}', download)
    app.router.add_route('POST', '/modifypw', modify_pw)
    app.router.add_route('POST', '/register', register)
    app.router.add_route('GET', '/logout', logout)
    resource = cors.add(app.router.add_resource("/m3u"))
    cors.add(resource.add_route('GET', playlist_m3u), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/red"))
    cors.add(resource.add_route('GET', redirect_till_last), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/ytdl"))
    cors.add(resource.add_route('GET', youtube_dl_do), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/ytto"))
    cors.add(resource.add_route('GET', youtube_redir_do), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/twi"))
    cors.add(resource.add_route('GET', twitch_redir_do), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/img"))
    cors.add(resource.add_route('GET', img_link), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    app.router.add_route('GET', '/ws', pls_h)
    await runner.setup()
    _LOGGER.info("Creating site (%s:%d)" % (app.p.args["host"], app.p.args["port"]))
    site = web.TCPSite(runner, app.p.args["host"], app.p.args["port"])
    await site.start()
    au = app.p.args["autoupdate"]
    if au >= 0 and au <= 23:
        now = datetime.now()
        if now.hour > au:
            now += timedelta(days=1)
            now = now.replace(hour=au)
            asyncio.create_task(run_at(now, partial(do_auto_refresh, app)))
        elif now.hour == au:
            asyncio.create_task(run_at(None, partial(do_auto_refresh, app)))
        else:
            now = now.replace(hour=au)
            asyncio.create_task(run_at(now, partial(do_auto_refresh, app)))
    _LOGGER.info("Start finished")


class Object:
    pass


def raise_system_exit():
    raise SystemExit


def handle_loop_exceptions(loop, context):
    if "exception" in context and context["exception"]:
        fmt = f': {traceback.format_exception(context["exception"])}'
    else:
        fmt = ''
    _LOGGER.error(f'Loop exception: {context["message"]}{fmt}')


def main():
    app = web.Application()
    app.p = Object()
    app.p.ws = dict()
    app.p.myrunners = []
    # Here's all the magic !
    os.environ['SSL_CERT_FILE'] = certifi.where()
    parser = argparse.ArgumentParser(prog=__prog__)
    parser.add_argument('--port', type=int, help='port number', required=False, default=8080)
    parser.add_argument('--autoupdate', type=int, help='autoupdate time', required=False, default=25)
    parser.add_argument('--client-id', help='Google client id', required=False, default='')
    parser.add_argument('--executors', type=int, help='executor number', required=False, default=2)
    parser.add_argument('--static', required=False, default=None)
    parser.add_argument('--redis', required=False, default='redis://localhost/0')
    parser.add_argument('--pid', required=False, default=None)
    parser.add_argument('--sid', required=False, default='')
    parser.add_argument('--pickle', required=False, default='')
    parser.add_argument('--telegram', required=False, default='')
    parser.add_argument('--common-dldir', required=False, default='')
    parser.add_argument('--youtube-apikey', required=False, default="")
    parser.add_argument('--localfolder-basedir', required=False, default=None)
    parser.add_argument('--host', required=False, default="0.0.0.0")
    parser.add_argument('--dbfile', required=False, help='DB file path', default=join(dirname(__file__), '..', 'maindb.db'))
    parser.add_argument("-v", "--verbose", help="increase output verbosity",
                        action="store_true")
    args = vars(parser.parse_args())
    if args["verbose"]:
        logging.basicConfig(level=logging.DEBUG)
    logging.config.dictConfig(LOGGING)
    app.p.args = args
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_loop_exceptions)
    app.p.loop = loop
    _LOGGER.info(f"Starting server main loop is {loop}, args is {args}")
    if 'pid' in args and args['pid']:
        with open(args['pid'], "w") as f:
            f.write(str(os.getpid()))
    try:
        loop.run_until_complete(init_db(app))
        loop.run_until_complete(start_app(app))
        loop2 = None
        if app.p.args['telegram']:
            loop2 = asyncio.new_event_loop()
            loop2.set_exception_handler(handle_loop_exceptions)
            app.p.telegram_executor = Executor(loop=loop2, nthreads=3)
            app.p.telegram_executor(start_telegram_bot, app.p, loop2)
        if platform.system() != "Windows":
            stop_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)
            for sig in stop_signals:
                loop.add_signal_handler(sig, raise_system_exit)
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            # loop.run_forever()
            _LOGGER.debug("I am in finally branch")
            loop.run_until_complete(asyncio_graceful_shutdown(loop, _LOGGER, False))
            if app.p.args['telegram']:
                loop2.create_task(stop_telegram_bot())
                app.p.telegram_executor.halt()
            for r in app.p.myrunners:
                loop.run_until_complete(r.cleanup())
            if app.p.db:
                loop.run_until_complete(app.p.db.close())
            if app.p.db2:
                loop.run_until_complete(app.p.db2.close())
            if app.p.executor:
                app.p.executor.halt()
            if app.p.redis:
                loop.run_until_complete(app.p.redis.close())
            _LOGGER.debug("Server: Closing loop")
            loop.close()
        except Exception:
            _LOGGER.error("Server: " + traceback.format_exc())


_LOGGER.info("Server module name is %s" % __name__)
if __name__ == '__main__':
    main()
