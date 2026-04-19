import json
import logging

from sqlalchemy.orm import DeclarativeBase, Mapped
from typing import Annotated, Type, Union, get_args, get_origin

from common.utils import Fieldable, JSONAble, MyEncoder

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql import operators, Select
from sqlalchemy import VARCHAR, Row, String, TypeDecorator, insert


_LOGGER = logging.getLogger(__name__)


class JSONEncodedDict(TypeDecorator):
    impl = VARCHAR

    cache_ok = True

    def coerce_compared_value(self, op, value):
        if op in (operators.like_op, operators.not_like_op):
            return String()
        else:
            return self

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value, cls=MyEncoder)

        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


JSONMutableEncodedDict = MutableDict.as_mutable(JSONEncodedDict)


class AlchemicDB:
    def set_engine(self, engine: AsyncEngine):
        self.engine = engine
        if engine:
            self.sm = async_sessionmaker(engine, expire_on_commit=False)

    def __init__(self, engine: Union["AsyncEngine", "AlchemicDB", None] = None):
        self.sm: async_sessionmaker = None
        if isinstance(engine, AsyncEngine):
            self.set_engine(engine)
        elif isinstance(engine, AlchemicDB):
            self.engine = engine.engine
            self.sm = engine.sm
        else:
            self.engine = None
        self._connection = None
        self._session = None
        self.rv = dict()

    def sk(self, key: str, value: object):
        self.rv[key] = value
        return self

    def __repr__(self):
        return f"AlchemicDB(engine={self.engine}, connection={self._connection}, session={self._session})"

    def __str__(self):
        return self.__repr__()

    def __call__(self):
        return AlchemicDB(self)

    @property
    def connection(self):
        return self._connection

    def is_connected(self):
        return self._connection and not self._connection.closed

    async def close_connection(self):
        if self.is_connected():
            await self._connection.close()
            self._connection = None

    async def close_session(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def commit_and_close_session(self):
        if self._session:
            await self._session.commit()
            await self._session.close()
            self._session = None

    async def initialize_connection(self):
        if not self.is_connected():
            self._connection = await AlchemicDB.get_connection(self.engine)
            if not self._connection.sync_connection:
                self._connection = await self._connection.start()
        return self._connection

    @property
    def session(self):
        return self.initialize_session()

    async def commit_connection(self):
        if self.is_connected():
            await self._connection.commit()

    async def commit_session(self):
        if self._session:
            await self._session.commit()

    async def commit(self):
        await self.commit_session()
        await self.commit_connection()

    async def upsert(self, obj: Type["AlchemicBase"], keys: str = 'rowid') -> "AlchemicBase":
        if not keys or not getattr(obj, keys, None):
            insq = insert(obj.__class__).values(**obj.get_update_dict()).returning(obj.__class__)
            obj = (await self.session.execute(insq)).scalar()
        else:
            obj = await self.session.merge(obj)
        return obj

    async def dispose(self):
        await self.close_session()
        await self.close_connection()
        if self.engine:
            await self.engine.dispose()
            self.engine = None

    def initialize_session(self):
        if not self._session:
            self._session = self.sm()
        return self._session

    async def initialize(self, engine: AsyncEngine | None = None):
        if engine:
            if self.engine and self.engine is not engine:
                await self.dispose()
            self.set_engine(engine)
        await self.initialize_connection()
        self.initialize_session()

    @staticmethod
    async def get_connection(engine: "AlcTp") -> AsyncConnection:
        if isinstance(engine, AsyncConnection):
            return engine if engine.sync_connection else await engine.start()
        elif isinstance(engine, AsyncSession):
            engine = engine.get_bind()
        elif isinstance(engine, AlchemicDB):
            return engine.connection if engine.is_connected() else await engine.initialize_connection()
        return await engine.connect()

    @staticmethod
    def get_session(engine: "AlcTp") -> AsyncSession:
        if isinstance(engine, AsyncSession):
            return engine
        elif isinstance(engine, AlchemicDB):
            return engine.session
        else:
            if isinstance(engine, AsyncConnection):
                engine = engine.engine
            async_session = async_sessionmaker(engine, expire_on_commit=False)
            return async_session()


class UsesAlchemicDB:

    def __init__(self, func):
        self.func = func

    async def __call__(self, *args, **kwargs):
        db = None
        if 'db' not in kwargs and \
           ((db := getattr(args[0], "db", None))
            or ((mo := getattr(args[0], "app", None)) and (mo := getattr(mo, "p", None)) and (db := getattr(mo, "db", None)))
            or ((mo := getattr(args[0], "params", None)) and (db := getattr(mo, "db2", None)))) and \
           isinstance(db, AlchemicDB):
            kwargs['db'] = (db := db())
        try:
            result = await self.func(*args, **kwargs)
        except SQLAlchemyError as e:
            _LOGGER.error(f"Database error: {e}")
            if '_err' in db.rv:
                return db.rv['_err']
            else:
                raise
        finally:
            if db:
                await db.close_session()
        return result

    def __get__(self, instance, owner):
        from functools import partial
        return partial(self.__call__, instance)


class AlchemicBase(DeclarativeBase, Fieldable, JSONAble):
    type_annotation_map = {
        dict: JSONMutableEncodedDict,
    }

    def get_mapped_field(self, nm: str, ann: Type) -> tuple[bool, object]:
        if (orig := get_origin(ann)) is Mapped or (orig is Annotated and (aargs := get_args(ann)) and get_origin(aargs[0]) is Mapped):
            return True, getattr(self, nm)
        else:
            return False, None

    def get_all_mapped_fields(self, mapped_fields: dict = None) -> dict:
        for nm, ann in self.__annotations__.items():
            if (mf := self.get_mapped_field(nm, ann))[0] and mapped_fields is not None:
                mapped_fields[nm] = mf[1]
        return mapped_fields

    @staticmethod
    def get_deep_copy(it: object, objmap: dict) -> object:
        if isinstance(it, dict):
            return {k: AlchemicBase.get_deep_copy(v, objmap) for k, v in it.items()}
        elif isinstance(it, list):
            return [AlchemicBase.get_deep_copy(v, objmap) for v in it]
        elif isinstance(it, tuple):
            return tuple(AlchemicBase.get_deep_copy(v, objmap) for v in it)
        elif isinstance(it, set):
            return {AlchemicBase.get_deep_copy(v, objmap) for v in it}
        elif isinstance(it, AlchemicBase):
            if id(it) in objmap:
                return objmap[id(it)]
            else:
                kwargs = dict()
                for nm, ann in it.__annotations__.items():
                    if (mf := it.get_mapped_field(nm, ann))[0]:
                        kwargs[nm] = AlchemicBase.get_deep_copy(mf[1], objmap)
                rv = it.__class__(**kwargs)
                objmap[id(it)] = rv
            return rv
        else:
            return it

    def __init__(self, *args, **kwargs):
        if (cp := kwargs.get('_cp')) and isinstance(cp, self.__class__):
            objmap = dict()
            objmap[id(cp)] = self
            for nm, ann in self.__annotations__.items():
                if (mf := cp.get_mapped_field(nm, ann))[0]:
                    kwargs[nm] = AlchemicBase.get_deep_copy(mf[1], objmap)
            del kwargs['_cp']
        self.registry.constructor(self, *args, **kwargs)

    def cp(self, **kwargs):
        if (cp := kwargs.get('_cp')) and isinstance(cp, self.__class__):
            objmap = dict()
            objmap[id(cp)] = self
            for nm, ann in self.__annotations__.items():
                if (mf := cp.get_mapped_field(nm, ann))[0]:
                    setattr(self, nm, AlchemicBase.get_deep_copy(mf[1], objmap))
        else:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def get_update_dict(self):
        varskeys = []
        for nm, ann in self.__annotations__.items():
            if get_origin(ann) is Annotated:
                args = get_args(ann)
                if len(args) > 1 and 'U' in args[1]:
                    varskeys.append(nm)
        return {key: getattr(self, key) for key in varskeys if hasattr(self, key)}

    def toJSON(self, **kwargs) -> dict:
        varskeys = []
        for nm, ann in self.__annotations__.items():
            if get_origin(ann) is Annotated:
                args = get_args(ann)
                if len(args) > 1 and 'J' in args[1]:
                    varskeys.append(nm)
        dcts = vars(self)
        dctd = dict()
        for key in varskeys:
            if key in dcts and dcts[key] is not None:  # optimization for javascript/json serialization, skip None values
                if isinstance(dcts[key], dict):
                    dd = dctd[key] = dict()
                    for k, v in dcts[key].items():
                        if v is not None:  # optimization for javascript/json serialization, skip None values
                            dd[k] = v
                else:
                    dctd[key] = dcts[key]

        # del dct['typei']
        # del dct['useri']
        return dctd

    @staticmethod
    async def _query_and_field(engine: "AlcTp", pssel: Select, fieldname: str, commit: bool = False):
        out = -1

        async def run_query(conn, pssel, commit):
            result = await conn.execute(pssel)
            out = getattr(result, fieldname, -1)
            if isinstance(out, (tuple, list, Row)) and len(out):
                out = out[0]
            elif not isinstance(out, int):
                out = -2
            if commit and out > 0:
                await conn.commit()
            return out
        if isinstance(engine, (AsyncConnection, AlchemicDB)):
            conn = await AlchemicDB.get_connection(engine)
            out = await run_query(conn, pssel, commit)
        else:
            async with AlchemicDB.get_connection(engine) as conn:
                out = await run_query(conn, pssel, commit)
                await conn.close()
        return out

    @staticmethod
    async def _get_query_result(session: AsyncSession, plsel: Select, get_first: bool = False):
        _LOGGER.debug(f"Executing query {plsel}")
        sr = await session.execute(plsel)
        if get_first:
            out = sr.scalars().first()
        else:
            out = sr.scalars().all()
        return out

    @staticmethod
    async def query_and_rowcount(engine: "AlcTp", pssel: Select, commit: bool = False):
        return await AlchemicBase._query_and_field(engine, pssel, 'rowcount', commit)

    @staticmethod
    async def query_and_rowid(engine: "AlcTp", pssel: Select, commit: bool = False):
        ipk = await AlchemicBase._query_and_field(engine, pssel, 'inserted_primary_key', commit)
        return ipk[0] if ipk and isinstance(ipk, (list, tuple, Row)) and len(ipk) > 0 else ipk if isinstance(ipk, int) else -3

    @staticmethod
    async def get_query_result(engine: "AlcTp", plsel: Select, get_first: bool = False, commit: bool = False) -> Union[list, "AlchemicBase"]:
        out = None
        if isinstance(engine, (AsyncEngine, AsyncConnection)):
            async with AlchemicDB.get_session(engine) as session, session.begin():
                out = await AlchemicBase._get_query_result(session, plsel, get_first)
                if commit:
                    await session.commit()
        elif isinstance(engine, (AsyncSession, AlchemicDB)):
            if isinstance(engine, AlchemicDB):
                engine = engine.session
            out = await AlchemicBase._get_query_result(engine, plsel, get_first)
            if commit:
                await engine.commit()
        return out


AlcTp = Union[AsyncEngine, AsyncSession, AsyncConnection, AlchemicDB]
