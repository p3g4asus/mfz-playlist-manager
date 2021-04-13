import json
import logging
from functools import partial
from textwrap import dedent

from aiohttp import WSMsgType, web
from aiohttp_security import (authorized_userid, check_authorized, forget,
                              remember)
import youtube_dl

from common.const import (COOKIE_USERID, CMD_PING)
from common.playlist import Playlist, PlaylistMessage
from common.timer import Timer
from common.utils import get_json_encoder, MyEncoder
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

    conv = int(request.query['conv']) if 'conv' in request.query else 0
    fmt = request.query['fmt'] if 'fmt' in request.query else 'm3u'

    if 'name' in request.query:
        pl = await Playlist.loadbyid(request.app.p.db, useri=userid, username=username, name=request.query['name'])
        if pl:
            if fmt == 'm3u':
                txt = pl[0].toM3U(request.host, conv)
                return web.Response(
                    text=txt,
                    content_type='text/plain',
                    charset='utf-8'
                )
            elif fmt == 'json':
                js = json.dumps(pl[0], cls=get_json_encoder(f'MyEnc{conv}', host=request.host, conv=conv))
                return web.Response(
                    text=js,
                    content_type='application/json',
                    charset='utf-8'
                )
            else:
                return web.HTTPBadRequest(body='Invalid format')
        else:
            return web.HTTPNotFound(body='Playlist %s not found' % request.query['name'])
    else:
        return web.HTTPBadRequest(body='Playlist name not found')


def youtube_dl_get_dict(current_url, out_dict):
    ydl_opts = {
        'ignoreerrors': True,
        'quiet': True,
        'extract_flat': True
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        playlist_dict = ydl.extract_info(current_url, download=False)
        if playlist_dict:
            out_dict.update(playlist_dict)
        else:
            out_dict.update(dict(_err=404))
        return
    out_dict.update(dict(_err=401))


async def youtube_dl_do(request):
    playlist_dict = dict()
    current_url = ''
    if 'link' in request.query:
        current_url = request.query['link']
        await request.app.p.executor(youtube_dl_get_dict, current_url, playlist_dict)
        if '_err' not in playlist_dict:
            return web.json_response(playlist_dict)
    _LOGGER.debug("url = %s answ is %s" % (current_url, str(playlist_dict)))
    return web.HTTPBadRequest(body='Link not found in URL')


async def youtube_redir_do(request):
    playlist_dict = dict()
    current_url = ''
    if 'link' in request.query:
        current_url = request.query['link']
        await request.app.p.executor(youtube_dl_get_dict, current_url, playlist_dict)
        if '_err' not in playlist_dict:
            outurl = playlist_dict.get('url')
            out_includes_audio = True
            audiourl = None
            curr_v_vcodec = 'N/A'
            curr_v_acodec = 'N/A'
            curr_a_acodec = 'N/A'
            if not outurl:
                reqfrm = playlist_dict.get('requested_formats', tuple())
                for frm in reqfrm:
                    acodec = frm.get('acodec')
                    if acodec.lower() == 'none':
                        acodec = None
                    vcodec = frm.get('vcodec')
                    if vcodec.lower() == 'none':
                        vcodec = None
                    if vcodec:
                        outurl = frm['manifest_url'] if 'manifest_url' in frm and frm['manifest_url'] else frm['url']
                        out_includes_audio = acodec is not None
                        curr_v_vcodec = vcodec
                        curr_v_acodec = acodec

                    if acodec:
                        audiourl = frm['manifest_url'] if 'manifest_url' in frm and frm['manifest_url'] else frm['url']
                        curr_a_acodec = acodec
                if not reqfrm or (outurl and not curr_v_acodec):
                    reqfrm = playlist_dict.get('formats', [])
                    for i, frm in enumerate(reqfrm):
                        acodec = frm.get('acodec')
                        if acodec.lower() == 'none':
                            acodec = None
                        vcodec = frm.get('vcodec')
                        if vcodec.lower() == 'none':
                            vcodec = None
                        if (vcodec and acodec) or (not outurl and i == len(reqfrm) - 1):
                            outurl = frm['manifest_url'] if 'manifest_url' in frm and frm['manifest_url'] else frm['url']
                            if vcodec:
                                curr_v_vcodec = vcodec
                                curr_v_acodec = acodec
                            if acodec:
                                curr_a_acodec = acodec

            if outurl or audiourl:
                _LOGGER.debug(f"codec {curr_v_vcodec}/{curr_v_acodec}/{curr_a_acodec}")
                return web.HTTPFound(outurl if outurl else audiourl)
    _LOGGER.debug("url = %s answ is %s" % (current_url, str(playlist_dict)))
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


async def send_ping(ws, control_dict):
    if not control_dict['end']:
        waiting = control_dict['msg'].cmd
        _LOGGER.debug(f"Sending ping for {waiting}")
        await ws.send_str(json.dumps(PlaylistMessage(CMD_PING, dict(waiting=waiting)), cls=MyEncoder))
        Timer(30, partial(send_ping, ws, control_dict))


async def pls_h(request):
    identity = await authorized_userid(request)
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            pl = PlaylistMessage(None, msg.json())
            _LOGGER.info("Message " + str(pl))
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
                        control_dict = dict(end=False, msg=pl)
                        Timer(30, partial(send_ping, ws, control_dict))
                        out = await p.process(ws, pl, userid, request.app.p.executor)
                        control_dict["end"] = True
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
