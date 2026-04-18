import logging
import urllib.parse
from datetime import datetime
from os import remove
from typing import Annotated, Dict, Iterable

from sqlalchemy import (ForeignKey, UniqueConstraint, and_, delete, func, inspect,
                        or_, select, update)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.orm import (Mapped, attribute_keyed_dict, joinedload, make_transient, mapped_column, noload,
                            relationship, subqueryload)

from common.const import (LINK_CONV_BIRD_REDIRECT, LINK_CONV_MASK,
                          LINK_CONV_OPTION_SHIFT, LINK_CONV_OPTION_VIDEO_EMBED,
                          LINK_CONV_REDIRECT, LINK_CONV_TWITCH,
                          LINK_CONV_UNTOUCH, LINK_CONV_YTDL_DICT,
                          LINK_CONV_YTDL_REDIRECT)
from common.user_alc_ses import User
from common.utils import Fieldable, JSONAble
from server.db.base import AlchemicBase, AlchemicDB, AlcTp
from sqlalchemy.util.concurrency import greenlet_spawn

_LOGGER = logging.getLogger(__name__)


class Type(AlchemicBase):
    __tablename__ = "type"
    rowid: Annotated[Mapped[int], 'J'] = mapped_column(primary_key=True, autoincrement=True)
    name: Annotated[Mapped[str], 'JU'] = mapped_column(unique=True)


class PlaylistComponent(AlchemicBase):
    __tablename__ = "playlist_component"
    rowid: Annotated[Mapped[int], 'JU'] = mapped_column(primary_key=True, autoincrement=True)
    playlisti: Annotated[Mapped[int], 'JU'] = mapped_column('playlist', ForeignKey("playlist.rowid", ondelete="CASCADE"), nullable=False)
    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="components")
    brand: Annotated[Mapped[str], 'JU'] = mapped_column(nullable=False)
    parenti: Annotated[Mapped[int], 'JU'] = mapped_column('parent', ForeignKey("playlist_component.rowid"), nullable=True)
    parent: Mapped["PlaylistComponent"] = relationship("PlaylistComponent", remote_side=[rowid], lazy="joined", join_depth=1)
    sel: Annotated[Mapped[bool], 'JU'] = mapped_column(nullable=False, default=False)
    rate: Annotated[Mapped[float], 'JU'] = mapped_column()
    title: Annotated[Mapped[str], 'JU'] = mapped_column()
    description: Annotated[Mapped[str], 'JU'] = mapped_column()
    filter: Annotated[Mapped[dict], 'JU'] = mapped_column()
    conf: Annotated[Mapped[dict], 'JU'] = mapped_column()
    views: Mapped[Dict[str, "ViewConf"]] = relationship("ViewConf", cascade="all, delete-orphan", back_populates="component", passive_deletes=True, lazy='selectin', collection_class=attribute_keyed_dict("hash"))
    __table_args__ = (UniqueConstraint('brand', 'playlist', 'parent', name='uix_brand_playlist_parent'),)

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
                if key == 'playlist' and isinstance(val, dict):
                    kwargs['playlist'] = Playlist(dbitem=val)
                elif key == 'parent' and isinstance(val, dict):
                    kwargs['parent'] = PlaylistComponent(dbitem=val)
                elif key == 'views' and isinstance(val, dict):
                    kwargs['views'] = {vk: ViewConf(dbitem=vv) if isinstance(vv, dict) else vv for vk, vv in val.items()}
                else:
                    kwargs[key] = val
            del kwargs['dbitem']
        super().__init__(*args, **kwargs)

    def __eq__(self, other):
        if not isinstance(other, PlaylistComponent):
            return False
        elif self.rowid and other.rowid:
            return self.rowid == other.rowid
        return (self.playlisti, self.brand, self.parenti) == (other.playlisti, other.brand, other.parenti)


