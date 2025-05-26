import abc
import asyncio
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import traceback
import zlib
from asyncio import Event
from base64 import b64encode
from collections import OrderedDict
from datetime import datetime
from functools import partial
from os import makedirs, remove, rename
from os.path import join, realpath, split, splitext
from shutil import move, rmtree

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

from common.const import (CMD_ADD, CMD_CLEAR, CMD_CLOSE, CMD_DEL, CMD_DOWNLOAD,
                          CMD_DUMP, CMD_FREESPACE, CMD_INDEX, CMD_IORDER, CMD_ITEMDUMP, CMD_MOVE,
                          CMD_PLAYID, CMD_PLAYITSETT, CMD_PLAYSETT, CMD_REN,
                          CMD_SEEN, CMD_SEEN_PREV, CMD_SORT, CMD_TOKEN, CMD_USER_SETTINGS, DOWNLOADED_SUFFIX,
                          MSG_BACKEND_ERROR, MSG_INVALID_PARAM, MSG_NAME_TAKEN,
                          MSG_PLAYLIST_NOT_FOUND, MSG_PLAYLISTITEM_NOT_FOUND,
                          MSG_TASK_ABORT, MSG_UNAUTHORIZED)
from common.playlist import (LOAD_ITEMS_ALL, LOAD_ITEMS_NO, LOAD_ITEMS_UNSEEN,
                             Playlist, PlaylistItem, PlaylistMessage)
from common.user import User
from common.utils import AbstractMessageProcessor, MyEncoder

_LOGGER = logging.getLogger(__name__)

DUMP_LIMIT = 50


