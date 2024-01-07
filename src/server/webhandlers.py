import hashlib
import json
import logging
import mimetypes
import traceback
from email.message import EmailMessage
from functools import partial
from os.path import exists, isfile, splitext
from textwrap import dedent
from time import time
from urllib.parse import urlencode
from uuid import uuid4

import yt_dlp as youtube_dl
from aiohttp import ClientSession, WSMsgType, streamer, web
from aiohttp.web_response import Response
from aiohttp_security import (authorized_userid, check_authorized, forget,
                              remember)
from google.auth.transport import requests
from google.oauth2 import id_token
from slugify import slugify

from common.const import (CMD_PING, CMD_REMOTEPLAY, CMD_REMOTEPLAY_JS,
                          CMD_REMOTEPLAY_JS_TELEGRAM, CMD_REMOTEPLAY_PUSH,
                          CONV_LINK_ASYNCH_SHIFT, CONV_LINK_ASYNCH_TWITCH,
                          CONV_LINK_MASK, INVALID_SID, MSG_INVALID_PARAM,
                          MSG_UNAUTHORIZED)
from common.playlist import LOAD_ITEMS_NO, Playlist, PlaylistItem, PlaylistMessage
from common.timer import Timer
from common.utils import MyEncoder, get_json_encoder
from server.dict_auth_policy import check_credentials, identity2username
from server.twitch_vod_id import vod_get_id

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
    auid, hextoken, _ = await authorized_userid(request)
    if isinstance(auid, int):
        identity = auid
    else:
        identity = None
    _LOGGER.debug("Identity is %s" % str(identity))
    if identity:
        template = index_template.format(
            message='Hello, {username}!'.format(username=await identity2username(request.app.p.db, identity)))
    else:
        template = index_template.format(message='You need to login')
    resp = web.Response(
        text=template,
        content_type='text/html',
    )
    if identity and not hextoken:
        await remember(request, resp, INVALID_SID)
    # if identity:
    #     resp.set_cookie(COOKIE_USERID, str(identity2id(identity)))
    return resp


async def modify_pw(request):
    auid, hextoken, _ = await authorized_userid(request)
    if isinstance(auid, int):
        identity = auid
    else:
        identity = None
    if identity:
        form = await request.post()
        username = await identity2username(request.app.p.db, identity)
        passedusername = form.get('username')
        if username != passedusername:
            return web.HTTPUnauthorized(body='Invalid username provided')
        password = form.get('password')
        if password and len(password) >= 5:
            await request.app.p.db.execute("UPDATE user set password=? WHERE username=?", (password, username))
            await request.app.p.db.commit()
            resp = web.HTTPFound('/')
            if identity and not hextoken:
                await remember(request, resp, INVALID_SID)
            return resp
    return web.HTTPUnauthorized(body='Invalid username / password combination')


async def playlist_m3u_2(request):
    try:
        async with request.app.p.db.execute(
            '''
            SELECT rowid FROM user
            WHERE token = ?
            ''', (request.match_info['token'],)
        ) as cursor:
            uid = await cursor.fetchone()
            if uid and isinstance(uid[0], int):
                return await playlist_m3u(request, userid=uid[0])
    except Exception:
        uid = None
    if not uid:
        return web.HTTPUnauthorized(body='Invalid User Token')


