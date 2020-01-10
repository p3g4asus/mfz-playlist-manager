import json
from .utils import JSONAble, Fieldable
import logging


_LOGGER = logging.getLogger(__name__)


class Playlist(JSONAble, Fieldable):
    def __init__(self, dbitem=None, rowid=None, name=None, items=None, typei=None, type=None, useri=None, user=None, conf=None, **kwargs):
        if dbitem:
            if isinstance(dbitem, str):
                dbitem = json.loads(dbitem)
            self.rowid = dbitem['rowid']
            self.name = dbitem['name']
            self.typei = dbitem['typei'] if 'typei' in dbitem else None
            self.type = dbitem['type'] if 'type' in dbitem else None
            self.useri = dbitem['useri'] if 'useri' in dbitem else None
            self.user = dbitem['user'] if 'user' in dbitem else None
            self.items = dbitem['items'] if 'items' in dbitem else items if items else []
            self.conf = dbitem['conf']
        else:
            self.rowid = None
            if isinstance(rowid, str) and not name and (useri or user):
                self.name = rowid
            else:
                self.rowid = rowid
                self.name = name
            self.typei = typei
            self.type = type
            self.useri = useri
            self.user = user
            self.items = items if items else []
            self.conf = conf
        for i in range(len(self.items)):
            it = self.items[i]
            if not isinstance(it, PlaylistItem):
                self.items[i] = PlaylistItem(dbitem=it)
        if self.conf and isinstance(self.conf, str):
            self.conf = json.loads(self.conf)

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def toJSON(self):
        dct = vars(self)
        # del dct['typei']
        # del dct['useri']
        return dct

    def toM3U(self):
        s = "#EXTM3U\r\n"
        for i in self.items:
            if not i.seen:
                s += i.toM3U()
        return s

    @staticmethod
    async def loadbyid(db, id=None, useri=None, name=None, username=None, loaditems=True):
        pls = []
        commontxt = '''
            SELECT P.name AS name,
            P.type AS typei,
            P.rowid AS rowid,
            P.user AS useri,
            P.conf AS conf,
            T.name AS type,
            U.username AS user
            FROM playlist AS P, user AS U, type AS T
            WHERE P.type=T.rowid AND P.user=U.rowid%s%s
        ''' % (
                "" if not isinstance(id, int) else (" AND P.rowid=%d" % id),
                "" if not isinstance(useri, int) else (" AND P.user=%d" % useri),
              )
        if isinstance(name, str) and len(name) and isinstance(username, str) and len(username):
            cursor = await db.execute(
                commontxt + " AND P.name=? AND U.username=?", (name, username)
            )
        elif isinstance(name, str) and len(name):
            cursor = await db.execute(
                commontxt + " AND P.name=?", (name,)
            )
        elif isinstance(username, str) and len(username):
            cursor = await db.execute(
                commontxt + " AND U.username=?", (username,)
            )
        else:
            cursor = await db.execute(
                commontxt
            )
        async for row in cursor:
            subcursor = await db.execute(
                '''
                SELECT * FROM playlist_item WHERE playlist=?
                ''',
                (row['rowid'],)
            )
            items = []
            dctr = dict(row)
            _LOGGER.debug("Row %s" % str(dctr))
            if loaditems:
                async for subrow in subcursor:
                    dctsr = dict(subrow)
                    osr = PlaylistItem(dbitem=dctsr)
                    _LOGGER.debug("SubRow %s / %s" % (str(dctsr), str(osr)))
                    items.append(osr)
            pl = Playlist(dbitem=dctr, items=items)
            _LOGGER.debug("Playlist %s" % str(pl))
            pls.append(pl)
        return pls

    async def getTypeI(self, db):
        async with db.execute(
            '''
            SELECT rowid FROM type WHERE name=?
            ''',
            (self.type,)
        ) as cursor:
            try:
                it = await cursor.fetchone()
                if it:
                    return it['rowid']
            except Exception:
                pass
        return None

    async def getUserI(self, db):
        async with db.execute(
            '''
            SELECT rowid FROM user WHERE username=?
            ''',
            (self.user,)
        ) as cursor:
            try:
                it = await cursor.fetchone()
                if it:
                    return it['rowid']
            except Exception:
                pass
        return None

    async def delete(self, db):
        rv = False
        if self.rowid:
            async with db.cursor() as cursor:
                await cursor.execute("DELETE FROM playlist WHERE rowid=?", (self.rowid,))
                rv = cursor.rowcount > 0
        elif self.name and (self.useri or self.user):
            if self.useri is None:
                self.useri = await self.getUserI(db)
                if self.useri:
                    async with db.cursor() as cursor:
                        await cursor.execute("DELETE FROM playlist WHERE name=? and user=?", (self.name, self.useri))
                        rv = cursor.rowcount > 0
        if rv:
            await db.commit()
        return rv

    def isOk(self):
        return self.typei and self.useri and self.name

    def __eq__(self, other):
        if self.rowid is not None and other.rowid is not None:
            return self.rowid == other.rowid
        elif self.rowid is None and other.rowid is None:
            return ((self.useri and self.useri == other.useri) or
                    (self.user and self.user == other.user)) and\
                    self.name == other.name
        else:
            return False

    async def toDB(self, db):
        if isinstance(self.conf, str):
            c = self.conf
        else:
            c = json.dumps(self.conf)
        if self.typei is None:
            self.typei = await self.getTypeI(db)
        if self.useri is None:
            self.useri = await self.getUserI(db)
        if self.isOk():
            if self.rowid:
                async with db.execute(
                    '''
                    SELECT count(*) FROM playlist
                    WHERE name = ? AND user = ? AND rowid != ?
                    ''', (self.name, self.useri, self.rowid)
                ) as cursor:
                    data = (await cursor.fetchone())[0]
                    if data:
                        return False
                async with db.cursor() as cursor:
                    await cursor.execute(
                        '''
                        UPDATE playlist SET name=?, conf=? WHERE rowid=?
                        ''', (self.name, c, self.rowid)
                    )
                    if cursor.rowcount <= 0:
                        return False
            else:
                async with db.execute(
                    '''
                    SELECT count(*) FROM playlist
                    WHERE name = ? AND user = ?
                    ''', (self.name, self.useri)
                ) as cursor:
                    data = (await cursor.fetchone())[0]
                    if data:
                        return False
                async with db.cursor() as cursor:
                    await cursor.execute(
                        '''
                        INSERT OR IGNORE into playlist(name,user,type,conf) VALUES (?,?,?,?)
                        ''',
                        (self.name, self.useri, self.typei, c)
                    )
                    if cursor.rowcount <= 0:
                        return False
                    self.rowid = cursor.lastrowid
            for i in self.items:
                if not i.seen:
                    i.playlist = self.rowid
                    await i.toDB(db)
            await db.commit()
            return True
        else:
            return False