class MessageProcessor(AbstractMessageProcessor):
    def __init__(self, db, dldir='', **kwargs):
        super().__init__(db, **kwargs)
        self.dl_dir = dldir
        self.dl_q = OrderedDict()
        self.downloader = None

    def interested(self, msg):
        return msg.c(CMD_DEL) or msg.c(CMD_REN) or msg.c(CMD_DUMP) or\
            msg.c(CMD_ADD) or msg.c(CMD_SEEN) or msg.c(CMD_SEEN_PREV) or msg.c(CMD_MOVE) or\
            msg.c(CMD_IORDER) or msg.c(CMD_SORT) or msg.c(CMD_PLAYID) or\
            msg.c(CMD_PLAYSETT) or msg.c(CMD_PLAYITSETT) or msg.c(CMD_DOWNLOAD) or msg.c(CMD_INDEX) or\
            msg.c(CMD_CLEAR) or msg.c(CMD_FREESPACE) or msg.c(CMD_TOKEN) or msg.c(CMD_USER_SETTINGS) or\
            msg.c(CMD_ITEMDUMP)

    async def processMove(self, msg, userid, executor):
        pdst = msg.playlistId()
        itx = msg.playlistItemId()
        if pdst and itx:
            pdst = await Playlist.loadbyid(self.db, rowid=pdst, loaditems=LOAD_ITEMS_NO)
            if not pdst:
                return msg.err(10, MSG_PLAYLIST_NOT_FOUND, playlist=None)
            else:
                pdst = pdst[0]
            if pdst.useri != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            it = await PlaylistItem.loadbyid(self.db, itx)
            if not it:
                return msg.err(14, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
            psrc = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
            if not psrc:
                return msg.err(16, MSG_PLAYLIST_NOT_FOUND, playlist=None)
            else:
                psrc = psrc[0]
            if psrc.useri != userid:
                return msg.err(502, MSG_UNAUTHORIZED, playlist=None)
            if not pdst.rowid:
                rv = await pdst.toDB(self.db)
                if not rv:
                    return msg.err(2, MSG_NAME_TAKEN, playlist=None)
            rv = await it.move_to(pdst.rowid, self.db)
            if rv:
                pdst = await Playlist.loadbyid(self.db, rowid=pdst.rowid)
                return msg.ok(playlist=pdst[0])
            else:
                return msg.err(4, MSG_BACKEND_ERROR, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processAdd(self, msg, userid, executor):
        x = msg.playlistObj()
        if x:
            if x.useri != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            rv = await x.toDB(self.db)
            if rv:
                return msg.ok(playlist=x)
            else:
                return msg.err(2, MSG_NAME_TAKEN, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processTokenRefresh(self, userid):
        users: list[User] = await User.loadbyid(self.db, rowid=userid)
        if users:
            return await users[0].refreshToken(self.db)
        else:
            return None

    async def processTokenGet(self, userid):
        users: list[User] = await User.loadbyid(self.db, rowid=userid)
        if users:
            return users[0].token
        else:
            return None

    async def processToken(self, msg, userid, executor):
        refresh = msg.f('refresh')
        token = None
        if refresh or not (token := await self.processTokenGet(userid)):
            token = await self.processTokenRefresh(userid)
        return msg.ok(token=token)

    async def processUserSettings(self, msg, userid, executor):
        users: list[User] = await User.loadbyid(self.db, rowid=userid)
        if users:
            u = users[0]
            u.conf['settings'] = msg.settings
            rv = await u.toDB(self.db)
            return msg.ok() if rv else msg.err(5, MSG_BACKEND_ERROR)
        else:
            return msg.err(501, MSG_UNAUTHORIZED)

    async def processDump(self, msg, userid, executor):
        u = msg.f("useri", (int,))
        if u:
            if u != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            vidx = msg.f('fast_videoidx')
            if isinstance(vidx, int) and vidx < 0:
                zlibc = -vidx
                vidx = None
            else:
                zlibc = -1
            try:
                all = int(msg.f('load_all'))
            except Exception:
                all = 0
            pl = await Playlist.loadbyid(self.db, rowid=msg.playlistId(), name=msg.playlistName(), useri=u, offset=vidx, limit=DUMP_LIMIT, loaditems=LOAD_ITEMS_UNSEEN if not all else LOAD_ITEMS_ALL if all > 0 else LOAD_ITEMS_NO)
            _LOGGER.debug("Playlists are %s" % str(pl))
            if len(pl):
                if msg.f('index', (int,)):
                    for i, p in enumerate(pl):
                        p.iorder = i + 1
                if zlibc > 0:
                    pl = str(b64encode(zlib.compress(bytes(json.dumps(pl, cls=MyEncoder), 'utf-8'), zlibc)), 'utf-8')
                return msg.ok(playlist=None, playlists=pl, fast_videoidx=vidx, fast_videostep=DUMP_LIMIT if vidx is not None else None)
        return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processRen(self, msg, userid, executor):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, rowid=x, loaditems=LOAD_ITEMS_NO)
            if pls:
                if pls[0].useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                pls[0].name = msg.f("to")
                rv = await pls[0].toDB(self.db)
                if rv:
                    return msg.ok(playlist=x, name=pls[0].name)
                else:
                    return msg.err(2, MSG_NAME_TAKEN, playlist=None)
            else:
                return msg.err(3, MSG_PLAYLIST_NOT_FOUND, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processSeen(self, msg, userid, executor):
        llx = msg.playlistItemId()
        if llx is not None:
            lx = llx if isinstance(llx, list) else [llx]
            seen = msg.f("seen")
            if isinstance(seen, list) and len(seen) != len(lx):
                return msg.err(20, MSG_INVALID_PARAM, playlistitem=None)
            elif not isinstance(seen, list):
                seen = [seen] * len(lx)
            nmod = 0
            for i, x in enumerate(lx):
                it = await PlaylistItem.loadbyid(self.db, rowid=x)
                if it:
                    pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
                    if pls:
                        if pls[0].useri != userid:
                            return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                        todb = False
                        if isinstance(it.conf, dict) and 'sec' in it.conf:
                            del it.conf['sec']
                            todb = True
                        if todb:
                            it.seen = None if not seen[i] else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            await it.toDB(self.db, commit=False)
                        elif not await it.setSeen(self.db, seen[i], commit=False):
                            return msg.err(2, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                        nmod += 1
                    else:
                        return msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlistitem=None)
                else:
                    return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
            if nmod:
                await self.db.commit()
        else:
            return msg.err(1, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        return msg.ok(playlistitem=llx)

    async def processSeenPrev(self, msg, userid, executor):
        x = msg.playlistItemId()
        if x is not None:
            it = await PlaylistItem.loadbyid(self.db, rowid=x)
            if it:
                pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
                if pls:
                    if pls[0].useri != userid:
                        return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                    if not await it.setSeen(self.db, True, commit=True, previous=True):
                        return msg.err(2, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                else:
                    return msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlistitem=None)
            else:
                return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        else:
            return msg.err(1, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_ALL)
        return msg.ok(playlistitem=x, playlist=pls[0])

    async def processPlayItSett(self, msg, userid, executor):
        x = msg.playlistItemId()
        it = await PlaylistItem.loadbyid(self.db, rowid=x)
        if it:
            pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
            if pls:
                if pls[0].useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                if msg.f('over'):
                    it.conf = msg.conf
                    if isinstance(it.conf, str):
                        it.conf = json.loads(it.conf)
                else:
                    it.conf.update(msg.conf)
                if not await it.toDB(self.db):
                    return msg.err(2, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
            else:
                return msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlistitem=None)
        else:
            return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        return msg.ok(playlistitem=x)

    async def processItemDump(self, msg, userid, executor):
        x = msg.playlistItemId()
        it = await PlaylistItem.loadbyid(self.db, rowid=x)
        if it:
            pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
            if pls:
                if pls[0].useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                else:
                    return msg.ok(playlistitem=it)
            else:
                return msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlistitem=None)
        else:
            return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)

    class Downloader(abc.ABC):
        @abc.abstractmethod
        def halt(self):
            pass

        @abc.abstractmethod
        async def dl(self, status, executor):
            pass

        def __init__(self, it, msg, db, dl_dir) -> None:
            self.it = it
            self.db = db
            self.msg = msg
            self.dl_dir = dl_dir
            self.rem = False
            self.ev = None

        def mark_del(self):
            self.rem = True

        def awake(self):
            if self.ev:
                self.ev.set()

        def is_deleted(self):
            return self.rem

        async def go_to_sleep(self):
            self.ev = Event()
            await self.ev.wait()

    class DRMDownloader(Downloader):
        def __init__(self, it, msg, db, dl_dir) -> None:
            super().__init__(it, msg, db, dl_dir)
            self.p = None

        @staticmethod
        def mul_from_u(u):
            if u:
                c = u[0].lower()
                if c == 'b':
                    return 1
                elif c == 'k':
                    return 1024
                elif c == 'm':
                    return 1024 * 1024
                elif c == 'g':
                    return 1024 * 1024 * 1024
                elif c == 't':
                    return 1024 * 1024 * 1024 * 1024
            return None

        def popen_do(self, args, status, sd):
            rv = 133
            rmtree(sd, ignore_errors=True)
            makedirs(sd, exist_ok=True)
            _LOGGER.info(f'[common dl] Starting process {args}')
            try:
                with subprocess.Popen(args, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
                    self.p = p
                    rv = 134
                    u1d = dict(Vid=None, Aud=None)
                    u2d = u1d.copy()
                    m1d = u1d.copy()
                    m2d = u1d.copy()
                    out = status['dl']['raw'] = dict(speed=0, total_bytes=0, downloaded_bytes=0)
                    for line in p.stdout:
                        if line:
                            clean = re.sub(r'\[[0-9;]+[a-zA-Z]|\t|\x1b', ' ', line).strip()
                            # downloaded_bytes speed total_bytes
                            if re.search(r'^(?:Vid|Aud)', clean):
                                if (mo := re.search(r'(?P<type>Vid|Aud)\s+(?P<res>[0-9]+x[0-9]+|[0-9]+\s+[^\s]+)\s+\|\s+(?P<br>[0-9]+\s+[^\s]+|[a-z0-9]+)\s+[^\d]+(?P<frag>\d+/\d+\s+)?(?P<perc>[0-9\.]+)%\s+(?P<b1>[0-9\.]+)(?P<u1>[^/]+)?/(?P<b2>[0-9\.]+)(?P<u2>[^\s]+)?\s+(?P<spd>[0-9\.]+)(?P<uspd>[^\s]+)\s+(?P<time>[^\s]+)', clean)):
                                    t = mo.group('type')
                                    u1 = u1d[t]
                                    u2 = u2d[t]
                                    g1 = mo.group('u1')
                                    g2 = mo.group('u2')
                                    if (not g1 and not u1) or (not g2 and not u2):
                                        continue
                                    else:
                                        if g1 and (m1 := self.mul_from_u(g1)):
                                            u1d[t] = g1
                                            m1d[t] = m1
                                        else:
                                            m1 = m1d[t]
                                            if not m1:
                                                continue
                                        if g2 and (m2 := self.mul_from_u(g2)):
                                            u2d[t] = g2
                                            m2d[t] = m2
                                        else:
                                            m2 = m2d[t]
                                            if not m2:
                                                continue
                                        db = int(float(mo.group('b1')) * m1)
                                        tb = int(float(mo.group('b2')) * m2)
                                        sp = int(float(mo.group('spd')) * self.mul_from_u(mo.group('uspd')))
                                        out['speed'] = sp
                                        out['status'] = f'Downloading {t}...'
                                        out['downloaded_bytes'] = db
                                        out['total_bytes'] = tb
                                        out['type'] = t
                            elif (mo := re.search(r'\s+:\s+((?:Decrypting|Muxing|Cleaning|Binary merging|Rename)[^$\r\n]+)', clean, re.IGNORECASE)):
                                out['status'] = mo.group(1)
                            elif re.search(r'\s+:\s+force\s+exit', clean.lower()):
                                rv = -2
                            elif re.search(r'\s+:\s+done', clean.lower()):
                                rv = 0
                            elif re.search(r'\s+ERROR\s+:', clean):
                                _LOGGER.warning(f'[dl drm log] {clean}')
                                rv = -3
                            else:
                                _LOGGER.debug(f'[dl drm log] {clean}')
                    self.p = None
            except Exception:
                _LOGGER.warning(f'[common dl] Cannot start process {traceback.format_exc()}')
                rv = 136
            return rv

        def halt(self):
            if self.p:
                self.p.send_signal(signal.CTRL_C_EVENT if os.name == 'nt' else signal.SIGINT)

        async def dl(self, status, executor):
            msg = self.msg
            format = msg.f('fmt')
            # conv = msg.f('conv')
            # host = msg.f('host')
            kw = ['N_m3u8DL-RE.exe' if os.name == 'nt' else 'N_m3u8DL-RE']
            if 'video' not in format:
                kw.extend(['-sa', 'id=0'])
            else:
                kw.append('--auto-select')
            sd = realpath(join(self.dl_dir, f't{self.it.rowid}'))
            kw.extend(['-M', 'format=mp4:muxer=ffmpeg',
                       '--no-log',
                       '--concurrent-download',
                       '--del-after-done',
                       '--log-level', 'INFO',
                       '--save-dir', sd,
                       '--tmp-dir', sd,
                       '--save-name', f'{self.it.rowid}',
                       self.it.conf['_drm_m']])
            [kw.extend(['--key', k]) for k in self.it.conf['_drm_k']]
            rv = await executor(self.popen_do, kw, status, sd)
            if not rv:
                dest = join(self.dl_dir, f'{self.it.rowid}.mp4')
                try:
                    remove(dest)
                except Exception:
                    pass
                move(join(sd, f'{self.it.rowid}.mp4'), dest)
                self.it.dl = dest
                if not await self.it.toDB(self.db):
                    msg = msg.err(2, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                else:
                    msg = msg.ok(playlistitem=self.it)
            else:
                msg = msg.err(5, MSG_BACKEND_ERROR, playlistitem=None)
            rmtree(sd, ignore_errors=True)
            return msg

    class YTDLDownloader(Downloader):
        def __init__(self, it, msg, db, dl_dir) -> None:
            super().__init__(it, msg, db, dl_dir)
            self.osc_s = None
            self.osc_t = None
            self.osc_c = None

        async def dl(self, status, executor):
            msg = self.msg
            format = msg.f('fmt')
            conv = msg.f('conv')
            token = msg.f('token')
            host = msg.f('host')
            post = [
                {
                    'key': 'FFmpegThumbnailsConvertor',
                    'format': 'jpg',
                    'when': 'before_dl',
                },
                {
                    'key': 'FFmpegExtractAudio'
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_chapters': True,
                    'add_metadata': True,
                    'add_infojson': False,
                },
                {
                    'key': 'EmbedThumbnail',
                    'already_have_thumbnail': False,
                }
            ]
            if 'video' not in format:
                kw = dict(extractaudio=True,
                          addmetadata=True,
                          embedthumbnail=True)
            else:
                kw = dict()
                post.pop(1)
            ytdl_opt = dict(
                format=format,
                noplaylist=True,
                writethumbnail=True,
                ignoreerrors=True,
                outtmpl=join(self.dl_dir, f'{self.it.rowid}_t.%(ext)s'),
                postprocessors=post,
                **kw
            )
            await executor(self.open_and_wait, await self.init_osc_client_server((self.it.get_conv_link(host, conv, token=token, additional=dict(audio='1' if 'video' not in format else '0')), ytdl_opt), status))
            if 'sta' in status['dl'] and not status['dl']['sta'] and\
               'file' in status['dl'] and status['dl']['file'] and\
               'rv' in status['dlx'] and not status['dlx']['rv']:
                try:
                    remove(self.it.dl)
                except Exception:
                    pass
                rv_err = status['dlx']
                if 'raw' in rv_err and 'requested_downloads' in rv_err['raw'] and\
                   rv_err['raw']['requested_downloads'] and\
                   'filepath' in rv_err['raw']['requested_downloads'][0] and\
                   rv_err['raw']['requested_downloads'][0]['filepath']:
                    fromfile = rv_err['raw']['requested_downloads'][0]['filepath']
                else:
                    fromfile = status['dl']['file']
                _, ext = splitext(fromfile)
                self.it.dl = join(self.dl_dir, f'{self.it.rowid}{ext}')
                rename(fromfile, self.it.dl)
                if not await self.it.toDB(self.db):
                    msg = msg.err(2, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                else:
                    msg = msg.ok(playlistitem=self.it)
            else:
                if 'dl' in status and 'files' in status['dl']:
                    i = status['dl']['file']
                    try:
                        remove(i)
                    except Exception:
                        pass
                    for i in status['dl']['files']:
                        try:
                            remove(i)
                        except Exception:
                            pass
                msg = msg.err(5, MSG_BACKEND_ERROR, playlistitem=None)
            self.osc_t.close()
            self.osc_s = None
            return msg

        def halt(self):
            self.osc_c.send_message('/haltjob', 1)

        def open_and_wait(self, args):
            pthfile = join(split(__file__)[0], '..', '..', 'youtubedl_process.py')
            subprocess.run([sys.executable, pthfile, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        @staticmethod
        def find_free_port():
            sock = socket.socket()
            sock.bind(('', 0))
            return sock.getsockname()[1]

        def send_job(self, job, *_):
            self.osc_c.send_message('/startjob', (job[0], json.dumps(job[1])))

        def job_progress(self, status, _, extstatus):
            newdict = json.loads(extstatus)
            status['dl'].update(newdict)

        def job_done(self, status, _, exits):
            status['dlx'] = json.loads(exits)
            self.osc_c.send_message('/destroy', 1)

        async def init_osc_client_server(self, job, status):
            dispatcher = Dispatcher()
            dispatcher.map("/iamalive", partial(self.send_job, job))
            dispatcher.map("/jobprogress", partial(self.job_progress, status))
            dispatcher.map("/jobdone", partial(self.job_done, status))
            myport = self.find_free_port()
            self.osc_s = AsyncIOOSCUDPServer(('127.0.0.1', myport), dispatcher, asyncio.get_event_loop())
            self.osc_t, _ = await self.osc_s.create_serve_endpoint()  # Create datagram endpoint and start serving
            hisport = self.find_free_port()
            self.osc_c = SimpleUDPClient('127.0.0.1', hisport)
            return (str(hisport), str(myport))

    async def processDl(self, msg: PlaylistMessage, userid, executor):
        x = msg.playlistItemId()
        if x:
            it = await PlaylistItem.loadbyid(self.db, rowid=x)
            if it:
                pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
                if pls:
                    drm = '_drm_k' in it.conf and it.conf['_drm_k'] and '_drm_m' in it.conf and it.conf['_drm_m']
                    sp = msg.init_send_status_with_ping()
                    downloader = self.DRMDownloader(it, msg, self.db, self.dl_dir) if drm else self.YTDLDownloader(it, msg, self.db, self.dl_dir)
                    if pls[0].useri != userid:
                        return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                    elif self.downloader:
                        k = str(x)
                        if k in self.dl_q:
                            tp: MessageProcessor.Downloader = self.dl_q[k]
                            tp.mark_del()
                            tp.awake()
                            return msg.ok()
                        elif 'dlid' in self.status and self.status['dlid'] == x:
                            self.downloader.halt()
                            return msg.ok()
                        else:
                            self.dl_q[k] = downloader
                            sp['que'] = True
                            await downloader.go_to_sleep()
                            del self.dl_q[k]
                    if not downloader.is_deleted():
                        self.downloader = downloader
                        self.status['dlid'] = it.rowid
                        sp['que'] = False
                        self.status['dl'] = sp
                        self.status['dlx'] = dict()
                        msg = await downloader.dl(self.status, executor)
                        self.status['dlid'] = -1
                        self.downloader = None
                    else:
                        msg = msg.err(100, MSG_TASK_ABORT, playlistitem=None)
                    if len(self.dl_q) and ('dlid' not in self.status or self.status['dlid'] == -1):
                        next(iter(self.dl_q.items()))[1].awake()
                    return msg
                else:
                    return msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlistitem=None)
            else:
                return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        elif self.downloader:
            for _, i in self.dl_q.items():
                i.mark_del()
            self.downloader.halt()
            return msg.ok()

    async def processFreeSpace(self, msg, userid, executor):
        x = msg.playlistItemId()
        if x:
            it = await PlaylistItem.loadbyid(self.db, rowid=x)
            if it:
                pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
                if pls:
                    if pls[0].useri != userid:
                        return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                    else:
                        todel = await it.clean(self.db, True)
                        return msg.ok(playlistitem=it, deleted=todel)
                else:
                    msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlistitem=None)
            else:
                return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        else:
            return msg.err(1, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)

    async def processIOrder(self, msg, userid, executor):
        x = msg.playlistItemId()
        if x is not None:
            it = await PlaylistItem.loadbyid(self.db, rowid=x)
            if it:
                pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_ALL)
                if pls:
                    pl = pls[0]
                    items = pl.items
                    if pl.useri != userid:
                        return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                    dest_iorder = msg.f("iorder")
                    round_iorder = dest_iorder if (dest_iorder % 10) == 0 else (dest_iorder // 10 + 1) * 10
                    plus_idx = -1
                    # await pl.cleanItems(self.db, commit=False)
                    foundme = False
                    for idx, other_it in enumerate(items):
                        if other_it.rowid != x:
                            if plus_idx < 0 and other_it.iorder >= dest_iorder:
                                plus_idx = idx
                        else:
                            it = other_it
                            foundme = True
                        if foundme and plus_idx >= 0:
                            break
                    fix_order = False
                    if plus_idx >= 0:
                        _LOGGER.debug(f"PlusIdx {plus_idx}")
                        cur_iorder = round_iorder + (len(items) - plus_idx) * 10
                        for idx in range(len(items) - 1, plus_idx - 1, -1):
                            _LOGGER.debug(f"SetIorder {items[idx]} -> {cur_iorder}")
                            if not await items[idx].setIOrder(self.db, -cur_iorder, commit=False):
                                return msg.err(5, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                            items[idx].iorder = -items[idx].iorder
                            cur_iorder -= 10
                        fix_order = True
                    if await it.setIOrder(self.db, round_iorder, commit=not fix_order):
                        if fix_order and not await pl.fix_iorder(self.db, commit=fix_order):
                            return msg.err(6, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                        else:
                            pl.items.sort(key=lambda x: x.iorder)
                            return msg.ok(playlistitem=it, playlist=pl)
                    else:
                        return msg.err(2, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                else:
                    msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlistitem=None)
            else:
                return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        else:
            return msg.err(1, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)

    async def processDel(self, msg, userid, executor):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, rowid=x, loaditems=LOAD_ITEMS_NO)
            if pls:
                if pls[0].useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                res = await pls[0].delete(self.db, commit=False)
                if res:
                    await Playlist.reset_index(self.db, useri=userid, commit=True)
                    return msg.ok(playlist=x)
                else:
                    msg.err(2, MSG_PLAYLIST_NOT_FOUND, playlist=None)
            else:
                msg.err(3, MSG_PLAYLIST_NOT_FOUND, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processSort(self, msg, userid, executor):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, rowid=x, loaditems=LOAD_ITEMS_ALL, sort_item_field='datepub')
            if pls:
                pl = pls[0]
                if pl.useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                # await pl.cleanItems(self.db, commit=False)
                cur_iorder = 10
                for other_it in pl.items:
                    if not await other_it.setIOrder(self.db, -cur_iorder, commit=False):
                        return msg.err(5, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                    other_it.iorder = -other_it.iorder
                    cur_iorder += 10
                if pl.items:
                    if not await pl.fix_iorder(self.db, commit=True):
                        return msg.err(2, MSG_PLAYLIST_NOT_FOUND, playlist=None)
                    pl.items.sort(key=lambda x: x.iorder)
                return msg.ok(playlist=pl)
            else:
                return msg.err(3, MSG_PLAYLIST_NOT_FOUND, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processIndex(self, msg, userid, executor):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, rowid=x, loaditems=LOAD_ITEMS_NO)
            if pls:
                pl = pls[0]
                if pl.useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                plss = await Playlist.loadbyid(self.db, useri=userid, loaditems=LOAD_ITEMS_NO)
                index = msg.f('index') + 0.5
                for i, pl in enumerate(plss):
                    if pl.rowid == x:
                        pl.iorder = index
                    else:
                        pl.iorder = i + 1
                plss.sort(key=lambda x: x.iorder)
                for i, pl in enumerate(plss):
                    pl.iorder = i + 1
                    await pl.toDB(self.db, commit=False)
                await self.db.commit()
                return msg.ok(sort=plss)
            else:
                return msg.err(3, MSG_PLAYLIST_NOT_FOUND, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processClear(self, msg, userid, executor):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, rowid=x, loaditems=LOAD_ITEMS_NO)
            if pls:
                pl: Playlist = pls[0]
                if pl.useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                if not await pl.clear(self.db):
                    return msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlist=None)
                else:
                    return msg.ok(playlist=pl)
            else:
                return msg.err(3, MSG_PLAYLIST_NOT_FOUND, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processPlayId(self, msg, userid, executor):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, rowid=x, loaditems=LOAD_ITEMS_NO)
            if pls:
                pl = pls[0]
                if pl.useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                # await pl.cleanItems(self.db, commit=False)
                play = pl.conf.get('play', dict())
                pl.conf['play'] = play

                def manage_play_dict(play_dict, message, source_field, dest_field):
                    try:
                        newid = getattr(message, source_field)
                        if not newid and dest_field in play_dict:
                            del play_dict[dest_field]
                        elif newid:
                            play_dict[dest_field] = newid
                    except Exception:
                        pass
                manage_play_dict(play, msg, 'playid', 'id')
                manage_play_dict(play, msg, 'playrate', 'rate')

                rv = await pl.toDB(self.db)
                if not rv:
                    return msg.err(20, MSG_INVALID_PARAM, playlist=None)
                return msg.ok(playlist=pl)
            else:
                return msg.err(3, MSG_PLAYLIST_NOT_FOUND, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processPlaySett(self, msg, userid, executor):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, rowid=x, loaditems=LOAD_ITEMS_NO)
            if pls:
                pl = pls[0]
                if pl.useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                # await pl.cleanItems(self.db, commit=False)
                try:
                    play = pl.conf.get('play', dict())
                    pl.conf['play'] = play
                    play['id'] = msg.f('playid')
                    keys = msg.f('key')
                    oldkeys = msg.f('oldkey')
                    cont = msg.f('content')
                    if cont:
                        key = play.get(keys if not oldkeys else oldkeys, dict())
                        if oldkeys and oldkeys in play and keys != oldkeys:
                            del play[oldkeys]
                        play[keys] = key
                        default_key = msg.f('default')
                        if default_key:
                            key[default_key] = cont
                        else:
                            if 'default' not in key:
                                key['default'] = cont
                            if f'default{DOWNLOADED_SUFFIX}' not in key:
                                key['default{DOWNLOADED_SUFFIX}'] = cont
                        key[msg.f('set')] = cont
                    elif cont is not None:
                        play[keys] = dict()
                    elif keys in play:
                        del play[keys]
                    pls = await Playlist.loadbyid(self.db, useri=userid, loaditems=LOAD_ITEMS_NO)
                    for plt in pls:
                        if plt.rowid != x:
                            play = plt.conf.get('play', dict())
                            plt.conf['play'] = play
                            if cont is None:
                                if keys in play:
                                    del play[keys]
                                    await plt.toDB(self.db, commit=False)
                            elif keys not in play or (oldkeys and oldkeys in play and keys != oldkeys):
                                newconf = dict()
                                if oldkeys and oldkeys in play:
                                    newconf = play[oldkeys]
                                    del play[oldkeys]
                                play[keys] = newconf
                                await plt.toDB(self.db, commit=False)
                    rv = await pl.toDB(self.db)
                    if not rv:
                        return msg.err(20, MSG_INVALID_PARAM, playlist=None)
                    return msg.ok(playlist=pl)
                except Exception:
                    _LOGGER.error(traceback.format_exc())
                    return msg.err(30, MSG_INVALID_PARAM, playlist=None)
            else:
                return msg.err(3, MSG_PLAYLIST_NOT_FOUND, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def process(self, ws, msg, userid, executor):
        resp = None
        if msg.c(CMD_DEL):
            resp = await self.processDel(msg, userid, executor)
        elif msg.c(CMD_MOVE):
            resp = await self.processMove(msg, userid, executor)
        elif msg.c(CMD_PLAYID):
            resp = await self.processPlayId(msg, userid, executor)
        elif msg.c(CMD_PLAYSETT):
            resp = await self.processPlaySett(msg, userid, executor)
        elif msg.c(CMD_PLAYITSETT):
            resp = await self.processPlayItSett(msg, userid, executor)
        elif msg.c(CMD_ADD):
            resp = await self.processAdd(msg, userid, executor)
        elif msg.c(CMD_REN):
            resp = await self.processRen(msg, userid, executor)
        elif msg.c(CMD_DUMP):
            resp = await self.processDump(msg, userid, executor)
        elif msg.c(CMD_CLEAR):
            resp = await self.processClear(msg, userid, executor)
        elif msg.c(CMD_SEEN):
            resp = await self.processSeen(msg, userid, executor)
        elif msg.c(CMD_SEEN_PREV):
            resp = await self.processSeenPrev(msg, userid, executor)
        elif msg.c(CMD_IORDER):
            resp = await self.processIOrder(msg, userid, executor)
        elif msg.c(CMD_INDEX):
            resp = await self.processIndex(msg, userid, executor)
        elif msg.c(CMD_DOWNLOAD):
            resp = await self.processDl(msg, userid, executor)
        elif msg.c(CMD_SORT):
            resp = await self.processSort(msg, userid, executor)
        elif msg.c(CMD_ITEMDUMP):
            resp = await self.processItemDump(msg, userid, executor)
        elif msg.c(CMD_TOKEN):
            resp = await self.processToken(msg, userid, executor)
        elif msg.c(CMD_FREESPACE):
            resp = await self.processFreeSpace(msg, userid, executor)
        elif msg.c(CMD_USER_SETTINGS):
            resp = await self.processUserSettings(msg, userid, executor)
        elif msg.c(CMD_CLOSE):
            if ws is not None:
                await ws.close()
        if resp:
            if ws is not None:
                await ws.send_str(json.dumps(resp, cls=MyEncoder))
            return resp
        else:
            return None
