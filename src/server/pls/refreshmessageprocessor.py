import abc
import json
import logging
import re
import traceback
from datetime import datetime

from sqlalchemy import delete, insert, update
from sqlalchemy.orm import make_transient

from common.const import (CMD_REFRESH, CMD_SYNC, MSG_DB_ERROR, MSG_PLAYLIST_NOT_FOUND,
                          MSG_UNAUTHORIZED, RV_NO_VIDEOS)
from common.playlist_alc_ses import PlaylistComponent, PlaylistItem, PlaylistMessage, LOAD_ITEMS_ALL, LOAD_ITEMS_NO, Playlist
from common.utils import MyEncoder
from server.db.base import AlchemicDB, UsesAlchemicDB
from sqlalchemy.util.concurrency import greenlet_spawn
from server.pls import AbstractMessageProcessor

_LOGGER = logging.getLogger(__name__)


class RefreshMessageProcessor(AbstractMessageProcessor):

    def interested(self, msg):
        if msg.c(CMD_REFRESH) or msg.c(CMD_SYNC):
            x = msg.playlistObj()
            if x:
                return x.type.name == self.get_name()
        return self.interested_plus(msg)

    async def process(self, ws, msg, userid, executor):
        if msg.c(CMD_REFRESH):
            resp = await self.processRefresh(msg, userid, executor)
        elif msg.c(CMD_SYNC):
            resp = await self.processSync(msg, userid, executor)
        else:
            resp = await self.getResponse(msg, userid, executor)
        if resp:
            if ws is not None:
                await ws.send_str(json.dumps(resp, cls=MyEncoder))
            return resp
        else:
            return None

    @abc.abstractmethod
    def get_name(self):
        pass

    @abc.abstractmethod
    def interested_plus(self, msg):
        pass

    @abc.abstractmethod
    async def getResponse(self, msg, userid, executor):
        pass

    @abc.abstractmethod
    def processPrograms(self, msg, datefrom=0, dateto=33134094791000, comps: list[PlaylistComponent] = [], filter=dict(), userid=None, executor=None):
        pass

    @staticmethod
    def video_is_not_filtered_out(video, filters) -> bool:
        if filters:
            if 'durmin' in filters:
                if 'duration' in video and video['duration'] and video['duration'] < filters['durmin']:
                    return False
            if 'durmax' in filters:
                if 'duration' in video and video['duration'] and video['duration'] > filters['durmax']:
                    return False
            if 'yes' in filters:
                for x in filters['yes']:
                    if not re.search(x, video['title'], re.IGNORECASE):
                        return False
            if 'no' in filters:
                for x in filters['no']:
                    if re.search(x, video['title'], re.IGNORECASE):
                        return False
            # keep maybe checking last
            if 'maybe' in filters:
                for x in filters['maybe']:
                    if re.search(x, video['title'], re.IGNORECASE):
                        return True
                return False
        return True

    @staticmethod
    def process_filters(filters: dict) -> dict:
        if 'durmin' in filters and filters['durmin']:
            try:
                filters['durmin'] = int(filters['durmin'][0])
            except Exception:
                del filters['durmin']
        if 'durmax' in filters and filters['durmax']:
            try:
                filters['durmax'] = int(filters['durmax'][0])
            except Exception:
                del filters['durmax']
        return filters

    @staticmethod
    def record_status(sta, newstr, field):
        if PlaylistMessage.PING_STATUS_CONS not in sta or sta[PlaylistMessage.PING_STATUS_CONS]:
            sta[field] = []
            sta[PlaylistMessage.PING_STATUS_CONS] = False
        sta[field].append(newstr)

    @UsesAlchemicDB
    async def processSync(self, msg, userid, executor, **kwargs):
        x = msg.playlistObj()
        if x:
            db = kwargs.get('db', self.db)
            if x.useri != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            datefrom = 0
            dateto = int(datetime.now().timestamp() * 1000)
            if x.rowid is not None:
                n = x.name
                u = x.autoupdate
                x = await Playlist.loadbyid(db, rowid=x.rowid, loaditems=LOAD_ITEMS_ALL)
                if x and len(x):
                    x = x[0]
                else:
                    return msg.err(5, MSG_PLAYLIST_NOT_FOUND, playlist=None)
                if x.useri != userid:
                    return msg.err(502, MSG_UNAUTHORIZED, playlist=None)
                x.name = n
                x.autoupdate = u
            elif x.items is None:
                x.items = []
            resp = await self.processPrograms(msg, datefrom=datefrom, dateto=dateto + 86400000 * 365 * 5, comps=x.components, userid=userid, executor=executor)
            if resp.rv == 0:
                n_new = len(resp.items)
                items = x.items
                if items:
                    items[0].uid = None
                    items[0].rowid = None
                    items[0].delete(db, True)
                items = x.items = resp.items
                try:
                    _LOGGER.debug(f"BTDB PL={x} Items: {items}")
                    x.dateupdate = dateto - 86400 * 3000
                    x = await x.toDB(db)
                    if x:
                        return msg.ok(playlist=x, n_new=n_new)
                    else:
                        return msg.err(18, MSG_DB_ERROR, playlist=None)
                except Exception:
                    _LOGGER.error(traceback.format_exc())
                    return msg.err(20, MSG_DB_ERROR, playlist=None)
            else:
                return resp
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    @UsesAlchemicDB
    async def processAutoRefresh(self, executor, **kwargs):
        db = kwargs.get('db', self.db)
        pls = await Playlist.loadbyid(db, loaditems=LOAD_ITEMS_NO)
        for p in pls:
            if p.autoupdate:
                pm = PlaylistMessage(cmd=CMD_REFRESH,
                                     playlist=p,
                                     datefrom=p.dateupdate,
                                     dateto=None)
                _LOGGER.debug(f"Msg {self.get_name()} = {pm}")
                if self.interested(pm):
                    outmsg = await self.processRefresh(pm, p.useri, executor, **kwargs)
                    _LOGGER.debug(f"OutMsg {self.get_name()} = {outmsg}")
                else:
                    _LOGGER.debug("Ignored")

    @UsesAlchemicDB
    async def processRefresh(self, msg, userid, executor, **kwargs):
        x: Playlist = msg.playlistObj()
        if x:
            db: AlchemicDB = kwargs.get('db', self.db)
            if x.useri != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            datefrom = msg.f('datefrom')
            if datefrom is None:
                datefrom = 0
            dateto = msg.f('dateto')
            if dateto is None:
                dateto = 33134094791000
            # dateto = min(dateto, int(datetime.now().timestamp() * 1000))
            if x.rowid is not None:
                comps: list[PlaylistComponent] = list(x.components)
                n = x.name
                u = x.autoupdate
                x = await Playlist.loadbyid(db, rowid=x.rowid, loaditems=LOAD_ITEMS_NO)
                if x and len(x):
                    x = x[0]
                else:
                    return msg.err(5, MSG_PLAYLIST_NOT_FOUND, playlist=None)
                if x.useri != userid:
                    return msg.err(502, MSG_UNAUTHORIZED, playlist=None)
                else:
                    make_transient(x)
                    xold = x
                newcomps = dict()
                parenti = None
                with db.session.no_autoflush:
                    for i, comp in enumerate(comps):
                        if not i and comp.rowid == 'm':
                            comp.rowid = None
                            comps[i] = comp = await db.upsert(comp)
                            parenti = comp.rowid
                        else:
                            if parenti is not None:
                                comp.parenti = parenti
                            comps[i] = comp = await db.upsert(comp)
                        newcomps[comp.rowid] = comp
                    deletes = []
                    oldcomps = list(xold.components)
                    for comp in oldcomps:
                        if comp.rowid in newcomps:
                            newcomps[comp.rowid].rate = comp.rate
                        else:
                            deletes.append(comp.rowid)
                    if deletes:
                        await db.session.execute(delete(PlaylistComponent).where(PlaylistComponent.rowid.in_(deletes)))
                    await db.commit_session()
                    x = (await Playlist.loadbyid(db, rowid=x.rowid, loaditems=LOAD_ITEMS_ALL))[0]
                    x.name = n
                    x.autoupdate = u
                    if not datefrom and len(x.items):
                        datefrom = x.items[-1].parsed_datepub()
                        _LOGGER.debug("Parsed datefrom %s" % str(datefrom))
                        if datefrom:
                            datefrom = int(datefrom.timestamp() * 1000)
                        else:
                            datefrom = 0
            else:
                if x.items is None:
                    x.items = []
                comps = x.components
                x.components = []
                x = await x.toDB(db, commit=False)
                with db.session.no_autoflush:
                    parenti = None
                    main = False
                    for i, comp in enumerate(comps):
                        comp.playlisti = x.rowid
                        comp.parenti = parenti
                        if comp.rowid == 'm':
                            main = True
                            comp.rowid = None
                        comps[i] = comp = await db.upsert(comp)
                        if main:
                            parenti = comp.rowid
                            main = False
                    if parenti is not None:
                        def _fake_code():
                            for comp in comps:
                                if comp.parent:
                                    pass
                        await greenlet_spawn(_fake_code)
                    x.components = comps
            _LOGGER.debug(f"Datefrom = {datefrom}, dateto={dateto}")
            resp = await self.processPrograms(msg, datefrom=datefrom, dateto=dateto, comps=x.components, filter=msg.f('filter'), userid=userid, executor=executor)
            with db.session.no_autoflush:
                if resp.rv == 0 or resp.rv == RV_NO_VIDEOS:
                    n_new = 0
                    if not resp.rv:
                        items: list[PlaylistItem] = x.items
                        for i in resp.items:
                            if i not in items:
                                i = await i.toDB(db, commit=False)
                                if i:
                                    items.append(i)
                                    _LOGGER.debug("PlsItem new %s" % json.dumps(i, cls=MyEncoder))
                                    n_new += 1
                                else:
                                    _LOGGER.warning('Plsitem invalid %s' % json.dumps(i, cls=MyEncoder))
                            else:
                                idx = items.index(i)
                                _LOGGER.debug("PlsItem exists %s. Is %s [%d]" % (json.dumps(i, cls=MyEncoder), json.dumps(items[idx], cls=MyEncoder), not items[idx].seen))
                                if not items[idx].seen and items[idx].isOk():
                                    i: PlaylistItem
                                    i.iorder = items[idx].iorder
                                    i.rowid = items[idx].rowid
                                    i.dl = items[idx].dl
                                    i.timeplayed = items[idx].timeplayed
                                    i.rate = items[idx].rate
                                    items[idx].conf.update(i.conf)
                                    i.conf = items[idx].conf
                                    items[idx] = await i.toDB(db, commit=False)
                    else:
                        _LOGGER.warning('Refresh OK but no new video')
                    try:
                        dateto = min(dateto, int(datetime.now().timestamp() * 1000))
                        await x.cleanItems(db, dateto - 86400 * 120000, commit=False)
                        _LOGGER.debug(f"BTDB PL={x} Items: {x.items}")
                        x.dateupdate = dateto - 86400 * 3000
                        x = await x.toDB(db)
                        if x:
                            # async with db.session:
                            #     for dbg in x.items:
                            #         if dbg.component:
                            #             pass
                            return msg.ok(playlist=x, n_new=n_new)
                        else:
                            return msg.err(18, MSG_DB_ERROR, playlist=None)
                    except Exception:
                        _LOGGER.error(traceback.format_exc())
                        return msg.err(20, MSG_DB_ERROR, playlist=None)
                else:
                    return resp
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)