class ViewConf(AlchemicBase):
    VIEW_CONF_TYPE_DEFAULT = 1
    VIEW_CONF_TYPE_DOWNLOAD = 2
    __tablename__ = "view_conf"
    rowid: Annotated[Mapped[int], 'JU'] = mapped_column(primary_key=True, autoincrement=True)
    name: Annotated[Mapped[str], 'JU'] = mapped_column(nullable=False)
    playlisti: Annotated[Mapped[int], 'JU'] = mapped_column('playlist', ForeignKey("playlist.rowid", ondelete="CASCADE"), nullable=False)
    playlist: Mapped["Playlist"] = relationship("Playlist", lazy='joined', back_populates="views")
    componenti: Annotated[Mapped[int], 'JU'] = mapped_column('component', ForeignKey("playlist_component.rowid", ondelete="CASCADE"), nullable=True)
    component: Mapped["PlaylistComponent"] = relationship("PlaylistComponent", lazy='joined', back_populates="views")
    width: Annotated[Mapped[int], 'JU'] = mapped_column(nullable=False)
    height: Annotated[Mapped[int], 'JU'] = mapped_column(nullable=False)
    mime: Annotated[Mapped[str], 'JU'] = mapped_column(nullable=True)
    type: Annotated[Mapped[int], 'JU'] = mapped_column(nullable=False, default=0)
    remove: Annotated[Mapped[bool], 'JU'] = mapped_column(nullable=False, default=False)
    __table_args__ = (UniqueConstraint('name', 'playlist', 'component', 'type', name='uix_name_playlist_component_type'),)

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
                if key == 'playlist' and isinstance(val, dict):
                    kwargs['playlist'] = Playlist(dbitem=val)
                elif key == 'component' and isinstance(val, dict):
                    kwargs['component'] = PlaylistComponent(dbitem=val)
                else:
                    kwargs[key] = val
            del kwargs['dbitem']
        super().__init__(*args, **kwargs)

    @property
    def hash(self):
        defa = 1 if self.type & ViewConf.VIEW_CONF_TYPE_DEFAULT else 0
        comp = -1 if defa or self.componenti is None else self.componenti
        return f"{self.name}|{self.playlisti}|{comp}|{defa}|{1 if self.type&ViewConf.VIEW_CONF_TYPE_DOWNLOAD else 0}"


LOAD_ITEMS_NO = 0
LOAD_ITEMS_ALL = 1
LOAD_ITEMS_UNSEEN = 2
LOAD_ITEMS_SEEN = 3