async def playlist_m3u(request, userid=None):
    _LOGGER.debug("host is %s" % str(request.host))
    identity = None
    if userid is None:
        auid, hextoken, _ = await authorized_userid(request)
        if isinstance(auid, int):
            identity = userid = auid
        else:
            return web.HTTPUnauthorized(body='Invalid user specification')

    conv = int(request.query['conv']) if 'conv' in request.query else 0
    fmt = request.query['fmt'] if 'fmt' in request.query else 'm3u'

    if 'name' in request.query:
        host = request.query['host'] if 'host' in request.query else f"{request.scheme}://{request.host}"
        pl = await Playlist.loadbyid(request.app.p.db, useri=userid, name=request.query['name'])
        asconv = (conv >> CONV_LINK_ASYNCH_SHIFT) & CONV_LINK_MASK
        if asconv == CONV_LINK_ASYNCH_TWITCH:
            for it in pl[0].items:
                it.link = await twitch_link_finder(it.link, request.app)
        if pl:
            if fmt == 'm3u':
                txt = pl[0].toM3U(host, conv)
                resp = web.Response(
                    text=txt,
                    content_type='text/plain',
                    charset='utf-8'
                )
            elif fmt == 'ely':
                it = int(request.query['it']) if 'it' in request.query else -2
                if it >= len(pl[0].items):
                    it = len(pl[0].items) - 1
                if it >= 0 and it < len(pl[0].items):
                    lnk = f'http://embedly.com/widgets/media.html?{urlencode(dict(url=pl[0].items[it].get_conv_link(host, conv)))}'
                    ln = f'<div class="embedly-card" href="{lnk}"></div>'
                else:
                    ln = '\n'
                    for it in pl[0].items:
                        lnk = f'http://embedly.com/widgets/media.html?{urlencode(dict(url=it.get_conv_link(host, conv)))}'
                        ln += f'<div class="embedly-card" href="{lnk}"></div>\n'
                webp = f"""
                    <!doctype html>
                        <head></head>
                        <body>
                            {ln}
                        </body>
                """
                resp = web.Response(
                    text=webp,
                    content_type='text/html',
                    charset='utf-8'
                )
            elif fmt == 'json':
                js = json.dumps(pl[0], cls=get_json_encoder(f'MyEnc{conv}', host=host, conv=conv))
                resp = web.Response(
                    text=js,
                    content_type='application/json',
                    charset='utf-8'
                )
            else:
                return web.HTTPBadRequest(body='Invalid format')
            if identity and not hextoken:
                await remember(request, resp, INVALID_SID)
            return resp
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


async def redirect_till_last(request):
    if 'link' in request.query:
        headers = {"range": "bytes=0-10", "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/81.0"}
        async with ClientSession() as session:
            async with session.get(request.query['link'], headers=headers) as resp:
                if resp.status >= 200 and resp.status < 300:
                    return web.HTTPFound(resp.url)
                else:
                    return web.StreamResponse(status=resp.status, reason=resp.reason)
    return web.HTTPBadRequest(body='Link not found in URL')


async def img_link(request):
    if 'link' in request.query:
        try:
            url = request.query['link']
            async with ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status >= 200 and resp.status < 300:
                        msg = EmailMessage()
                        msg['content-type'] = resp.headers.get('content-type')
                        mimetype, options = msg.get_content_type(), msg['content-type'].params
                        return Response(body=await resp.read(), content_type=mimetype, charset=None if 'charset' not in options else options['charset'])
                    else:
                        return web.StreamResponse(status=resp.status, reason=resp.reason)
        except Exception:
            _LOGGER.error(traceback.format_exc())
    return web.HTTPBadRequest(body='Link not found in URL')


async def twitch_link_finder(link, app):
    if 0:
        from server.twitch_vod_link import get_vod_feeds
        from server.twitch_vod_link0 import get_vod_link
        feeds = None
        try:
            vodid = vod_get_id(link)
            feeds = await get_vod_feeds(vodid)
            _LOGGER.debug(f'link={link} vodid={vodid}: {feeds}')
            if feeds:
                link = feeds.getFeed(0)
        except Exception:
            _LOGGER.warning(f'Twitch conv error for lnk {link}: {traceback.format_exc()}')
        if not feeds:
            try:
                feeds = await get_vod_link(link, app.p.executor)
                if feeds:
                    link = feeds[0]
            except Exception:
                _LOGGER.warning(f'Twitch conv0 error for lnk {link}: {traceback.format_exc()}')
    else:
        from server.twitch_vod_link2 import get_vod_link
        vodid = vod_get_id(link)
        link0 = await get_vod_link(vodid)
        if link0:
            link = link0
    return link


async def twitch_redir_do(request):
    if 'link' in request.query:
        link = request.query['link']
        link = await twitch_link_finder(link, request.app)
        return web.HTTPFound(link)
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


