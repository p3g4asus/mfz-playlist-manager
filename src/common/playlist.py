import json
import logging
import urllib.parse
from datetime import datetime
from os import remove
from common.const import LINK_CONV_BIRD_REDIRECT, LINK_CONV_MASK, LINK_CONV_OPTION_SHIFT, LINK_CONV_OPTION_VIDEO_EMBED, LINK_CONV_REDIRECT, LINK_CONV_TWITCH, LINK_CONV_UNTOUCH, LINK_CONV_YTDL_DICT, LINK_CONV_YTDL_REDIRECT

from .utils import Fieldable, JSONAble, MyEncoder

_LOGGER = logging.getLogger(__name__)

LOAD_ITEMS_NO = 0
LOAD_ITEMS_ALL = 1
LOAD_ITEMS_UNSEEN = 2
LOAD_ITEMS_SEEN = 3


class Playlist(JSONAble, Fieldable):
    def __init__(self, dbitem=None, rowid=None, name=None, items=None, typei=None, type=None, useri=None, user=None, conf=None, dateupdate=None, autoupdate=True, iorder=0, **kwargs):
        if dbitem:
            if isinstance(dbitem, str):
                dbitem = json.loads(dbitem)
            self.rowid = dbitem['rowid']
            self.iorder = dbitem['iorder'] if 'iorder' in dbitem else 0
            self.dateupdate = dbitem['dateupdate']
            self.autoupdate = dbitem['autoupdate'] if 'autoupdate' in dbitem else 1
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
            self.iorder = iorder
            self.typei = typei
            self.type = type
            self.useri = useri
            self.user = user
            self.items = items if items else []
            self.dateupdate = dateupdate
            self.autoupdate = autoupdate
            self.conf = conf
        for i in range(len(self.items)):
            it = self.items[i]
            if not isinstance(it, PlaylistItem):
                self.items[i] = PlaylistItem(dbitem=it)
        if self.conf and isinstance(self.conf, str):
            self.conf = json.loads(self.conf)

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def toJSON(self, **kwargs):
        dct = vars(self)
        # del dct['typei']
        # del dct['useri']
        return dct

    def toM3U(self, host, conv, token=None):
        s = "#EXTM3U\n"
        for i in self.items:
            if not i.seen:
                s += i.toM3U(host, conv, token=token)
        return s

    @staticmethod
    async def loadbyid(db, rowid=None, useri=None, name=None, username=None, loaditems=LOAD_ITEMS_UNSEEN, sort_item_field='iorder', offset=None, limit=None) -> list["Playlist"]:
        pls = []
        sort = ' ORDER BY iorder, rowid'
        commontxt = '''
            SELECT P.name AS name,
            P.type AS typei,
            P.rowid AS rowid,
            P.user AS useri,
            P.conf AS conf,
            P.dateupdate AS dateupdate,
            P.autoupdate AS autoupdate,
            T.name AS type,
            U.username AS user,
            P.iorder AS iorder
            FROM playlist AS P, user AS U, type AS T
            WHERE P.type=T.rowid AND P.user=U.rowid%s%s
        ''' % ("" if not isinstance(rowid, int) else (" AND P.rowid=%d" % rowid),
               "" if not isinstance(useri, int) else (" AND P.user=%d" % useri),)
        if isinstance(name, str) and len(name) and isinstance(username, str) and len(username):
            cursor = await db.execute(
                commontxt + " AND P.name=? AND U.username=?" + sort, (name, username)
            )
        elif isinstance(name, str) and len(name):
            cursor = await db.execute(
                commontxt + " AND P.name=?" + sort, (name,)
            )
        elif isinstance(username, str) and len(username):
            cursor = await db.execute(
                commontxt + " AND U.username=?" + sort, (username,)
            )
        else:
            cursor = await db.execute(
                commontxt + sort
            )
        async for row in cursor:
            dctr = dict(row)
            _LOGGER.debug("Row %s" % str(dctr))
            if loaditems != LOAD_ITEMS_NO:
                items = await PlaylistItem.loadbyid(db, None, playlist=row['rowid'], loaditems=loaditems, sortby=sort_item_field, offset=offset, limit=limit)
            else:
                items = []
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

    async def delete(self, db, commit=True):
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
        if rv and commit:
            await db.commit()
        return rv

    @staticmethod
    async def reset_index(db, useri=None, commit=True):
        pls = await Playlist.loadbyid(db, None, useri=useri, loaditems=LOAD_ITEMS_NO)
        for i, pl in enumerate(pls):
            pl.iorder = i + 1
            await pl.toDB(db, commit=False)
        if commit:
            await db.commit()

    def isOk(self):
        return self.typei and self.useri and self.name

    def __eq__(self, other):
        if self.rowid is not None and other.rowid is not None:
            return self.rowid == other.rowid
        elif self.rowid is None and other.rowid is None:
            return ((self.useri and self.useri == other.useri)
                    or (self.user and self.user == other.user)) and self.name == other.name
        else:
            return False

    async def fix_iorder(self, db, commit=True):
        rv = False
        if self.rowid is not None:
            rv = True
            async with db.cursor() as cursor:
                await cursor.execute(
                    '''
                    UPDATE playlist_item SET iorder=abs(iorder) WHERE playlist=?
                    ''', (self.rowid,)
                )
                if cursor.rowcount <= 0:
                    _LOGGER.debug(f"Fix iorder No Items rowid={self.rowid}")
                    rv = False
            if commit and rv:
                await db.commit()
        for i in self.items:
            if isinstance(i.iorder, int):
                i.iorder = abs(i.iorder)
        _LOGGER.debug(f"Fix iorder rv = {rv}")
        return rv

    async def clear(self, db, commit=True):
        if self.rowid:
            async with db.cursor() as cursor:
                await cursor.execute(
                    "UPDATE playlist_item SET seen=datetime('now') WHERE playlist=? AND seen IS NULL",
                    (self.rowid, ))
            if commit:
                await db.commit()
            return True
        else:
            return False

    async def cleanItems(self, db, datelimit, commit=True):
        items = self.items
        rv = True
        for idx in range(len(items) - 1, -1, -1):
            other_it = items[idx]
            rvn = True
            if not other_it.isOk() and other_it.playlist is not None:
                rvn = await other_it.delete(db, commit=False)
                del items[idx]
            elif other_it.seen:
                dp = datetime.strptime(other_it.seen, '%Y-%m-%d %H:%M:%S')
                if int(dp.timestamp() * 1000) < datelimit:
                    rvn = await other_it.delete(db, commit=False)
                    del items[idx]
                elif other_it.rowid is not None:
                    rvn = await other_it.setIOrder(db, -(idx + 1) * 10, commit=False)
                else:
                    other_it.iorder = -(idx + 1) * 10
            elif other_it.rowid is not None:
                rvn = await other_it.setIOrder(db, -(idx + 1) * 10, commit=False)
            else:
                other_it.iorder = -(idx + 1) * 10
            if not rvn:
                rv = rvn
        await self.fix_iorder(db, commit=commit)
        return rv

    async def toDB(self, db, commit=True):
        if isinstance(self.conf, str):
            c = self.conf
        else:
            c = json.dumps(self.conf, cls=MyEncoder)
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
                        UPDATE playlist SET name=?, dateupdate=?, autoupdate=?, conf=?, iorder=? WHERE rowid=?
                        ''', (self.name, self.dateupdate, self.autoupdate, c, self.iorder, self.rowid)
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
                async with db.execute(
                    '''
                    SELECT MAX(iorder) FROM playlist
                    WHERE user = ?
                    ''', (self.useri, )
                ) as cursor:
                    data = (await cursor.fetchone())[0]
                self.iorder = data + 1
                async with db.cursor() as cursor:
                    await cursor.execute(
                        '''
                        INSERT OR IGNORE into playlist(name,user,type,dateupdate,autoupdate,conf,iorder) VALUES (?,?,?,?,?,?,?)
                        ''',
                        (self.name, self.useri, self.typei, self.dateupdate, self.autoupdate, c, self.iorder)
                    )
                    if cursor.rowcount <= 0:
                        return False
                    self.rowid = cursor.lastrowid
            for i in self.items:
                if not i.seen:
                    i.playlist = self.rowid
                    await i.toDB(db, commit=False)
            if commit:
                await db.commit()
            return True
        else:
            return False

    def get_duration(self, seen=False):
        dur = 0
        for i in self.items:
            if seen or not i.seen:
                dur += i.dur
        return dur


class PlaylistItem(JSONAble, Fieldable):
    def __init__(self, dbitem=None, title=None, uid=None, rowid=None, link=None, conf=None, playlist=None, img=None, datepub=None, dur=None, seen=None, iorder=None, dl=None, **kwargs):
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
            self.iorder = dbitem['iorder']
            self.dl = dbitem['dl']
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
            self.iorder = iorder
            self.dl = dl
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

    @staticmethod
    def convert_img_url(thumb, host):
        return urllib.parse.unquote(thumb[6:]) if thumb and thumb[0] == '?' else (f'{host}-s/{thumb[1:]}' if thumb and thumb[0] == '@' else thumb)

    def get_conv_link(self, host, convall, token=None, additional: dict = dict()):
        conv = convall & LINK_CONV_MASK
        embed = (convall >> LINK_CONV_OPTION_SHIFT) & LINK_CONV_OPTION_VIDEO_EMBED
        if conv == LINK_CONV_UNTOUCH:
            if token and embed:
                piece = 'twi'
            else:
                return self.link
        elif conv == LINK_CONV_YTDL_DICT:
            piece = 'ytdl'
        elif conv == LINK_CONV_YTDL_REDIRECT:
            piece = 'ytto'
        elif conv == LINK_CONV_REDIRECT:
            piece = 'red'
        elif conv == LINK_CONV_TWITCH:
            if 'twitch.tv' not in self.link:
                return self.link
            piece = 'twi'
        elif conv == LINK_CONV_BIRD_REDIRECT:
            piece = 'bird'
        dictv = additional.copy()
        dictv.update(dict(conv=conv, link=self.link))
        if token and embed:
            return f"{host}/{piece}s/{token}/{self.rowid}?{urllib.parse.urlencode(dictv)}"
        else:
            return f"{host}/{piece}?{urllib.parse.urlencode(dictv)}"

    def toJSON(self, host='', conv=0, **kwargs):
        dct = vars(self)
        if conv:
            dct = dict(**dct)
            dct['link'] = self.get_conv_link(host, conv, token=kwargs['token'] if 'token' in kwargs else None)
        # del dct['playlist']
        return dct

    def parsed_datepub(self):
        if self.datepub:
            if isinstance(self.datepub, str):
                try:
                    return datetime.strptime(self.datepub, '%Y-%m-%d %H:%M:%S.%f')
                except Exception:
                    return None
            elif isinstance(self.datepub, datetime):
                return self.datepub
        return None

    @staticmethod
    async def loadbyid(db, rowid, playlist=None, loaditems=LOAD_ITEMS_UNSEEN, sortby='iorder', offset=None, limit=None, user=None, dl=None):
        if isinstance(rowid, int):
            where = f'WHERE rowid={rowid}'
            listresult = False
        elif not isinstance(playlist, int):
            return None
        else:
            where = f'WHERE PI.playlist = {playlist}'
            if loaditems == LOAD_ITEMS_UNSEEN:
                where += ' AND PI.seen IS NULL AND PI.link IS NOT NULL'
            elif loaditems == LOAD_ITEMS_SEEN:
                where += ' AND PI.seen IS NOT NULL'
            listresult = True
        if limit is not None and offset is not None:
            lc = f'LIMIT {offset},{limit}'
        else:
            lc = ''
        if dl:
            where += ' AND (PI.dl IS NOT NULL OR instr(PI.conf, \'"todel"\') > 0)'
        if user:
            where = f'INNER JOIN playlist ON playlist.user={user} AND playlist.rowid=PI.playlist ' + where
        subcursor = await db.execute(
            f'''
            SELECT PI.*
                   FROM playlist_item AS PI
                   {where}
                   ORDER BY {sortby}
                   {lc}
            '''
        )
        if not listresult:
            data = await subcursor.fetchone()
            return PlaylistItem(dbitem=data) if data else None
        else:
            items = []
            async for subrow in subcursor:
                dctsr = dict(subrow)
                osr = PlaylistItem(dbitem=dctsr)
                _LOGGER.debug("SubRow %s / %s" % (str(dctsr), str(osr)))
                items.append(osr)
            return items

    async def setSeen(self, db, value=True, commit=True, previous=False):
        rv = False
        if self.rowid:
            async with db.cursor() as cursor:
                vc = "datetime('now')" if value else "NULL"
                inverse = "IS NULL" if value else "IS NOT NULL"
                await cursor.execute(
                    f"UPDATE playlist_item SET seen={vc} WHERE {'rowid=?' if not previous else ('iorder<=? AND playlist=? AND seen ' + inverse)}",
                    (self.rowid,) if not previous else (self.iorder, self.playlist))
                rv = cursor.rowcount > 0
        if rv and commit:
            await db.commit()
        return rv

    async def setIOrder(self, db, iorder, commit=True):
        rv = False
        if self.rowid:
            async with db.cursor() as cursor:
                await cursor.execute(
                    "UPDATE playlist_item SET iorder=? WHERE rowid=?",
                    (iorder, self.rowid,))
                rv = cursor.rowcount > 0
        if rv:
            self.iorder = iorder
            if commit:
                await db.commit()
        return rv

    def toM3U(self, host, conv, token=None):
        return "#EXTINF:0,%s\n%s\n" % (self.title if self.title else "N/A", self.get_conv_link(host, conv, token=token))

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

    def takes_space(self):
        return self.dl or (self.conf and 'todel' in self.conf and self.conf['todel'])

    async def clean(self, db=None, commit=True):
        todel = []
        if self.dl:
            todel.append(self.dl)
            self.dl = None
        if self.conf and 'todel' in self.conf:
            todel.extend(self.conf['todel'])
            del self.conf['todel']
        _LOGGER.info(f'Clean needs to remove those files: {todel}')
        for fl in todel:
            try:
                remove(fl)
            except Exception:
                pass
        if todel and db:
            await self.toDB(db, commit)
        return todel

    async def delete(self, db, commit=True):
        rv = False
        should_check = False
        if self.rowid:
            async with db.cursor() as cursor:
                await cursor.execute("DELETE FROM playlist_item WHERE rowid=?", (self.rowid,))
                rv = cursor.rowcount > 0
                should_check = True
        elif self.uid and self.playlist:
            async with db.cursor() as cursor:
                await cursor.execute("DELETE FROM playlist_item WHERE uid=? AND playlist=?", (self.uid, self.playlist))
                rv = cursor.rowcount > 0
                should_check = True
        elif self.playlist:
            async with db.cursor() as cursor:
                await cursor.execute("DELETE FROM playlist_item WHERE playlist=?", (self.playlist,))
                rv = cursor.rowcount > 0
        if rv and commit:
            await db.commit()
        if should_check:
            await self.clean()
        return rv

    def isOk(self):
        return self.link and self.uid and self.playlist

    async def move_to(self, playlist, db):
        if playlist != self.playlist:
            await self.setSeen(db)
            self.rowid = None
            self.playlist = playlist
        self.seen = None
        self.iorder = None
        return await self.toDB(db)

    async def move_to_end(self, db):
        return await self.move_to(self.playlist, db)

    async def toDB(self, db, commit=True):
        if isinstance(self.conf, str):
            c = self.conf
        else:
            c = json.dumps(self.conf, cls=MyEncoder)
        if self.isOk():
            if self.iorder is None:
                async with db.execute(
                    '''
                    SELECT max(iorder) + 10 FROM playlist_item WHERE playlist=?
                    ''', (self.playlist,)
                ) as cursor:
                    iorder = await cursor.fetchone()
                    if iorder and iorder[0]:
                        self.iorder = iorder[0]
                    else:
                        self.iorder = 10
            async with db.cursor() as cursor:
                await cursor.execute(
                    '''
                    INSERT OR REPLACE INTO playlist_item(
                        rowid,uid,link,title,playlist,conf,datepub,img,dur,iorder,dl,seen
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
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
                     self.iorder,
                     self.dl,
                     self.seen))
                self.rowid = cursor.lastrowid
            if commit:
                await db.commit()
            return True
        else:
            return False


class PlaylistMessage(JSONAble, Fieldable):
    PING_STATUS = 'send_status_with_ping'
    PING_STATUS_CONS = '__c'

    def init_send_status_with_ping(self, **kwargs):
        d = dict(**kwargs)
        self[PlaylistMessage.PING_STATUS] = d
        return d

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
            elif isinstance(x, (list, tuple)):
                xx = []
                for z in x:
                    if isinstance(z, PlaylistItem):
                        xx.append(z.rowid)
                    elif isinstance(z, int):
                        xx.append(z)
                return xx
        return None

    def playlistId(self):
        x = self.f("playlist")
        if x:
            if isinstance(x, Playlist):
                return x.rowid
            elif isinstance(x, int):
                return x
        return None

    def playlistName(self):
        x = self.f("name")
        if x:
            if isinstance(x, str) and x:
                return x
        return None

    def playlistObj(self):
        x = self.f("playlist")
        if x:
            if isinstance(x, Playlist):
                return x
        return None

    def toJSON(self, **kwargs):
        return vars(self)
