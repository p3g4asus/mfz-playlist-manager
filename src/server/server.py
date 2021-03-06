import argparse
import asyncio
import base64
import glob
import json
import logging
import os
import traceback
from functools import partial
from os.path import basename, dirname, isfile, join, splitext

from aiohttp import web
from aiohttp_security import SessionIdentityPolicy
from aiohttp_security import setup as setup_security
from aiohttp_session import setup as setup_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet

import aiosqlite
from common.const import PORT_OSC_CONST, COOKIE_LOGIN
from common.timer import Timer
from common.utils import asyncio_graceful_shutdown
from server.sqliteauth import SqliteAuthorizationPolicy
from server.webhandlers import index, logout, login, modify_pw, pls_h, register, playlist_m3u

__prog__ = "pls-server"

_LOGGER = logging.getLogger(__name__)

# https://github.com/AndreMiras/p4a-service-sticky/blob/develop/main.py
# https://github.com/kivy/kivy/wiki/Background-Service-using-P4A-android.service


def stop_service(address, fixedlist, *args, **kwargs):
    app = fixedlist[0]
    _LOGGER.debug("Received stop command")
    app.p.loop.stop()


def ping_app(app):
    app.p.osc_client.send_message('/server_ping', app.p.osc_port)
    app.p.osc_ping_timer = Timer(2, partial(ping_app, app))


def insert_notification():
    from jnius import autoclass
    fim = join(dirname(__file__), 'images', 'playlist-music.png')
    Context = autoclass('android.content.Context')
    Color = autoclass("android.graphics.Color")
    Intent = autoclass('android.content.Intent')
    PendingIntent = autoclass('android.app.PendingIntent')
    AndroidString = autoclass('java.lang.String')
    NotificationBuilder = autoclass('android.app.Notification$Builder')
    Notification = autoclass('android.app.Notification')
    NotificationChannel = autoclass('android.app.NotificationChannel')
    NotificationManager = autoclass('android.app.NotificationManager')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    service = autoclass('org.kivy.android.PythonService').mService

    NOTIFICATION_CHANNEL_ID = AndroidString(service.getPackageName().encode('utf-8'))
    channelName = AndroidString('HTTPServerService'.encode('utf-8'))
    chan = NotificationChannel(NOTIFICATION_CHANNEL_ID, channelName, NotificationManager.IMPORTANCE_DEFAULT)
    chan.setLightColor(Color.BLUE)
    chan.setLockscreenVisibility(Notification.VISIBILITY_PRIVATE)
    manager = service.getSystemService(Context.NOTIFICATION_SERVICE)
    manager.createNotificationChannel(chan)

    #
    # service_name = 'S1'
    # package_name = 'com.something'
    # Previous version of Kivy had a reference to the service like below.
    # service = autoclass('{}.Service{}'.format(package_name, service_name)).mService
    # notification_service = service.getSystemService(
    #    Context.NOTIFICATION_SERVICE)
    app_context = service.getApplication().getApplicationContext()
    notification_builder = NotificationBuilder(app_context, NOTIFICATION_CHANNEL_ID)
    title = AndroidString("PlsManager".encode('utf-8'))
    message = AndroidString("HttpServerService".encode('utf-8'))
    # app_class = service.getApplication().getClass()
    notification_intent = Intent(app_context, PythonActivity)
    notification_intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP |
                                 Intent.FLAG_ACTIVITY_SINGLE_TOP |
                                 Intent.FLAG_ACTIVITY_NEW_TASK)
    notification_intent.setAction(Intent.ACTION_MAIN)
    notification_intent.addCategory(Intent.CATEGORY_LAUNCHER)
    intent = PendingIntent.getActivity(service, 0, notification_intent, 0)
    notification_builder.setContentTitle(title)
    notification_builder.setContentText(message)
    notification_builder.setContentIntent(intent)
    BitmapFactory = autoclass("android.graphics.BitmapFactory")
    Icon = autoclass("android.graphics.drawable.Icon")
    BitmapFactoryOptions = autoclass("android.graphics.BitmapFactory$Options")
    # Drawable = jnius.autoclass("{}.R$drawable".format(service.getPackageName()))
    # icon = getattr(Drawable, 'icon')
    options = BitmapFactoryOptions()
    # options.inMutable = True
    # declaredField = options.getClass().getDeclaredField("inPreferredConfig")
    # declaredField.set(cast('java.lang.Object',options), cast('java.lang.Object', BitmapConfig.ARGB_8888))
    # options.inPreferredConfig = BitmapConfig.ARGB_8888;
    bm = BitmapFactory.decodeFile(fim, options)
    notification_builder.setSmallIcon(Icon.createWithBitmap(bm))
    notification_builder.setAutoCancel(True)
    new_notification = notification_builder.getNotification()
    # Below sends the notification to the notification bar; nice but not a foreground service.
    # notification_service.notify(0, new_noti)
    service.startForeground(1, new_notification)


