from common.utils import AbstractMessageProcessor
from common.const import (
    CMD_DEL,
    CMD_REN,
    CMD_DUMP,
    CMD_ADD,
    CMD_SEEN,
    CMD_CLOSE,
    MSG_NAME_TAKEN,
    MSG_PLAYLIST_NOT_FOUND,
    MSG_PLAYLISTITEM_NOT_FOUND
)
from common.playlist import Playlist, PlaylistItem
import json


class MessageProcessor(AbstractMessageProcessor):

    def interested(self, msg):
        return msg.c(CMD_DEL) or msg.c(CMD_REN) or msg.c(CMD_DUMP) or msg.c(CMD_ADD)

    async def processAdd(self, msg):
        x = msg.playlistObj()
        if x:
            rv = x.toDB(self.db)
            if rv:
                return msg.ok()
            else:
                return msg.err(2, MSG_NAME_TAKEN, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processDump(self, msg):
        p = msg.playlistId()
        u = msg.f("useri", (int,))
        if p is not None or u is not None:
            pl = await Playlist.loadbyid(self.db, id=p, useri=u)
            if len(pl):
                return msg.ok(playlist=None, playlists=pl)
        return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processRen(self, msg):
        x = msg.playlistId()
        if x is not None:
            pl = Playlist(rowid=x, name=msg.f("to"))
            rv = await pl.toDB(self.db)
            if rv:
                return msg.ok(playlist=x, name=pl.name)
            else:
                return msg.err(2, MSG_NAME_TAKEN, playlist=None)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def processSeen(self, msg):
        x = msg.playlistItemId()
        if x is not None:
            x = await PlaylistItem(rowid=x).setSeen(self.db, msg.f("seen"))
            return msg.ok(playlistitem=x)
        else:
            return msg.err(1, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)

    async def processDel(self, msg):
        x = msg.playlistId()
        if x is not None:
            await Playlist(rowid=x).delete(self.db)
            return msg.ok(playlist=x)
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def process(self, ws, msg):
        resp = None
        if msg.c(CMD_DEL):
            resp = await self.processDel(msg)
        elif msg.c(CMD_ADD):
            resp = await self.processAdd(msg)
        elif msg.c(CMD_REN):
            resp = await self.processRen(msg)
        elif msg.c(CMD_DUMP):
            resp = await self.processDump(msg)
        elif msg.c(CMD_SEEN):
            resp = await self.processSeen(msg)
        elif msg.c(CMD_CLOSE):
            resp = await ws.close()
            return False
        if resp:
            await ws.send_str(json.dumps(resp))
        return True