class Playlist(AlchemicBase):
    __tablename__ = "playlist"
    rowid: Annotated[Mapped[int], 'JU'] = mapped_column(primary_key=True, autoincrement=True)
    components: Annotated[Mapped[list["PlaylistComponent"]], 'J'] = relationship("PlaylistComponent", cascade="all, delete-orphan", back_populates="playlist", passive_deletes=True, lazy='selectin')
    views: Annotated[Mapped[Dict[str, "ViewConf"]], 'J'] = relationship("ViewConf", cascade="all, delete-orphan", back_populates="playlist", passive_deletes=True, lazy='selectin', collection_class=attribute_keyed_dict("hash"))
    name: Annotated[Mapped[str], 'JU'] = mapped_column()
    typei: Annotated[Mapped[int], 'JU'] = mapped_column('type', ForeignKey("type.rowid"), nullable=False)
    type: Annotated[Mapped["Type"], 'J'] = relationship("Type", lazy="joined")
    useri: Annotated[Mapped[int], 'JU'] = mapped_column('user', ForeignKey("user.rowid"), nullable=False)
    user: Annotated[Mapped["User"], 'J'] = relationship("User", lazy="joined")
    conf: Annotated[Mapped[dict], 'JU'] = mapped_column()
    rate: Annotated[Mapped[float], 'JU'] = mapped_column()
    playstate: Annotated[Mapped[str], 'JU'] = mapped_column()
    iorder: Annotated[Mapped[int], 'JU'] = mapped_column(nullable=False, default=0)
    items: Annotated[Mapped[list["PlaylistItem"]], 'J'] = relationship("PlaylistItem", cascade="all, delete-orphan", back_populates="playlist", passive_deletes=True, lazy='selectin')
    dateupdate: Annotated[Mapped[int], 'JU'] = mapped_column()
    autoupdate: Annotated[Mapped[bool], 'JU'] = mapped_column()

    __table_args__ = (UniqueConstraint("name", "user", name="name_useri_key"),)

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
                if key == 'type':
                    kwargs['type'] = Type(**val)
                elif key == 'user' and isinstance(val, dict):
                    kwargs['user'] = User(**val)
                elif key == 'components' and isinstance(val, list):
                    kwargs['components'] = [PlaylistComponent(dbitem=v) if isinstance(v, dict) else v for v in val]
                elif key == 'views' and isinstance(val, dict):
                    kwargs['views'] = {vk: ViewConf(dbitem=vv) if isinstance(vv, dict) else vv for vk, vv in val.items()}
                elif key == 'items' and isinstance(val, list):
                    kwargs['items'] = [PlaylistItem(dbitem=v) if isinstance(v, dict) else v for v in val]
                else:
                    kwargs[key] = val
            del kwargs['dbitem']
        super().__init__(*args, **kwargs)

    def toM3U(self, host, conv, token=None):
        s = "#EXTM3U\n"
        for i in self.items:
            if not i.seen:
                s += i.toM3U(host, conv, token=token)
        return s

    @staticmethod
    async def loadbyid(engine: AlcTp, rowid=None, useri=None, name=None, username=None, loaditems=LOAD_ITEMS_UNSEEN, sort_item_field='iorder', offset=None, limit=None) -> list["Playlist"]:
        plsel = select(Playlist)
        if loaditems == LOAD_ITEMS_NO:
            plsel = plsel.options(noload(Playlist.items))
        elif loaditems == LOAD_ITEMS_UNSEEN:
            plsel = plsel.options(subqueryload(Playlist.items.and_(PlaylistItem.seen.is_(None))))
        elif loaditems == LOAD_ITEMS_SEEN:
            plsel = plsel.options(subqueryload(Playlist.items.and_(PlaylistItem.seen.is_not(None))))
        andargs = []
        if isinstance(rowid, int):
            andargs.append(Playlist.rowid == rowid)
        if isinstance(useri, int):
            andargs.append(Playlist.useri == useri)
        if isinstance(name, str) and len(name):
            andargs.append(Playlist.name == name)
        if isinstance(username, str) and len(username):
            # andargs.append(User.username == username)
            plsel = plsel.options(joinedload(Playlist.user.and_(User.username == username)))
        plsel = plsel.where(and_(*andargs)).order_by(Playlist.iorder, Playlist.rowid)

        out = await AlchemicBase.get_query_result(engine, plsel)
        # out = await greenlet_spawn(Playlist._dont_be_lazy, out)
        if loaditems != LOAD_ITEMS_NO:
            def sort_items(out: list["Playlist"], sort_item_field: str, offset: int, limit: int):
                for pl in out:
                    pl.items.sort(key=lambda x: getattr(x, sort_item_field) if hasattr(x, sort_item_field) else 0)
                    if offset is not None and limit is not None:
                        pl.items = pl.items[offset:offset + limit]
            await greenlet_spawn(sort_items, out, sort_item_field, offset, limit)
        return out

    @staticmethod
    async def test_db(dbfile: str, **kwargs):
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine("sqlite+aiosqlite:///" + dbfile, echo=True)
        uss = await Playlist.loadbyid(engine, **kwargs)
        return uss

    async def delete(self, db: AlcTp, commit=True):
        if self.rowid:
            delq = delete(Playlist).where(Playlist.rowid == self.rowid)
            await db.session.delete(self)
            if commit:
                await db.session.commit()
        elif self.name and (self.useri or self.user):
            if self.useri is None:
                self.useri = self.user.rowid
            if self.useri:
                delq = delete(Playlist).where(Playlist.name == self.name, Playlist.useri == self.useri)
                await db.session.execute(delq)
                if commit:
                    await db.session.commit()
        return True

    @staticmethod
    async def reset_index(db: AlcTp, useri=None, commit=True):
        pls = await Playlist.loadbyid(db, None, useri=useri, loaditems=LOAD_ITEMS_NO)
        for i, pl in enumerate(pls):
            pl.iorder = i + 1
            await pl.toDB(db, commit=False)
        if commit:
            await db.commit()
        if not isinstance(db, (AsyncConnection, AlchemicDB)):
            await db.close()

    def isOk(self):
        return self.typei and self.useri and self.name

    def __eq__(self, other):
        if self.rowid is not None and other.rowid is not None:
            return self.rowid == other.rowid
        elif self.rowid is None and other.rowid is None:
            return ((self.useri and self.useri == other.useri)
                    or (self.user and other.user and self.user.name and other.user.name and self.user.name == other.user.name)) and self.name == other.name
        else:
            return False

    async def fix_iorder(self, db: AlcTp, commit=True):
        # faccio cosi per problemi vari con sqlalchemy
        # (a volte fallisce il vincolo di unicità, a volte fallisce il reflect delle modifiche del db sugli oggetti)
        if 1:
            updateq = update(PlaylistItem).where(PlaylistItem.playlisti == self.rowid).values(iorder=func.abs(PlaylistItem.iorder))
            await db.session.execute(updateq)
        elif 2:
            with db.session.no_autoflush:
                for it in self.items:
                    if isinstance(it.iorder, int):
                        it.iorder = abs(it.iorder)
                        await db.session.flush()
        else:
            for it in self.items:
                make_transient(it)
                if isinstance(it.iorder, int):
                    it.iorder = abs(it.iorder)
            updateq = update(PlaylistItem).where(PlaylistItem.playlisti == self.rowid).values(iorder=func.abs(PlaylistItem.iorder))
            await db.session.execute(updateq)
        if commit:
            await db.commit_session()
        rv = self.rowid is not None
        _LOGGER.debug(f"Fix iorder rv = {rv}")
        return rv

    async def clear(self, db: AlcTp, commit=True):
        rv = False
        if self.rowid:
            updateq = update(PlaylistItem).where(and_(PlaylistItem.playlisti == self.rowid, PlaylistItem.seen.is_(None))).values(seen=func.now())
            await db.session.execute(updateq)
            if commit:
                await db.session.commit()
            rv = True
        return rv

    async def cleanItems(self, db: AlcTp, datelimit, commit=True):
        items = self.items
        rv = True
        for idx in range(len(items) - 1, -1, -1):
            other_it = items[idx]
            rvn = True
            if not other_it.isOk() and other_it.playlisti is not None:
                rvn = await other_it.delete(db, commit=False)
                del items[idx]
            elif other_it.seen:
                dp = datetime.strptime(other_it.seen, '%Y-%m-%d %H:%M:%S') if isinstance(other_it.seen, str) else other_it.seen
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

    @staticmethod
    def _dont_be_lazy(it: "Playlist" | Iterable["Playlist"]) -> "Playlist" | Iterable["Playlist"]:
        if isinstance(it, Iterable):
            for item in it:
                Playlist._dont_be_lazy(item)
        else:
            if it.components:
                pass
            if it.user:
                pass
            PlaylistItem._dont_be_lazy(it.items)
        return it

    async def toDB(self, db: AlcTp, commit: bool = True):
        rv = None
        if self.typei is None:
            self.typei = self.type.rowid
        if self.useri is None:
            self.useri = self.user.rowid
        if self.isOk():
            rv = self
            if self.rowid:
                cnt = select(func.count(Playlist.rowid)).where(and_(Playlist.name == self.name, Playlist.useri == self.useri, Playlist.rowid != self.rowid))
                out = await AlchemicBase.get_query_result(db, cnt, get_first=True)
                if out:
                    return None
                if (stt := inspect(self)).transient or stt.detached:
                    rv = await db.upsert(self)
            else:
                if not inspect(self).transient:
                    make_transient(self)
                cnt = select(func.count(Playlist.rowid)).where(and_(Playlist.name == self.name, Playlist.useri == self.useri))
                out = await AlchemicBase.get_query_result(db, cnt, get_first=True)
                if out:
                    return None
                maxorder = select(func.max(Playlist.iorder)).where(Playlist.useri == self.useri)
                out = await AlchemicBase.get_query_result(db, maxorder, get_first=True)
                self.iorder = (out if out else 0) + 1
                rv = await db.upsert(self)
                await greenlet_spawn(Playlist._dont_be_lazy, self)
            if commit:
                await db.session.commit()
        return rv

    def get_duration(self, seen=False):
        dur = 0
        for i in self.items:
            if seen or not i.seen:
                dur += i.dur
        return dur


