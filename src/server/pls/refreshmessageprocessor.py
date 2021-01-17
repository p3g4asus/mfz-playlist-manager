import abc
import json
import logging
import traceback
from datetime import datetime

from common.const import (CMD_REFRESH, MSG_DB_ERROR, MSG_PLAYLIST_NOT_FOUND,
                          MSG_UNAUTHORIZED)
from common.playlist import LOAD_ITEMS_ALL, Playlist
from common.utils import AbstractMessageProcessor, MyEncoder

_LOGGER = logging.getLogger(__name__)


class RefreshMessageProcessor(AbstractMessageProcessor):

    def interested(self, msg):
        if msg.c(CMD_REFRESH):
            x = msg.playlistObj()
            if x:
                return x.type == self.get_name()
        return self.interested_plus(msg)

    async def process(self, ws, msg, userid):
        if msg.c(CMD_REFRESH):
            resp = await self.processRefresh(msg, userid)
        else:
            resp = await self.getResponse(msg, userid)
        if resp:
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
    async def getResponse(self, msg, userid):
        pass

    @abc.abstractmethod
    def processPrograms(self, msg, datefrom=0, dateto=33134094791000, conf=dict(), playlist=None):
        pass

    async def processRefresh(self, msg, userid):
        x = msg.playlistObj()
        if x:
            if x.useri != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            datefrom = msg.f('datefrom')
            if datefrom is None:
                datefrom = 0
            dateto = msg.f('dateto')
            if dateto is None:
                dateto = 33134094791000
            dateto = min(dateto, int(datetime.now().timestamp() * 1000))
            if x.rowid is not None:
                c = x.conf
                n = x.name
                x = await Playlist.loadbyid(self.db, rowid=x.rowid, loaditems=LOAD_ITEMS_ALL)
                if x and len(x):
                    x = x[0]
                else:
                    return msg.err(5, MSG_PLAYLIST_NOT_FOUND, playlist=None)
                if x.useri != userid:
                    return msg.err(502, MSG_UNAUTHORIZED, playlist=None)
                x.conf = c
                x.name = n
                if not datefrom and len(x.items):
                    datefrom = x.items[-1].parsed_datepub()
                    _LOGGER.debug("Parsed datefrom %s" % str(datefrom))
                    if datefrom:
                        datefrom = int(datefrom.timestamp() * 1000)
                    else:
                        datefrom = 0
            elif x.items is None:
                x.items = []
            resp = await self.processPrograms(msg, datefrom=datefrom, dateto=dateto, conf=x.conf, playlist=x.rowid)
            if resp.rv == 0:
                n_new = 0
                items = x.items
                for i in resp.items:
                    if i not in items:
                        items.append(i)
                        _LOGGER.debug("PlsItem new %s" % str(i))
                        n_new += 1
                    else:
                        idx = items.index(i)
                        _LOGGER.debug("PlsItem exists %s. Is %s [%d]" % (str(i), items[idx], not items[idx].seen))
                        if not items[idx].seen and items[idx].isOk():
                            i.iorder = items[idx].iorder
                            items[idx] = i
                try:
                    await x.cleanItems(self.db, commit=False)
                    _LOGGER.debug(f"BTDB PL={x} Items: {items}")
                    x.dateupdate = dateto - 86400*3000
                    rv = await x.toDB(self.db)
                    if rv:
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
