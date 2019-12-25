import json
from .utils import JSONAble, Fieldable


class Playlist(JSONAble, Fieldable):
    def __init__(self, dbitem=None, rowid=None, name=None, items=None, typei=None, type=None, useri=None, user=None, conf=None, **kwargs):
        if dbitem:
            if isinstance(dbitem, str):
                dbitem = json.loads(dbitem)
            self.rowid = dbitem['rowid']
            self.name = dbitem['name']
            self.typei = dbitem['typei']
            self.type = dbitem['type']
            self.useri = dbitem['useri']
            self.user = dbitem['user']
            self.items = dbitem['items'] if 'items' in dbitem else items if items else []
            self.conf = dbitem['conf']
        else:
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
        if conf and isinstance(conf, str):
            self.conf = json.loads(self.conf)

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def toJSON(self):
        dct = vars(self)
        del dct['typei']
        del dct['useri']
        return dct

    def toM3U(self):
        s = "#EXTM3U\r\n"
        for i in self.items:
            if not i.seen:
                s += i.toM3U()
        return s

    @staticmethod
    async def loadbyid(db, id=None, useri=None, name=None, username=None):
        pls = []
        commontxt = '''
            SELECT P.name AS name,
            P.user AS user,
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
            subcursor = db.execute(
                '''
                SELECT * FROM playlist_item WHERE playlist=?
                ''',
                row['rowid']
            )
            items = []
            async for subrow in subcursor:
                items.append(PlaylistItem(dbitem=subrow))
            pls.append(Playlist(dbitem=row, items=items))

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
        if self.rowid:
            await db.execute("DELETE FROM playlist WHERE rowid=?", self.rowid)
            return True
        elif self.name and (self.useri or self.user):
            if self.useri is None:
                self.useri = await self.getUserI(db)
                if self.useri:
                    await db.execute("DELETE FROM playlist WHERE name=? and user=?", self.name, self.useri)
                    return True
        return False

    def isOk(self):
        return self.typei and self.useri and self.name

    def __eq__(self, other):
        if self.rowid is not None and other.rowid is not None:
            return self.rowid == other.rowid
        else:
            return ((self.useri and self.useri == other.useri) or
                    (self.user and self.user == other.user)) and\
                    self.name == other.name

    async def toDB(self, db):
        if not isinstance(self.conf, str):
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
                    data = await cursor.fetchone()[0]
                    if data:
                        return False
                await db.execute(
                    '''
                    UPDATE playlist SET name=?, conf=? WHERE rowid=?
                    ''', (self.name, c, self.rowid)
                )
            else:
                async with db.execute(
                    '''
                    SELECT count(*) FROM playlist
                    WHERE name = ? AND user = ?
                    ''', (self.name, self.useri)
                ) as cursor:
                    data = await cursor.fetchone()[0]
                    if data:
                        return False
                async with db.cursor() as cursor:
                    await cursor.execute(
                        '''
                        INSERT OR IGNORE int playlist(name,user,type,conf) VALUES (?,?,?,?)
                        ''',
                        (self.name, self.useri, self.typei, c)
                    )
                    self.rowid = cursor.lastrowid
            for i in self.items:
                if not i.seen:
                    i.playlist = self.rowid
                    await i.toDB(db)
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
        if conf and isinstance(conf, str):
            self.conf = json.loads(self.conf)

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def __eq__(self, other):
        if self.rowid is not None and other.rowid is not None:
            return self.rowid == other.rowid
        else:
            return self.uid == other.uid and self.playlist == other.playlist

    def toJSON(self):
        dct = vars(self)
        del dct['playlist']
        return dct

    async def setSeen(self, db, value=True):
        if self.isOk():
            if value:
                await db.execute(
                    "UPDATE playlist_item SET seen=datetime('now') WHERE rowid=?",
                    (self.rowid,))
            else:
                await db.execute(
                    "UPDATE playlist_item SET seen=NULL WHERE rowid=?",
                    (self.rowid,))
            return True
        else:
            return False

    def toM3U(self):
        return "#EXTINF:0,%s\r\n%s\r\n\r\n" % (self.title if self.title else "N/A", self.link)

    async def isPresent(self, db):
        if self.playlist is None or not self.uid:
            return False
        else:
            async with db.execute(
                '''
                SELECT count(*) FROM playlist_item
                WHERE uid = ? AND playlist = ?
                ''', (self.uid, self.playlist)
            ) as cursor:
                data = await cursor.fetchone()[0]
                return data > 0
            return False

    async def delete(self, db):
        if self.rowid:
            await db.execute("DELETE FROM playlist_item WHERE rowid=?", self.rowid)
            return True
        elif self.uid:
            await db.execute("DELETE FROM playlist_item WHERE uid=?", self.uid)
            return True
        return False

    def isOk(self):
        return self.link and self.uid and self.playlist

    async def toDB(self, db):
        if not isinstance(self.conf, str):
            c = self.conf
        else:
            c = json.dumps(self.conf)
        if self.isOk():
            async with db.cursor() as cursor:
                self.assertFalse(db.in_transaction)
                await cursor.execute(
                    '''
                    INSERT OR REPLACE INTO playlist_item(
                        rowid,uid,link,title,playlist,conf,datepub,img,dur
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    ''',
                    (self.rowid,
                     self.uid,
                     self.link,
                     self.title,
                     self.playlist,
                     c,
                     self.datepub,
                     self.img,
                     self.dur)
                 )
                self.rowid = cursor.lastrowid
            return True
        else:
            return False


class PlaylistMessage(JSONAble, Fieldable):
    def __init__(self, cmd=None, *dictpars, **kwargs):
        self.cmd = cmd
        for dictionary in dictpars:
            for key in dictionary:
                if key == "playlist" and isinstance(dictionary[key], dict):
                    setattr(self, key, Playlist(dbitem=dictionary[key]))
                else:
                    setattr(self, key, dictionary[key])
        for key in kwargs:
            if key == "playlist" and isinstance(kwargs[key], dict):
                setattr(self, key, Playlist(dbitem=kwargs[key]))
            else:
                setattr(self, key, kwargs[key])

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