class PlaylistItem(JSONAble, Fieldable):
    def __init__(self, dbitem=None, title=None, uid=None, rowid=None, link=None, conf=None, playlist=None, img=None, datepub=None, dur=None, seen=None, **kwargs):
        if dbitem:
            if isinstance(dbitem, str):
                dbitem = json.loads(dbitem)
            self.rowid = dbitem['rowid']
            self.uid = dbitem['uid']
            self.link = dbitem['link']
            self.title = dbitem['title']
            self.playlist = dbitem['playlist']
            self.img = dbitem['img']
            self.datepub = dbitem['datepub']
            self.conf = dbitem['conf']
            self.dur = dbitem['dur']
            self.seen = dbitem['seen']
        else:
            self.rowid = rowid
            self.uid = uid
            self.link = link
            self.title = title
            self.playlist = playlist
            self.img = img
            self.conf = conf
            self.datepub = datepub
            self.dur = dur
            self.seen = seen
        if self.conf and isinstance(self.conf, str):
            self.conf = json.loads(self.conf)

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def __eq__(self, other):
        if self.rowid is not None and other.rowid is not None:
            return self.rowid == other.rowid
        else:
            return self.uid and self.uid == other.uid and\
                self.playlist == other.playlist and self.playlist

    def toJSON(self):
        dct = vars(self)
        # del dct['playlist']
        return dct

    @staticmethod
    async def loadbyid(db, rowid):
        subcursor = await db.execute(
            '''
            SELECT * FROM playlist_item WHERE rowid=?
            ''',
            (rowid,)
        )
        data = await subcursor.fetchone()
        if data:
            return PlaylistItem(dbitem=data)
        else:
            return None

    async def setSeen(self, db, value=True):
        rv = False
        if self.rowid:
            async with db.cursor() as cursor:
                if value:
                    await cursor.execute(
                        "UPDATE playlist_item SET seen=datetime('now') WHERE rowid=?",
                        (self.rowid,))
                else:
                    await cursor.execute(
                        "UPDATE playlist_item SET seen=NULL WHERE rowid=?",
                        (self.rowid,))
                rv = cursor.rowcount > 0
        if rv:
            await db.commit()
        return rv

    def toM3U(self):
        return "#EXTINF:0,%s\r\n%s\r\n\r\n" % (self.title if self.title else "N/A", self.link)

    async def isPresent(self, db):
        if not self.playlist or not self.uid:
            return False
        else:
            async with db.execute(
                '''
                SELECT count(*) FROM playlist_item
                WHERE uid = ? AND playlist = ?
                ''', (self.uid, self.playlist)
            ) as cursor:
                data = (await cursor.fetchone())[0]
                return data > 0
            return False

    async def delete(self, db):
        rv = False
        if self.rowid:
            async with db.cursor() as cursor:
                await cursor.execute("DELETE FROM playlist_item WHERE rowid=?", (self.rowid,))
                rv = cursor.rowcount > 0
        elif self.uid and self.playlist:
            async with db.cursor() as cursor:
                await cursor.execute("DELETE FROM playlist_item WHERE uid=?", (self.uid,))
                rv = cursor.rowcount > 0
        if rv:
            await db.commit()
        return rv

    def isOk(self):
        return self.link and self.uid and self.playlist

    async def toDB(self, db):
        if isinstance(self.conf, str):
            c = self.conf
        else:
            c = json.dumps(self.conf)
        if self.isOk():
            seen = None
            async with db.execute(
                '''
                SELECT seen FROM playlist_item
                WHERE uid = ? AND playlist = ?
                ''', (self.uid, self.playlist)
            ) as cursor:
                seen = await cursor.fetchone()
                if seen:
                    seen = seen[0]
            async with db.cursor() as cursor:
                await cursor.execute(
                    '''
                    INSERT OR REPLACE INTO playlist_item(
                        rowid,uid,link,title,playlist,conf,datepub,img,dur,seen
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    ''',
                    (self.rowid,
                     self.uid,
                     self.link,
                     self.title,
                     self.playlist,
                     c,
                     self.datepub,
                     self.img,
                     self.dur,
                     seen))
                self.seen = seen
                self.rowid = cursor.lastrowid
            return True
        else:
            return False