CREATE_DB_IF_NOT_EXIST = [
    '''
    CREATE TABLE IF NOT EXISTS user(
        rowid INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
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
    CREATE TABLE IF NOT EXISTS playlist_item_seen(
        uid TEXT NOT NULL,
        playlist INTEGER NOT NULL,
        seen DATETIME,
        PRIMARY KEY (uid, playlist),
        FOREIGN KEY (playlist)
            REFERENCES playlist (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE
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


async def init_db(app):
    app.p.db = await aiosqlite.connect(app.p.args['dbfile'])
    if not isinstance(app.p.db, aiosqlite.Connection):
        app.p.db = None
    else:
        app.p.db.row_factory = aiosqlite.Row
        for q in CREATE_DB_IF_NOT_EXIST:
            await app.p.db.execute(q)
        await app.p.db.commit()
        import importlib
        app.p.processors = dict()
        app.p.locked = dict()
        modules = glob.glob(join(dirname(__file__), "pls", "*.py*"))
        pls = [splitext(basename(f))[0] for f in modules if isfile(f)]
        for x in pls:
            if x not in app.p.processors:
                try:
                    m = importlib.import_module("server.pls."+x)
                    cla = getattr(m, "MessageProcessor")
                    if cla:
                        app.p.processors[x] = cla(app.p.db)
                        if x != "common":
                            await app.p.db.execute("INSERT OR IGNORE INTO type(name) VALUES (?)", (x,))
                except Exception:
                    _LOGGER.warning(traceback.format_exc())
        await app.p.db.commit()


def init_auth(app):
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)

    storage = EncryptedCookieStorage(secret_key, cookie_name=COOKIE_LOGIN)
    setup_session(app, storage)

    policy = SessionIdentityPolicy()
    setup_security(app, policy, SqliteAuthorizationPolicy(app.p.db))


async def start_app(app):
    _LOGGER.info("Setting up")
    init_auth(app)
    runner = web.AppRunner(app)
    app.p.myrunners.append(runner)
    app.router.add_route('GET', '/', index)
    app.router.add_route('POST', '/login', login)
    app.router.add_route('POST', '/modifypw', modify_pw)
    app.router.add_route('POST', '/register', register)
    app.router.add_route('GET', '/logout', logout)
    app.router.add_route('GET', '/m3u', playlist_m3u)
    app.router.add_route('GET', '/ws', pls_h)
    await runner.setup()
    _LOGGER.info("Creating site (%s:%d)" % (app.p.args["host"], app.p.args["port"]))
    site = web.TCPSite(runner, app.p.args["host"], app.p.args["port"])
    await site.start()
    _LOGGER.info("Start finished")


class Object:
    pass


async def osc_init(app):
    from pythonosc.osc_server import AsyncIOOSCUDPServer
    try:
        _LOGGER.debug("Binding osc port %d" % app.p.osc_port)
        app.p.osc_server = AsyncIOOSCUDPServer(
            ('127.0.0.1', app.p.osc_port),
            app.p.osc_dispatcher, asyncio.get_event_loop())
        app.p.osc_transport, app.p.osc_protocol = await app.p.osc_server.create_serve_endpoint()  # Create datagram endpoint and start serving
        if app.p.osc_init_timer:
            app.p.osc_init_timer = None
        app.p.osc_ping_timer = Timer(2, partial(ping_app, app))
        _LOGGER.debug("OSC OK")
    except (Exception, OSError):
        app.p.osc_init_timer = Timer(1, partial(osc_init, app))


def main():
    app = web.Application()
    app.p = Object()
    app.p.myrunners = []
    p4a = os.environ.get('PYTHON_SERVICE_ARGUMENT', '')
    _LOGGER.info("Starting server p4a = %s" % p4a)
    if len(p4a):
        from pythonosc.dispatcher import Dispatcher
        from pythonosc.udp_client import SimpleUDPClient
        args = json.loads(p4a)
        app.p.osc_port = args["msgfrom"]
        app.p.osc_server = None
        app.p.osc_transport = None
        app.p.osc_protocol = None
        app.p.osc_dispatcher = Dispatcher()
        app.p.osc_client = SimpleUDPClient('127.0.0.1', PORT_OSC_CONST)
        app.p.osc_dispatcher.map("/stop_service", stop_service, app)
        app.p.osc_ping_timer = None
        app.p.osc_init_timer = Timer(0, partial(osc_init, app))
        insert_notification()
        import certifi
        # Here's all the magic !
        os.environ['SSL_CERT_FILE'] = certifi.where()
    else:
        parser = argparse.ArgumentParser(prog=__prog__)
        parser.add_argument('--port', type=int, help='port number', required=False, default=8080)
        parser.add_argument('--host', required=False, default="0.0.0.0")
        parser.add_argument('--dbfile', required=False, help='DB file path', default=join(dirname(__file__), '..', 'maindb.db'))
        parser.add_argument("-v", "--verbose", help="increase output verbosity",
                            action="store_true")
        args = vars(parser.parse_args())
    if args["verbose"]:
        logging.basicConfig(level=logging.DEBUG)

    app.p.args = args
    loop = asyncio.get_event_loop()
    app.p.loop = loop
    try:
        loop.run_until_complete(init_db(app))
        loop.run_until_complete(start_app(app))
        loop.run_forever()
    finally:
        try:
            # loop.run_forever()
            _LOGGER.debug("I am in finally branch")
            loop.run_until_complete(asyncio_graceful_shutdown(loop, _LOGGER, False))
            if len(p4a):
                if app.p.osc_init_timer:
                    app.p.osc_init_timer.cancel()
                    app.p.osc_init_timer = None
                if app.p.osc_ping_timer:
                    app.p.osc_ping_timer.cancel()
                    app.p.osc_ping_timer = None
                if app.p.osc_transport:
                    app.p.osc_transport.close()
                    app.p.osc_transport = None
                from jnius import autoclass
                service = autoclass('org.kivy.android.PythonService').mService
                service.stopForeground(True)
                service.stopSelf()
            for r in app.p.myrunners:
                loop.run_until_complete(r.cleanup())
            if app.p.db:
                loop.run_until_complete(app.p.db.close())
            _LOGGER.debug("Server: Closing loop")
            loop.close()
        except Exception:
            _LOGGER.error("Server: " + traceback.format_exc())


_LOGGER.info("Server module name is %s" % __name__)
if __name__ == '__main__':
    main()
