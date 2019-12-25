from textwrap import dedent

from aiohttp import web, WSMsgType

from aiohttp_security import (
    remember, forget, authorized_userid, check_authorized
)

from server.sqliteauth import check_credentials, identity2id, identity2username

from common.const import COOKIE_USERID
from common.playlist import PlaylistMessage, Playlist

import logging

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
    if identity:
        template = index_template.format(
            message='Hello, {username}!'.format(username=identity2username(identity)))
    else:
        template = index_template.format(message='You need to login')
    resp = web.Response(
        text=template,
        content_type='text/html',
    )
    if identity:
        resp.set_cookie(COOKIE_USERID, str(identity2id(id)))
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
            await request.app.p.db.execute("UPDATE user set password=? WHERE username=?", [(password, username)])
            await request.app.p.db.commit()
            return web.HTTPFound('/')
    return web.HTTPUnauthorized(body='Invalid username / password combination')


async def playlist_m3u(request):
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
        pl = Playlist.loadbyid(useri=userid, username=username, name=request.query['name'])
        if pl:
            txt = pl[0].toM3U()
            return web.Response(
                text=txt,
                content_type='text/plain',
            )
        else:
            return web.HTTPNotFound(body='Playlist %s not found' % request.query['name'])
    else:
        return web.HTTPBadRequest(body='Playlist name not found')


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
    if verified:
        await remember(request, response, verified)
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
    if identity:
        print('Websocket connection starting')
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        print('Websocket connection ready')

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                pl = PlaylistMessage(None, msg.json())
                _LOGGER.info("Message "+str(pl))
                for p in request.app.p.processors:
                    if p.interested(pl):
                        if await p.process(ws, pl):
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
        if username and len(username) >= 5 and password and len(password) >= 5:
            db = request.app.p.db
            cursor = await db.execute("select * from user WHERE username=?", username)
            async for row in cursor:
                return web.HTTPUnauthorized(body='Username already taken')
            await db.execute('INSERT INTO user(username,password) VALUES (?;?)', (username, password))
            await db.commit()
            return web.HTTPFound('/login')
        else:
            return web.HTTPUnauthorized(body='Invalid username / password combination')
