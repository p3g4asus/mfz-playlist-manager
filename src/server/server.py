import argparse
import asyncio
import logging
import logging.config
import os
import platform
import signal
import time
import traceback
from datetime import datetime, timedelta
from functools import partial
from os.path import dirname, join

import aiohttp_cors
import certifi
from aiohttp import web
from aiohttp_security import setup as setup_security
from aiohttp_session import setup as setup_session
from redis import asyncio as aioredis

from common.const import COOKIE_LOGIN, COOKIE_SID, COOKIE_USERID
from common.utils import asyncio_graceful_shutdown
from server.db import connect_db
from server.dict_auth_policy import DictAuthorizationPolicy
from server.pls.refreshmessageprocessor import RefreshMessageProcessor
from server.redis_storage import RedisKeyStorage
from server.session_cookie_identity import SessionCookieIdentityPolicy
from server.memory_monitor import MemoryMonitor
from server.refresh_diagnostics import RefreshDiagnostics
from server.task_diagnostics import TaskDiagnostics
from server.telegram.main import start_telegram_bot, stop_telegram_bot
from server.webhandlers import (auth_for_item, download, img_link, index, login, login_g, logout,
                                modify_pw, playlist_m3u, pls_h_2, post_proxy,
                                redirect_till_last, register, remote_command,
                                telegram_command, twitch_redir_do, twitch_redir_logged, urlebird_redir_do, urlebird_redir_logged, user_check_call,
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


async def init_db(app, append: str = ''):
    tplo = await connect_db(app.p.args, append)
    setattr(app.p, 'db' + append, tplo[0])
    setattr(app.p, 'processors' + append, tplo[1])
    setattr(app.p, 'types' + append, tplo[2])


async def init_auth(app):
    app.p.redis = aioredis.from_url(app.p.args['redis'], encoding="utf-8", decode_responses=False)
    term = f'_{app.p.args["sid"]}'
    csid = COOKIE_SID + term
    storage = RedisKeyStorage(cookie_name=csid, httponly=True, redis_pool=app.p.redis, max_age=app.p.args['redis_lim'] * 3600)
    setup_session(app, storage)

    policy = SessionCookieIdentityPolicy(sid_key=csid, login_key=COOKIE_LOGIN + term, user_key=COOKIE_USERID + term, max_age=app.p.args['redis_lim'] * 3600)
    await policy.clean_redis_sessions(app.p.redis, app.p.args['redis_lim'] if app.p.args['redis_lim'] >= 0.1 else 7 * 24 * 2)
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
    diagnostics = app.p.refresh_diagnostics
    run_started = time.monotonic()
    run_id = diagnostics.start_run() if diagnostics else None
    outcome = 'ok'
    try:
        for k, p in app.p.processors.items():
            _LOGGER.debug(f'Checking {k}')
            if isinstance(p, RefreshMessageProcessor):
                token = diagnostics.start_processor(run_id, k) if diagnostics else None
                processor_outcome = 'error'
                try:
                    await p.processAutoRefresh(app.p.executor, diagnostics=diagnostics,
                                               run_id=run_id, processor_key=k)
                    processor_outcome = 'ok'
                finally:
                    if diagnostics:
                        diagnostics.end_processor(run_id, k, token, processor_outcome)
    except Exception as exc:
        outcome = f'error_{type(exc).__name__}'
        raise
    finally:
        if diagnostics:
            diagnostics.end_run(run_id, run_started, outcome)


async def start_app(app):
    cors = aiohttp_cors.setup(app)
    _LOGGER.info("Setting up")
    await init_auth(app)
    runner = web.AppRunner(app)
    app.p.myrunners.append(runner)
    app.p.executor = Executor(loop=app.p.loop, nthreads=app.p.args["executors"])
    if app.p.args["static"] is not None:
        app.router.add_static('/static', app.p.args["static"], follow_symlinks=True)
    app.router.add_route('GET', '/', index)
    app.router.add_route('GET', '/auth/{subp:(local|download)}{token:/[a-fA-F0-9\\-]+}/{rowid:[0-9]+}/{fil:.+}', auth_for_item)
    app.router.add_route('GET', '/rcmd/{sfx:[g-z]?}{hex:[a-fA-F0-9]+}', remote_command)
    app.router.add_route('GET', '/telegram/{hex:[a-fA-F0-9]+}', telegram_command)
    app.router.add_route('POST', '/login_g', login_g)
    app.router.add_route('POST', '/login', login)
    app.router.add_route('get', '/dl{token:(/[a-fA-F0-9\\-]+)?}/{rowid:[0-9]+}', partial(user_check_call, method=download))
    app.router.add_route('POST', '/modifypw', modify_pw)
    app.router.add_route('POST', '/register', register)
    app.router.add_route('GET', '/logout', logout)
    resource = cors.add(app.router.add_resource("/m3u{token:(/[a-fA-F0-9\\-]+)?}"))
    cors.add(resource.add_route('GET', partial(user_check_call, method=playlist_m3u)), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/red"))
    cors.add(resource.add_route('GET', redirect_till_last), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/proxy"))
    cors.add(resource.add_route('POST', post_proxy), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/ytdl"))
    cors.add(resource.add_route('GET', youtube_dl_do), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/ytto"))
    cors.add(resource.add_route('GET', youtube_redir_do), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/bird"))
    cors.add(resource.add_route('GET', urlebird_redir_do), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/birds{token:(/[a-fA-F0-9\\-]+)?}/{rowid:[0-9]+}"))
    cors.add(resource.add_route('GET', partial(user_check_call, method=urlebird_redir_logged)), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/twi"))
    cors.add(resource.add_route('GET', twitch_redir_do), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/twis{token:(/[a-fA-F0-9\\-]+)?}/{rowid:[0-9]+}"))
    cors.add(resource.add_route('GET', partial(user_check_call, method=twitch_redir_logged)), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/img"))
    cors.add(resource.add_route('GET', img_link), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
    resource = cors.add(app.router.add_resource("/ws{hex:(/[g-z][a-f0-9]+)?}"))
    cors.add(resource.add_route('GET', pls_h_2), {
        "*": aiohttp_cors.ResourceOptions(allow_credentials=False, expose_headers="*", allow_headers="*")
    })
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
    app.p.myrunners = []
    # Here's all the magic !
    os.environ['SSL_CERT_FILE'] = certifi.where()
    parser = argparse.ArgumentParser(prog=__prog__)
    parser.add_argument('--port', type=int, help='port number', required=False, default=8080)
    parser.add_argument('--redis-lim', type=float, help='Redis session duration (hours)', required=False, default=7 * 24 * 2)
    parser.add_argument('--autoupdate', type=int, help='autoupdate time', required=False, default=25)
    parser.add_argument('--client-id', help='Google client id', required=False, default='')
    parser.add_argument('--executors', type=int, help='executor number', required=False, default=2)
    parser.add_argument('--static', required=False, default=None)
    parser.add_argument('--redis', required=False, default='redis://localhost/0')
    parser.add_argument('--pid', required=False, default=None)
    parser.add_argument('--sid', required=False, default='')
    parser.add_argument('--pickle', required=False, default='')
    parser.add_argument('--telegram', required=False, default='')
    parser.add_argument('--redirect-files', required=False, default=False, action="store_true")
    parser.add_argument('--common-dldir', required=False, default='')
    parser.add_argument('--mediaset-profiledir', required=False, default='/tmp/chrome-profile')
    parser.add_argument('--mediaset-getsmil', required=False, default='playwright')
    parser.add_argument('--mediaset-drmurl', required=False, default='http://127.0.0.1:1337/api/decrypt')
    parser.add_argument('--mediaset-d1', required=False, default=4, type=float)
    parser.add_argument('--mediaset-d2', required=False, default=4, type=float)
    parser.add_argument('--mediaset-d3', required=False, default=65, type=int)
    parser.add_argument('--localfolder-basedir', required=False, default=None)
    parser.add_argument('--host', required=False, default="0.0.0.0")
    parser.add_argument('--dbfile', required=False, help='DB file path', default=join(dirname(__file__), '..', 'maindb.db'))
    parser.add_argument('--memory-log', required=False,
                        default=join(dirname(__file__), '..', '..', 'logs', 'memory-usage.csv'),
                        help='CSV file for periodic process memory samples')
    parser.add_argument('--memory-interval', type=int, default=300,
                        help='seconds between memory samples (minimum 10)')
    parser.add_argument('--memory-monitor', action='store_true',
                        help='enable periodic memory sampling to CSV')
    parser.add_argument('--memory-tracemalloc', action='store_true',
                        help='also track Python allocations with tracemalloc')
    parser.add_argument('--memory-tracemalloc-frames', type=int, default=1,
                        help='maximum traceback frames stored per allocation (1-25)')
    parser.add_argument('--memory-snapshot-interval', type=int, default=0,
                        help='seconds between allocation snapshot comparisons (0 disables them)')
    parser.add_argument('--memory-snapshot-log', required=False,
                        default=join(dirname(__file__), '..', '..', 'logs', 'memory-allocation-diffs.csv'),
                        help='CSV file for periodic allocation snapshot differences')
    parser.add_argument('--refresh-diagnostics', action='store_true',
                        help='write detailed scheduled playlist refresh metrics to CSV')
    parser.add_argument('--refresh-diagnostics-log', required=False,
                        default=join(dirname(__file__), '..', '..', 'logs', 'refresh-diagnostics-detailed.csv'),
                        help='CSV file for scheduled refresh diagnostics')
    parser.add_argument('--refresh-tracemalloc-snapshot', action='store_true',
                        help='compare allocation snapshots before and after each scheduled refresh')
    parser.add_argument('--refresh-snapshot-playlist-ids', default='',
                        help='comma-separated playlist IDs to snapshot before and after refresh')
    parser.add_argument('--task-diagnostics', action='store_true',
                        help='periodically record asyncio task stacks and WebSocket lifetimes')
    parser.add_argument('--task-diagnostics-interval', type=int, default=300,
                        help='seconds between asyncio task censuses (minimum 30)')
    parser.add_argument('--task-diagnostics-log', required=False,
                        default=join(dirname(__file__), '..', '..', 'logs', 'asyncio-task-census.csv'),
                        help='CSV file for periodic asyncio task censuses')
    parser.add_argument('--websocket-diagnostics-log', required=False,
                        default=join(dirname(__file__), '..', '..', 'logs', 'websocket-connections.csv'),
                        help='CSV file for WebSocket open and close events')
    parser.add_argument("-v", "--verbose", help="increase output verbosity",
                        action="store_true")
    args = vars(parser.parse_args())
    if args["verbose"]:
        logging.basicConfig(level=logging.DEBUG)
    logging.config.dictConfig(LOGGING)
    app.p.args = args
    loop = asyncio.new_event_loop()
    # Lo assegni a questo thread
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(handle_loop_exceptions)
    app.p.loop = loop
    _LOGGER.info(f"Starting server main loop is {loop}, args is {args}")
    if 'pid' in args and args['pid']:
        with open(args['pid'], "w") as f:
            f.write(str(os.getpid()))
    try:
        loop2 = None
        memory_task = None
        task_diagnostics_task = None
        app.p.refresh_diagnostics = None
        app.p.task_diagnostics = None
        loop.run_until_complete(init_db(app))
        loop.run_until_complete(start_app(app))
        if app.p.args['telegram']:
            loop2 = asyncio.new_event_loop()
            loop2.run_until_complete(init_db(app, '2'))
            loop2.set_exception_handler(handle_loop_exceptions)
            app.p.telegram_executor = Executor(loop=loop2, nthreads=3)
            app.p.telegram_executor(start_telegram_bot, app.p, loop2)
        if platform.system() != "Windows":
            stop_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)
            for sig in stop_signals:
                loop.add_signal_handler(sig, raise_system_exit)
        if args['memory_monitor'] or args['memory_snapshot_interval'] > 0:
            monitor = MemoryMonitor(args['memory_log'], args['memory_interval'], args['memory_tracemalloc'],
                                    args['memory_snapshot_interval'], args['memory_snapshot_log'],
                                    args['memory_tracemalloc_frames'])
            memory_task = loop.create_task(monitor.run(loop))
        if args['task_diagnostics']:
            app.p.task_diagnostics = TaskDiagnostics(
                args['task_diagnostics_log'], args['websocket_diagnostics_log'],
                args['task_diagnostics_interval'])
            task_diagnostics_task = loop.create_task(app.p.task_diagnostics.run(loop))
        if args['refresh_diagnostics']:
            app.p.refresh_diagnostics = RefreshDiagnostics(args['refresh_diagnostics_log'],
                                                          args['refresh_tracemalloc_snapshot'],
                                                          args['refresh_snapshot_playlist_ids'])
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            # loop.run_forever()
            _LOGGER.debug("I am in finally branch")
            if memory_task:
                memory_task.cancel()
                loop.run_until_complete(asyncio.gather(memory_task, return_exceptions=True))
            if task_diagnostics_task:
                task_diagnostics_task.cancel()
                loop.run_until_complete(asyncio.gather(task_diagnostics_task, return_exceptions=True))
            if app.p.refresh_diagnostics:
                app.p.refresh_diagnostics.close()
            loop.run_until_complete(asyncio_graceful_shutdown(loop, _LOGGER, False))
            if loop2 and app.p.args['telegram']:
                loop2.create_task(stop_telegram_bot())
                app.p.telegram_executor.halt()
            for r in app.p.myrunners:
                loop.run_until_complete(r.cleanup())
            if app.p.db:
                loop.run_until_complete(app.p.db.dispose())
            if app.p.db2:
                loop.run_until_complete(app.p.db2.dispose())
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
