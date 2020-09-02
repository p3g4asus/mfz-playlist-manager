from common.utils import AbstractMessageProcessor, MyEncoder
from common.const import (
    CMD_DEL,
    CMD_REN,
    CMD_DUMP,
    CMD_MOVE,
    CMD_ADD,
    CMD_IORDER,
    CMD_SEEN,
    CMD_SORT,
    CMD_CLOSE,
    MSG_NAME_TAKEN,
    MSG_BACKEND_ERROR,
    MSG_UNAUTHORIZED,
    MSG_PLAYLIST_NOT_FOUND,
    MSG_PLAYLISTITEM_NOT_FOUND
)
from common.playlist import LOAD_ITEMS_ALL, LOAD_ITEMS_NO, Playlist, PlaylistItem
import json
import logging

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(AbstractMessageProcessor):

    def interested(self, msg):
        return msg.c(CMD_DEL) or msg.c(CMD_REN) or msg.c(CMD_DUMP) or\
            msg.c(CMD_ADD) or msg.c(CMD_SEEN) or msg.c(CMD_MOVE) or\
            msg.c(CMD_IORDER) or msg.c(CMD_SORT)

    async def processMove(self, msg, userid):
        pdst = msg.playlistObj()
        itx = msg.playlistItemId()
        if pdst and itx:
            if pdst.rowid:
                pdst = await Playlist.loadbyid(self.db, rowid=pdst.rowid)
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
                pdst.items.append(it)
                return msg.ok(playlist=pdst)
            else:
                return msg.err(4, MSG_BACKEND_ERROR, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processAdd(self, msg, userid):
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

    async def processDump(self, msg, userid):
        u = msg.f("useri", (int,))
        if u:
            if u != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            pl = await Playlist.loadbyid(self.db, rowid=msg.playlistId(), useri=u)
            _LOGGER.debug("Playlists are %s" % str(pl))
            if len(pl):
                return msg.ok(playlist=None, playlists=pl)
        return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processRen(self, msg, userid):
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

    async def processSeen(self, msg, userid):
        x = msg.playlistItemId()
        if x is not None:
            it = await PlaylistItem.loadbyid(self.db, rowid=x)
            if it:
                pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
                if pls:
                    if pls[0].useri != userid:
                        return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                    if await it.setSeen(self.db, msg.f("seen"), commit=True):
                        return msg.ok(playlistitem=x)
                    else:
                        return msg.err(2, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                else:
                    msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlistitem=None)
            else:
                return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        else:
            return msg.err(1, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)

    async def processIOrder(self, msg, userid):
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
                    await pl.cleanItems(self.db, commit=False)
                    for idx, other_it in enumerate(items):
                        if other_it.rowid != x and other_it.iorder >= dest_iorder:
                            plus_idx = idx
                            break
                    if plus_idx >= 0:
                        _LOGGER.debug(f"PlusIdx {plus_idx}")
                        cur_iorder = round_iorder + (len(items) - plus_idx) * 10
                        for idx in range(len(items) - 1, plus_idx - 1, -1):
                            _LOGGER.debug(f"SetIorder {items[idx]} -> {cur_iorder}")
                            if not await items[idx].setIOrder(self.db, -cur_iorder, commit=False):
                                return msg.err(5, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                            items[idx].iorder = -items[idx].iorder
                            cur_iorder -= 10
                    if await it.setIOrder(self.db, round_iorder, commit=False):
                        if not await pl.fix_iorder(self.db, commit=True):
                            return msg.err(6, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                        else:
                            return msg.ok(playlistitem=it)
                    else:
                        return msg.err(2, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                else:
                    msg.err(4, MSG_PLAYLIST_NOT_FOUND, playlistitem=None)
            else:
                return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        else:
            return msg.err(1, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)

    async def processDel(self, msg, userid):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, rowid=x, loaditems=LOAD_ITEMS_NO)
            if pls:
                if pls[0].useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                res = await pls[0].delete(self.db)
                if res:
                    return msg.ok(playlist=x)
                else:
                    msg.err(2, MSG_PLAYLIST_NOT_FOUND, playlist=None)
            else:
                msg.err(3, MSG_PLAYLIST_NOT_FOUND, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processSort(self, msg, userid):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, rowid=x, loaditems=LOAD_ITEMS_ALL, sort_item_field='datepub')
            if pls:
                pl = pls[0]
                if pl.useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                await pl.cleanItems(self.db, commit=False)
                cur_iorder = 10
                for other_it in pl.items:
                    if not await other_it.setIOrder(self.db, -cur_iorder, commit=False):
                        return msg.err(5, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
                    other_it.iorder = -other_it.iorder
                    cur_iorder += 10
                if pl.items:
                    if not await pl.fix_iorder(self.db, commit=True):
                        return msg.err(2, MSG_PLAYLIST_NOT_FOUND, playlist=None)
                return msg.ok(playlist=pl)
            else:
                msg.err(3, MSG_PLAYLIST_NOT_FOUND, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def process(self, ws, msg, userid):
        resp = None
        if msg.c(CMD_DEL):
            resp = await self.processDel(msg, userid)
        if msg.c(CMD_MOVE):
            resp = await self.processMove(msg, userid)
        elif msg.c(CMD_ADD):
            resp = await self.processAdd(msg, userid)
        elif msg.c(CMD_REN):
            resp = await self.processRen(msg, userid)
        elif msg.c(CMD_DUMP):
            resp = await self.processDump(msg, userid)
        elif msg.c(CMD_SEEN):
            resp = await self.processSeen(msg, userid)
        elif msg.c(CMD_IORDER):
            resp = await self.processIOrder(msg, userid)
        elif msg.c(CMD_SORT):
            resp = await self.processSort(msg, userid)
        elif msg.c(CMD_CLOSE):
            await ws.close()
        if resp:
            await ws.send_str(json.dumps(resp, cls=MyEncoder))
            return True
        else:
            return False
