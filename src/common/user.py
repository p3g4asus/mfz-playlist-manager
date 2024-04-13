import json
import logging
from typing import Union
from uuid import uuid4
from aiosqlite import Connection

from common.utils import Fieldable, JSONAble


_LOGGER = logging.getLogger(__name__)


class User(Fieldable, JSONAble):
    def __init__(self, dbitem: dict = None, rowid: int = None, username: str = None, password: str = None, tg: str = None, token: str = None, conf: Union[dict, str] = dict(), **kwargs):
        if dbitem:
            if isinstance(dbitem, str):
                dbitem = json.loads(dbitem)
            self.rowid: int = dbitem['rowid']
            self.username: str = dbitem['username']
            self.password: str = dbitem['password']
            self.tg: str = dbitem['tg']
            self.token: str = dbitem['token']
            self.conf: dict = dbitem['conf']
        else:
            self.rowid = rowid
            self.username: str = username
            self.password: str = password
            self.tg: str = tg
            self.token: str = token
            self.conf: dict = conf
        if self.conf and isinstance(self.conf, str):
            self.conf = json.loads(self.conf)
        elif not isinstance(self.conf, dict):
            self.conf = dict()

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def toJSON(self, **kwargs) -> dict:
        dct = vars(self)
        # del dct['typei']
        # del dct['useri']
        return dct

    @staticmethod
    async def loadbyid(db: Connection, rowid: int = None, username: str = None, token: str = None, password: str = None, tg: str = None, item_id: int = None) -> list:
        pls = []
        commontxt = f'''
            SELECT P.username AS username,
            P.password AS password,
            P.rowid AS rowid,
            P.token AS token,
            P.conf AS conf,
            P.tg AS tg
            FROM user AS P{", playlist AS K, playlist_item AS Z" if item_id else ""}
            WHERE
        '''
        where = ''
        pars = tuple()
        if isinstance(rowid, int):
            where = ' P.rowid=?'
            pars = (rowid, )
        elif token:
            where = ' P.token=?'
            pars = (token, )
        elif username and password:
            where = ' P.username=? AND P.password=?'
            pars = (username, password, )
        elif tg:
            where = ' P.tg=?'
            pars = (tg, )
        elif isinstance(item_id, int):
            where = ' K.user=P.rowid AND K.rowid=Z.playlist AND Z.rowid=?'
            pars = (item_id, )
        else:
            return list()
        cursor = await db.execute(
            commontxt + where, pars
        )
        async for row in cursor:
            dctr = dict(row)
            _LOGGER.debug("Row %s" % str(dctr))
            pl = User(dbitem=dctr)
            pls.append(pl)
        return pls

    async def toDB(self, db: Connection, commit: bool = True):
        if isinstance(self.conf, str):
            c = self.conf
        else:
            c = json.dumps(self.conf)
        if self.rowid:
            async with db.execute(
                '''
                SELECT count(*) FROM user
                WHERE (username = ? OR token = ?) AND rowid != ?
                ''', (self.username, self.token, self.rowid)
            ) as cursor:
                data = (await cursor.fetchone())[0]
                if data:
                    return False
            async with db.cursor() as cursor:
                await cursor.execute(
                    '''
                    UPDATE user SET username=?, tg=?, token=?, conf=?, password=? WHERE rowid=?
                    ''', (self.username, self.tg, self.token, c, self.password, self.rowid)
                )
                if cursor.rowcount <= 0:
                    return False
        else:
            async with db.execute(
                '''
                SELECT count(*) FROM user
                WHERE username = ? OR token = ?
                ''', (self.username, self.token)
            ) as cursor:
                data = (await cursor.fetchone())[0]
                if data:
                    return False
            async with db.cursor() as cursor:
                await cursor.execute(
                    '''
                    INSERT OR IGNORE into user(username,tg,token,conf,password) VALUES (?,?,?,?,?)
                    ''',
                    (self.username, self.tg, self.token, c, self.password)
                )
                if cursor.rowcount <= 0:
                    return False
                self.rowid = cursor.lastrowid

        if commit:
            await db.commit()
        return True

    async def refreshToken(self, db: Connection, commit: bool = True) -> str:
        while True:
            token = str(uuid4())
            users = await User.loadbyid(db, token=token)
            if not users:
                self.token = token
                await self.toDB(db, commit)
                return self.token

    @staticmethod
    async def get_settings(db, userid, *args, **kwargs):
        users: list[User] = await User.loadbyid(db, rowid=userid)
        out = []
        if users:
            dct: dict = users[0].conf.get('settings', dict())
            for a in args:
                out.append(dct.get(a, kwargs.get(a)))
        return out[0] if len(out) == 1 else out
