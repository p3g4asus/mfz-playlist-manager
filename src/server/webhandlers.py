import json
import logging
from textwrap import dedent

from aiohttp import WSMsgType, web
from aiohttp_security import (authorized_userid, check_authorized, forget,
                              remember)
import youtube_dl

from common.const import COOKIE_USERID
from common.playlist import Playlist, PlaylistMessage
from common.utils import MyEncoder
from server.sqliteauth import check_credentials, identity2id, identity2username

_LOGGER = logging.getLogger(__name__)


index_template = dedent("""
    <!doctype html>
        <head></head>
        <body>
            <p>{message}</p>
            <form action="/login" method="post">
                Login:
                <input type="text" name="username">
                Password:
                <input type="password" name="password">
                <input type="submit" value="Login">
            </form>
            <a href="/logout">Logout</a>
        </body>
""")


async def index(request):
    identity = await authorized_userid(request)
    _LOGGER.debug("Identity is %s" % str(identity))
    if identity:
        template = index_template.format(
            message='Hello, {username}!'.format(username=identity2username(identity)))
    else:
        template = index_template.format(message='You need to login')
    resp = web.Response(
        text=template,
        content_type='text/html',
    )
    # if identity:
    #     resp.set_cookie(COOKIE_USERID, str(identity2id(identity)))
    return resp


async def modify_pw(request):
    identity = await authorized_userid(request)
    if identity:
        form = await request.post()
        username = identity2username(identity)
        passedusername = form.get('username')
        if username != passedusername:
            return web.HTTPUnauthorized(body='Invalid username provided')
        password = form.get('password')
        if password and len(password) >= 5:
            await request.app.p.db.execute("UPDATE user set password=? WHERE username=?", (password, username))
            await request.app.p.db.commit()
            return web.HTTPFound('/')
    return web.HTTPUnauthorized(body='Invalid username / password combination')


async def playlist_m3u(request):
    _LOGGER.debug("host is %s" % str(request.host))
    identity = await authorized_userid(request)
    if identity:
        userid = identity2id(identity)
        username = None
    elif 'useri' in request.query:
        userid = request.query['useri']
        username = None
    elif 'username' in request.query:
        userid = None
        username = request.query['username']
    else:
        return web.HTTPUnauthorized(body='Invalid username / password combination')

    if 'name' in request.query:
        pl = await Playlist.loadbyid(request.app.p.db, useri=userid, username=username, name=request.query['name'])
        if pl:
            txt = pl[0].toM3U()
            return web.Response(
                text=txt.replace('%myhost%', request.host),
                content_type='text/plain',
            )
        else:
            return web.HTTPNotFound(body='Playlist %s not found' % request.query['name'])
    else:
        return web.HTTPBadRequest(body='Playlist name not found')


async def youtube_dl_do(request):
    if 'link' in request.query:
        ydl_opts = {
            'ignoreerrors': True,
            'quiet': True,
            'extract_flat': True
        }
        current_url = request.query['link']
        _LOGGER.debug("current_url is %s" % str(current_url))
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            playlist_dict = ydl.extract_info(current_url, download=False)
            _LOGGER.debug("answ is %s" % str(playlist_dict))
            return web.json_response(playlist_dict)
    else:
        return web.HTTPBadRequest(body='Link not found in URL')


async def login(request):
    response = web.HTTPFound('/')
    username = await authorized_userid(request)
    if username:
        return response
    form = await request.post()
    username = form.get('username')
    password = form.get('password')

    verified = await check_credentials(
        request.app.p.db, username, password)
    _LOGGER.debug("Ver = " + str(verified))
    if verified:
        await remember(request, response, verified)
        userid = identity2id(verified)
        request.app.p.locked[userid] = False
        response.set_cookie(COOKIE_USERID, str(userid))
        return response

    return web.HTTPUnauthorized(body='Invalid username / password combination')


async def logout(request):
    await check_authorized(request)
    response = web.Response(
        text='You have been logged out',
        content_type='text/html',
    )
    await forget(request, response)
    return response


async def pls_h(request):
    identity = await authorized_userid(request)
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            pl = PlaylistMessage(None, msg.json())
            _LOGGER.info("Message "+str(pl))
            if not identity:
                _LOGGER.info("Unauthorized")
                await ws.send_str(json.dumps(pl.err(100, "Not authorized"), cls=MyEncoder))
                break
            userid = identity2id(identity)
            locked = request.app.p.locked
            for k, p in request.app.p.processors.items():
                _LOGGER.debug(f'Checking {k}')
                if p.interested(pl):
                    multicmd = pl.f('multicmd')
                    _LOGGER.debug(f'Lck = {locked[userid] if userid in locked else False} mcmd={multicmd}')
                    if userid in locked and locked[userid] and locked[userid] != multicmd:
                        await ws.send_str(json.dumps(pl.ok(wait=2), cls=MyEncoder))
                        break
                    else:
                        out = await p.process(ws, pl, userid)
                        if out:
                            if multicmd and (userid not in locked or not locked[userid] or locked[userid] == multicmd):
                                locked[userid] = out.f('multicmd')
                            break
                        else:
                            return ws
        elif msg.type == WSMsgType.ERROR:
            _LOGGER.error('ws connection closed with exception %s' %
                          ws.exception())
            break
    return ws


async def register(request):
    identity = await authorized_userid(request)
    if identity:
        return web.HTTPFound('/')
    else:
        form = await request.post()
        username = form.get('username')
        password = form.get('password')
        _LOGGER.debug("Usermame=%s Password=%s" % (username, password))
        if username and len(username) >= 5 and password and len(password) >= 5:
            db = request.app.p.db
            async with db.execute(
                '''
                SELECT count(*) FROM user
                WHERE username = ?
                ''', (username,)
            ) as cursor:
                data = (await cursor.fetchone())[0]
                if data:
                    return web.HTTPUnauthorized(body='Username already taken')
            await db.execute('INSERT INTO user(username,password) VALUES (?,?)', (username, password))
            await db.commit()
            return web.HTTPFound('/')
        else:
            return web.HTTPUnauthorized(body='Invalid username / password combination')