class PlaylistItem(AlchemicBase):
    __tablename__ = "playlist_item"
    rowid: Annotated[Mapped[int], 'JU'] = mapped_column(primary_key=True, autoincrement=True)
    uid: Annotated[Mapped[str], 'JU'] = mapped_column(nullable=False)
    link: Annotated[Mapped[str], 'JU'] = mapped_column(nullable=False)
    title: Annotated[Mapped[str], 'JU'] = mapped_column()
    playlisti: Annotated[Mapped[int], 'JU'] = mapped_column('playlist', ForeignKey("playlist.rowid", ondelete="CASCADE"), nullable=False)
    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="items", lazy="joined")
    conf: Annotated[Mapped[dict], 'JU'] = mapped_column()
    datepub: Annotated[Mapped[datetime], 'JU'] = mapped_column()
    img: Annotated[Mapped[str], 'JU'] = mapped_column()
    dur: Annotated[Mapped[int], 'JU'] = mapped_column()
    seen: Annotated[Mapped[datetime], 'JU'] = mapped_column()
    iorder: Annotated[Mapped[int], 'JU'] = mapped_column(nullable=False)
    dl: Annotated[Mapped[str], 'JU'] = mapped_column()
    componenti: Annotated[Mapped[int], 'JU'] = mapped_column('component', ForeignKey("playlist_component.rowid"), nullable=True)
    component: Mapped["PlaylistComponent"] = relationship("PlaylistComponent", lazy="joined")
    timeplayed: Annotated[Mapped[float], 'JU'] = mapped_column()
    rate: Annotated[Mapped[float], 'JU'] = mapped_column()
    __table_args__ = (UniqueConstraint("playlist", "iorder", name="playlist_iorder_key"),
                      UniqueConstraint("uid", "playlist", name="uid_playlist_key"),)

    def __eq__(self, other):
        if self.rowid is not None and other.rowid is not None:
            return self.rowid == other.rowid
        else:
            return self.uid and self.uid == other.uid and\
                self.playlisti == other.playlisti and self.playlisti

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
                if key == 'playlist' and isinstance(val, dict):
                    kwargs['playlist'] = Playlist(dbitem=val)
                elif key == 'component' and isinstance(val, dict):
                    kwargs['component'] = PlaylistComponent(dbitem=val)
                elif key == 'ratec':
                    self.ratec = val
                else:
                    kwargs[key] = val
            del kwargs['dbitem']
        super().__init__(*args, **kwargs)

    @staticmethod
    def convert_img_url(thumb, host, idx=0):
        thumb = thumb.split('|')
        thumb = thumb[idx if idx < len(thumb) else 0]
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
        dct = super().toJSON(**kwargs)
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
    async def loadbyid(engine: AlcTp, rowid, playlist=None, loaditems=LOAD_ITEMS_UNSEEN, sortby='iorder', offset=None, limit=None, user=None, dl=None):
        plisel = select(PlaylistItem)
        andargs = []
        if isinstance(rowid, int):
            andargs.append(PlaylistItem.rowid == rowid)
            listresult = False
        elif not isinstance(playlist, int):
            return None
        else:
            andargs.append(PlaylistItem.playlisti == playlist)
            if loaditems == LOAD_ITEMS_UNSEEN:
                andargs.append(PlaylistItem.seen.is_(None))
                andargs.append(PlaylistItem.link.is_not_(None))
            elif loaditems == LOAD_ITEMS_SEEN:
                andargs.append(PlaylistItem.seen.is_not_(None))
            listresult = True
        if dl:
            andargs.append(or_(PlaylistItem.dl.is_not(None), and_(PlaylistItem.conf.is_not(None), func.instr(PlaylistItem.conf, '"todel"') > 0)))
        if user:
            plisel = plisel.join(Playlist).join(User).where(User.username == user)
        plisel = plisel.where(and_(*andargs)).order_by(getattr(PlaylistItem, sortby))
        if limit is not None and offset is not None:
            plisel = plisel.offset(offset).limit(limit)
        return await AlchemicBase.get_query_result(engine, plisel, get_first=not listresult)

    async def setSeen(self, db: AlcTp, value=True, commit=True, previous=False):
        rv = False
        if self.rowid:
            if not previous:
                self.seen = datetime.now() if value else None
            else:
                updateq = update(PlaylistItem).where(and_(PlaylistItem.playlisti == self.playlisti, PlaylistItem.iorder <= self.iorder, PlaylistItem.seen.is_(None) if value else PlaylistItem.seen.is_not(None))).values(seen=func.now() if value else None)
                await db.session.execute(updateq)
            if commit:
                await db.session.commit()
            rv = True
        return rv

    async def setIOrder(self, db: AlcTp, iorder, commit=True):
        rv = False
        if self.rowid:
            self.iorder = iorder
            if commit:
                await db.session.commit()
            rv = True
        return rv

    def toM3U(self, host, conv, token=None):
        return "#EXTINF:0,%s\n%s\n" % (self.title if self.title else "N/A", self.get_conv_link(host, conv, token=token))

    async def isPresent(self, db: AsyncEngine | AsyncSession):
        if not self.playlisti or not self.uid:
            return False
        else:
            selq = select(func.count(PlaylistItem.rowid)).where(and_(PlaylistItem.uid == self.uid, PlaylistItem.playlisti == self.playlisti))
            return await AlchemicBase.get_query_result(db, selq, get_first=True) > 0

    def takes_space(self):
        return self.dl or (self.conf and 'todel' in self.conf and self.conf['todel'])

    async def clean(self, db: AlcTp = None, commit=True):
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
            await self.toDB(db, commit=commit)
        return todel

    async def delete(self, db: AlcTp, commit=True):
        rv = False
        should_check = True
        delq = None
        if self.rowid:
            await db.session.delete(self)
            rv = True
        elif self.uid and self.playlisti:
            delq = delete(PlaylistItem).where(and_(PlaylistItem.uid == self.uid, PlaylistItem.playlisti == self.playlisti))
        elif self.playlisti:
            delq = delete(PlaylistItem).where(PlaylistItem.playlisti == self.playlisti)
        else:
            should_check = False
        if delq:
            await db.session.execute(delq)
            rv = True
        if should_check:
            await self.clean(db, commit=commit)
            if commit:
                await db.session.commit()
        return rv

    def isOk(self):
        return self.link and self.uid and self.playlisti

    async def move_to(self, playlist, db: AlcTp, commit=True):
        if playlist != self.playlisti:
            await self.setSeen(db, commit=commit)
            self.rowid = None
            self.playlisti = playlist
        self.seen = None
        self.iorder = None
        return await self.toDB(db, commit=commit)

    async def move_to_end(self, db: AlcTp, commit=True):
        return await self.move_to(self.playlisti, db, commit=commit)

    @staticmethod
    def _dont_be_lazy(it: "PlaylistItem" | Iterable["PlaylistItem"]) -> "PlaylistItem" | Iterable["PlaylistItem"]:
        if isinstance(it, Iterable):
            for item in it:
                PlaylistItem._dont_be_lazy(item)
        else:
            if it.component:
                if it.component.parent:
                    pass
            if it.playlist:
                pass
        return it

    async def toDB(self, db: AlcTp, commit: bool = True):
        rv = None
        if self.isOk():
            rv = self
            if self.rowid is None and not inspect(self).transient:
                make_transient(self)
            if self.iorder is None:
                maxv = select(func.max(PlaylistItem.iorder)).where(PlaylistItem.playlisti == self.playlisti)
                out = await AlchemicBase.get_query_result(db, maxv, get_first=True)
                self.iorder = (out if out else 0) + 10
            if (self.rowid and ((stt := inspect(self)).transient or stt.detached)) or self.rowid is None:
                rv = await db.upsert(self)

                await greenlet_spawn(PlaylistItem._dont_be_lazy, self)
                # await db.session.execute(update(PlaylistItem), [self.get_update_dict()])
            if commit:
                await db.session.commit()
        return rv


class PlaylistMessage(JSONAble, Fieldable):
    PING_STATUS = 'send_status_with_ping'
    PING_STATUS_CONS = '__c'
    PING_DELAY = '__d'

    def get(self, key, default=None):
        return getattr(self, key) if hasattr(self, key) else default

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