async def login_g(request):
    form = await request.post()
    token = form.get('idtoken')
    # (Receive token by HTTPS POST)
    # ...
    try:
        auid, _, _ = await authorized_userid(request)
        response = web.HTTPNoContent()
        if isinstance(auid, int):
            await remember(request, response, INVALID_SID, max_age=86400 * 365 if form.get('remember') else None)
            return response
        userid = None
        # Specify the CLIENT_ID of the app that accesses the backend:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), request.app.p.args['client_id'])

        # Or, if multiple clients access the backend server:
        # idinfo = id_token.verify_oauth2_token(token, requests.Request())
        # if idinfo['aud'] not in [CLIENT_ID_1, CLIENT_ID_2, CLIENT_ID_3]:
        #     raise ValueError('Could not verify audience.')

        # If auth request is from a G Suite domain:
        # if idinfo['hd'] != GSUITE_DOMAIN_NAME:
        #     raise ValueError('Wrong hosted domain.')

        # ID token is valid. Get the user's Google Account ID from the decoded token.
        password = idinfo['sub']
        _LOGGER.debug(f"token is {idinfo}")
        db = request.app.p.db
        async with db.execute(
            '''
            SELECT U.rowid as rowid,
                U.username as username,
                U.password as password from user as U WHERE password=?
            ''', (password,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                userid = row['rowid']
            else:
                async with db.execute('INSERT INTO user(username,password) VALUES (?,?)', (idinfo['email'], password)) as cursor2:
                    userid = cursor2.lastrowid
                    await db.commit()
        if userid:
            if isinstance(auid, str):
                ids = json.dumps(dict(sid=auid, uid=userid))
                _LOGGER.debug(f'Remembering... {ids}')
                await remember(request, response, ids, max_age=86400 * 365 if form.get('remember') else None)
            else:
                return web.HTTPUnprocessableEntity(body=f'Identity server error ({str(auid)})')
            return response
    except Exception:
        _LOGGER.warning(f'Ecxception validationg token {traceback.format_exc()}')
        pass
    return web.HTTPUnauthorized(body='Invalid Google Token')


async def login(request):
    response = web.HTTPNoContent()
    auid, _, _ = await authorized_userid(request)
    form = await request.post()
    if isinstance(auid, int):
        await remember(request, response, INVALID_SID, max_age=86400 * 365 if form.get('remember') else None)
        return response
    username = form.get('username')
    password = form.get('password')

    verified = await check_credentials(request.app.p.db, username, password)
    _LOGGER.debug("Ver = " + str(verified))
    if verified:
        if isinstance(auid, str):
            await remember(request, response, json.dumps(dict(sid=auid, uid=verified)), max_age=86400 * 365 if form.get('remember') else None)
            return response
        else:
            return web.HTTPUnprocessableEntity(body=f'Identity server error ({str(auid)})')
    else:
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
        try:
            waiting = control_dict['msg'].cmd
            _LOGGER.debug(f"Sending ping for {waiting}")
            await ws.send_str(json.dumps(PlaylistMessage(CMD_PING, dict(waiting=waiting)), cls=MyEncoder))
            if not ws.closed and not ws.exception():
                Timer(30, partial(send_ping, ws, control_dict))
            else:
                control_dict['end'] = True
                _LOGGER.debug("Websocket is closed: ping not done")
        except Exception:
            _LOGGER.debug(f"Exception detected {traceback.format_exc()}: Stop pinging")
            control_dict['end'] = True


async def process_remoteplay_cmd_queue(ws, queue):
    if not queue:
        return []
    else:
        i = 0
        while True:
            cmd = queue[i]
            try:
                await ws.send_str(cmd)
                if i == len(queue) - 1:
                    return []
                else:
                    i += 1
            except Exception:
                _LOGGER.warning(f'Remote play command failed {traceback.format_exc()}')
                return queue[i:]


@streamer
async def file_sender(writer, file_path=None):
    """
    This function will read large file chunk by chunk and send it through HTTP
    without reading them into memory
    """
    with open(file_path, 'rb') as f:
        chunk = f.read(2 ** 16)
        while chunk:
            await writer.write(chunk)
            chunk = f.read(2 ** 16)


async def download(request):
    try:
        stream = int(request.query['stream'])
    except Exception:
        stream = False
    if not stream:
        auid, _, _ = await authorized_userid(request)
        if not isinstance(auid, int):
            userid = None
        else:
            userid = auid
    rowid = int(request.match_info['rowid'])
    if (stream or userid) and rowid:
        it = await PlaylistItem.loadbyid(request.app.p.db, rowid=rowid)
        if it:
            pls = await Playlist.loadbyid(request.app.p.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
            if pls:
                if not stream and pls[0].useri != userid:
                    return web.HTTPUnauthorized(body='Invalid user id')
                elif not it.dl or not exists(it.dl) or not isfile(it.dl):
                    return web.HTTPBadRequest(body=f'Invalid dl: {it.dl} for {it.title}')
                else:
                    if stream:
                        headers = dict()
                        mime, _ = mimetypes.guess_type(it.dl)
                        if not mime:
                            return web.HTTPNotAcceptable(reason='Invalid MIME type')
                    else:
                        headers = {
                            "Content-disposition": f"attachment; filename={slugify(it.title + splitext(it.dl)[1], separator=' ', lowercase=False)}"
                        }
                        mime = 'application/octet-stream'

                    return web.Response(
                        body=file_sender(file_path=it.dl),
                        headers=headers,
                        content_type=mime,
                    )
        return web.HTTPNotFound(body='Invalid playlist or playlist item')
    else:
        return web.HTTPNotAcceptable(body="Invalid userid or rowid")


async def telegram_command(request):
    hextoken = request.match_info['hex']
    dws = request.app.p.ws
    if hextoken in dws and isinstance(dws[hextoken], str) and dws[hextoken] in dws and isinstance(dws[dws[hextoken]], dict):
        q = request.query
        cmd = None
        dct = dws[dws[hextoken]]
        if 'act' in q and q['act'] == 'start' and 'username' in q:
            cmd = dict(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_TELEGRAM, act='start', username=q['username'])
        elif 'act' in q and q['act'] == 'finish' and 'username' in q and 'token' in q and 'token_info' in dct and dct['token_info']['exp'] > time() * 1000 and q['username'] == dct['token_info']['username']:
            tok = dct['token_info']['token']
            del dct['token_info']
            if q['token'] == tok:
                db = request.app.p.db
                cmd = dict(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_TELEGRAM, act='finish')
                await db.execute("UPDATE user set tg=null WHERE tg=?", (q['username'], ))
                await db.execute("UPDATE user set tg=? WHERE rowid=?", (q['username'], dct['uid']))
                await db.commit()
            else:
                return web.HTTPUnauthorized(body='Invalid token: please retry')
        else:
            return web.HTTPNotAcceptable(body='Invalid params')
        if cmd:
            cmd = json.dumps(cmd)
            if dct['cmdqueue']:
                dct['cmdqueue'].append(cmd)
            else:
                dct['cmdqueue'] = await process_remoteplay_cmd_queue(dct['ws'], [cmd])
            return web.HTTPNoContent()
    else:
        return web.HTTPNotFound(body='Invalid hex token')


async def remote_command(request):
    hextoken = request.match_info['hex']
    if hextoken in request.app.p.ws:
        typem = 1 if 'red' in request.query else 2 if 'get' in request.query or 'get[]' in request.query else 0
        redirect_pars = f'?hex={hextoken}'
        outdict = {'hex': hextoken}
        try:
            for k, v in request.query.items():
                if typem == 1:
                    if k == 'red':
                        redirect_pars = v + redirect_pars
                    else:
                        d = dict()
                        d[k] = v
                        redirect_pars = f'{redirect_pars}&{urlencode(d)}'
                elif typem == 2:
                    if k in ('get', 'get[]') and v in request.app.p.ws[hextoken]:
                        outdict[v] = request.app.p.ws[hextoken][v]
                elif k in outdict:
                    if isinstance(outdict[k], list):
                        outdict[k].append(v)
                    else:
                        outdict[k] = [outdict[k], v]
                else:
                    outdict[k] = v
        except Exception:
            del request.app.p.ws[hextoken]
            _LOGGER.debug(f"Exception detected {traceback.format_exc()}: Deleting ws")
            return web.HTTPUnauthorized(body='Invalid hex link')
        if typem == 1:
            raise web.HTTPFound(location=redirect_pars)
        else:
            _LOGGER.debug(f'Sending this dict: {outdict}')
            cmd = json.dumps(outdict)
            if typem == 0:
                dct = request.app.p.ws[hextoken]
                if dct['cmdqueue']:
                    dct['cmdqueue'].append(cmd)
                else:
                    dct['cmdqueue'] = await process_remoteplay_cmd_queue(dct['ws'], [cmd])
                outdict['queue'] = len(dct['cmdqueue'])
                cmd = json.dumps(outdict)
            return web.Response(
                text=cmd,
                content_type='application/json',
                charset='utf-8'
            )
    else:
        return web.HTTPUnauthorized(body='Invalid hex link')


async def pls_h(request):
    auid, _, player_hex = await authorized_userid(request)
    if not isinstance(auid, int):
        userid = None
    else:
        userid = auid
    ws = web.WebSocketResponse(autoping=True, heartbeat=None, timeout=45, autoclose=False)
    await ws.prepare(request)
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            pl = PlaylistMessage(None, msg.json())
            _LOGGER.info("Message " + str(pl))
            if not userid:
                _LOGGER.info("Unauthorized")
                await ws.send_str(json.dumps(pl.err(501, MSG_UNAUTHORIZED), cls=MyEncoder))
                break
            elif pl.c(CMD_REMOTEPLAY):
                if not player_hex:
                    _LOGGER.info("Invalid token")
                    await ws.send_str(json.dumps(pl.err(502, MSG_UNAUTHORIZED), cls=MyEncoder))
                else:
                    dws = request.app.p.ws
                    dd = dws.get(player_hex, dict())
                    if isinstance(dd, dict):
                        dd.update(dict(ws=ws, uid=userid))
                        dws[player_hex] = dd
                        if 'telegram' in dd and dd['telegram'] in dws:
                            del dws[dd['telegram']]
                        telegram = dd['telegram'] = hashlib.sha256(str(uuid4()).encode('utf-8')).hexdigest()
                        dws[telegram] = player_hex
                        host = f"{pl.host + ('/' if pl.host[len(pl.host) - 1] != '/' else '')}rcmd/{player_hex}"
                        host2 = f"{pl.host + ('/' if pl.host[len(pl.host) - 1] != '/' else '')}telegram/{telegram}"
                        await ws.send_str(json.dumps(pl.ok(url=host, telegram=host2, hex=player_hex), cls=MyEncoder))
                        dd['cmdqueue'] = (await process_remoteplay_cmd_queue(ws, dd['cmdqueue'])) if 'cmdqueue' in dd else []
                    else:
                        await ws.send_str(json.dumps(pl.err(20, MSG_INVALID_PARAM)))
            elif pl.c(CMD_REMOTEPLAY_PUSH):
                if not player_hex:
                    _LOGGER.info("Invalid token")
                    await ws.send_str(json.dumps(pl.err(502, MSG_UNAUTHORIZED), cls=MyEncoder))
                else:
                    try:
                        w = pl.f(pl.what)
                        dd = request.app.p.ws.get(player_hex, dict())
                        dd.update({'ws': ws, pl.what: w, 'uid': userid})
                        request.app.p.ws[player_hex] = dd
                        _LOGGER.info(f'New dict el for {player_hex} [{pl.what}] -> {json.dumps(w)}')
                        await ws.send_str(json.dumps(pl.ok(), cls=MyEncoder))
                    except Exception:
                        await ws.send_str(json.dumps(pl.err(509, traceback.format_exc()), cls=MyEncoder))
            for k, p in request.app.p.processors.items():
                _LOGGER.debug(f'Checking {k}')
                if p.interested(pl):
                    control_dict = dict(end=False, msg=pl)
                    Timer(30, partial(send_ping, ws, control_dict))
                    out = await p.process(ws, pl, userid, request.app.p.executor)
                    control_dict["end"] = True
                    if out:
                        break
                    else:
                        return ws
        elif msg.type == WSMsgType.ERROR:
            _LOGGER.error('ws connection closed with exception %s' %
                          ws.exception())
            break
    return ws


async def register(request):
    auid, _, _ = await authorized_userid(request)
    if isinstance(auid, int):
        response = web.HTTPFound('/')
        await remember(request, response, INVALID_SID)
        return response
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