class PlaylistMessage(JSONAble, Fieldable):

    def set_from_dict(self, dictionary):
        for key in dictionary:
            if key == "playlist" and isinstance(dictionary[key], dict):
                setattr(self, key, Playlist(dbitem=dictionary[key]))
            elif key == "playlists" and isinstance(dictionary[key], list):
                self.playlists = []
                for p in dictionary[key]:
                    if isinstance(p, dict):
                        self.playlists.append(Playlist(dbitem=p))
                    else:
                        self.playlists.append(p)
            else:
                setattr(self, key, dictionary[key])

    def __init__(self, cmd=None, *dictpars, **kwargs):
        self.cmd = cmd
        for dictionary in dictpars:
            self.set_from_dict(dictionary)
        self.set_from_dict(kwargs)

    def c(self, cmd):
        return self.cmd == cmd

    def ok(self, **kwargs):
        op = vars(self)
        return PlaylistMessage(None, op, rv=0, **kwargs)

    def err(self, err, msg, **kwargs):
        op = vars(self)
        return PlaylistMessage(None, op, rv=err, err=msg, **kwargs)

    def playlistItemId(self):
        x = self.f("playlistitem")
        if x:
            if isinstance(x, PlaylistItem):
                return x.rowid
            elif isinstance(x, int):
                return x
        return None

    def playlistId(self):
        x = self.f("playlist")
        if x:
            if isinstance(x, Playlist):
                return x.rowid
            elif isinstance(x, int):
                return x
        return None

    def playlistObj(self):
        x = self.f("playlist")
        if x:
            if isinstance(x, Playlist):
                return x
        return None

    def toJSON(self):
        return vars(self)
