from common.utils import AbstractMessageProcessor, MyEncoder
from common.const import (
    CMD_DEL,
    CMD_REN,
    CMD_DUMP,
    CMD_ADD,
    CMD_SEEN,
    CMD_CLOSE,
    MSG_NAME_TAKEN,
    MSG_UNAUTHORIZED,
    MSG_PLAYLIST_NOT_FOUND,
    MSG_PLAYLISTITEM_NOT_FOUND
)
from common.playlist import Playlist, PlaylistItem
import json
import logging

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(AbstractMessageProcessor):

    def interested(self, msg):
        return msg.c(CMD_DEL) or msg.c(CMD_REN) or msg.c(CMD_DUMP) or\
            msg.c(CMD_ADD) or msg.c(CMD_SEEN)

    async def processAdd(self, msg, userid):
        x = msg.playlistObj()
        if x:
            if x.useri != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            rv = x.toDB(self.db)
            if rv:
                return msg.ok()
            else:
                return msg.err(2, MSG_NAME_TAKEN, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processDump(self, msg, userid):
        u = msg.f("useri", (int,))
        if u:
            if u != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            pl = await Playlist.loadbyid(self.db, id=msg.playlistId(), useri=u)
            _LOGGER.debug("Playlists are %s" % str(pl))
            if len(pl):
                return msg.ok(playlist=None, playlists=pl)
        return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processRen(self, msg, userid):
        x = msg.playlistId()
        if x is not None:
            pls = await Playlist.loadbyid(self.db, id=x, loaditems=False)
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
                pls = await Playlist.loadbyid(self.db, id=it.playlist, loaditems=False)
                if pls:
                    if pls[0].useri != userid:
                        return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                    if await it.setSeen(self.db, msg.f("seen")):
                        await self.db.commit()
                        return msg.ok(playlistitem=x)
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
            pls = await Playlist.loadbyid(self.db, id=x, loaditems=False)
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

    async def process(self, ws, msg, userid):
        resp = None
        if msg.c(CMD_DEL):
            resp = await self.processDel(msg, userid)
        elif msg.c(CMD_ADD):
            resp = await self.processAdd(msg, userid)
        elif msg.c(CMD_REN):
            resp = await self.processRen(msg, userid)
        elif msg.c(CMD_DUMP):
            resp = await self.processDump(msg, userid)
        elif msg.c(CMD_SEEN):
            resp = await self.processSeen(msg, userid)
        elif msg.c(CMD_CLOSE):
            await ws.close()
        if resp:
            await ws.send_str(json.dumps(resp, cls=MyEncoder))
            return True
        else:
            return False
