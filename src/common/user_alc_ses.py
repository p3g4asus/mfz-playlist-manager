import logging
from typing import Annotated
from uuid import uuid4

from sqlalchemy import ForeignKey, UniqueConstraint, func, inspect, or_, select, and_
from sqlalchemy.orm import Mapped, make_transient
from sqlalchemy.orm import mapped_column

from server.db.base import AlcTp, AlchemicBase


_LOGGER = logging.getLogger(__name__)


class Player(AlchemicBase):
    __tablename__ = "player"
    rowid: Annotated[Mapped[int], 'U'] = mapped_column(primary_key=True, autoincrement=True)
    name: Annotated[Mapped[str], 'U'] = mapped_column(nullable=False)
    url: Annotated[Mapped[str], 'U'] = mapped_column(nullable=False)
    useri: Annotated[Mapped[int], 'U'] = mapped_column('user', ForeignKey("user.rowid", ondelete="CASCADE"), nullable=False)
    sel: Annotated[Mapped[bool], 'U'] = mapped_column(nullable=False, default=False)
    __table_args__ = (UniqueConstraint('name', 'user', name='uix_name_user'),)


class Browser(AlchemicBase):
    __tablename__ = "browser"
    rowid: Annotated[Mapped[int], 'U'] = mapped_column(primary_key=True, autoincrement=True)
    name: Annotated[Mapped[str], 'U'] = mapped_column(nullable=False)
    url: Annotated[Mapped[str], 'U'] = mapped_column(nullable=False)
    useri: Annotated[Mapped[int], 'U'] = mapped_column('user', ForeignKey("user.rowid", ondelete="CASCADE"), nullable=False)
    sel: Annotated[Mapped[bool], 'U'] = mapped_column(nullable=False, default=False)
    __table_args__ = (UniqueConstraint('name', 'user', name='uix_name_user'),)


class User(AlchemicBase):
    __tablename__ = "user"
    rowid: Annotated[Mapped[int], 'JU'] = mapped_column(primary_key=True, autoincrement=True)
    username: Annotated[Mapped[str], 'JU'] = mapped_column(unique=True)
    password: Annotated[Mapped[str], 'U'] = mapped_column()
    token: Annotated[Mapped[str], 'U'] = mapped_column(unique=True)
    tg: Annotated[Mapped[str], 'U'] = mapped_column()
    conf: Annotated[Mapped[dict], 'U'] = mapped_column()

    def __init__(self, *args, **kwargs):
        if args:
            if len(args) > 1:
                raise ValueError("Too many positional arguments")
            if isinstance(args[0], dict):
                kwargs['dbitem'] = args[0]
                args = []
            else:
                raise ValueError("Positional argument must be a dictionary")
        if 'dbitem' in kwargs and isinstance(kwargs['dbitem'], dict):
            for key, val in kwargs['dbitem'].items():
                kwargs[key] = val
            del kwargs['dbitem']
        super().__init__(*args, **kwargs)

    @staticmethod
    async def loadbyid(engine: AlcTp, rowid: int = None, username: str = None, token: str = None, password: str = None, tg: str = None, item_id: int = None) -> list:
        ussel = select(User)
        if isinstance(rowid, int):
            ussel = ussel.where(User.rowid == rowid)
        elif token:
            ussel = ussel.where(User.token == token)
        elif username and password:
            ussel = ussel.where(and_(User.username == username, User.password == password))
        elif tg:
            ussel = ussel.where(User.tg == tg)
        elif isinstance(item_id, int):
            from .playlist_alc_ses import Playlist, PlaylistItem
            ussel = ussel.join(Playlist, Playlist.useri == User.rowid).join(PlaylistItem, PlaylistItem.playlisti == Playlist.rowid).where(PlaylistItem.rowid == item_id)
        else:
            pass
        return await AlchemicBase.get_query_result(engine, ussel, get_first=False)

    @staticmethod
    async def test_db(dbfile: str, **kwargs):
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine("sqlite+aiosqlite:///" + dbfile, echo=True)
        uss = await User.loadbyid(engine, **kwargs)
        return uss

    async def toDB(self, db: AlcTp, commit: bool = True):
        rv = self
        if self.rowid:
            fq = select(func.count(User.rowid)).where(and_(or_(User.username == self.username, User.token == self.token), User.rowid != self.rowid))
            out = await AlchemicBase.get_query_result(db, fq, get_first=True)
            if out:
                return None
            if (stt := inspect(self)).transient or stt.detached:
                rv = await db.upsert(self)
        else:
            if not inspect(self).transient:
                make_transient(self)
            fq = select(func.count(User.rowid)).where(or_(User.username == self.username, User.token == self.token))
            out = await AlchemicBase.get_query_result(db, fq, get_first=True)
            if out:
                return None
            rv = await db.upsert(self)
        if commit:
            await db.session.commit()
        return rv

    async def refreshToken(self, db: AlcTp, commit: bool = True) -> str:
        while True:
            token = str(uuid4())
            users = await User.loadbyid(db, token=token)
            if not users:
                self.token = token
                await self.toDB(db, commit)
                return self.token

    @staticmethod
    async def get_settings(db: AlcTp, userid, *args, **kwargs):
        users: list[User] = await User.loadbyid(db, rowid=userid)
        out = []
        if users:
            dct: dict = users[0].conf.get('settings', dict()) if users[0].conf else dict()
            for a in args:
                out.append(dct.get(a, kwargs.get(a)))
        return out[0] if len(out) == 1 else out
