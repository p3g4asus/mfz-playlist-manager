
from glob import glob
import logging
import traceback

from os.path import basename, dirname, isfile, join, split, splitext

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import event, select

from common.playlist_alc_ses import Type
from server.db.base import AlchemicBase, AlchemicDB


_LOGGER = logging.getLogger(__name__)

CREATE_DB_IF_NOT_EXIST = [
    '''
    CREATE TABLE IF NOT EXISTS user(
        rowid INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        token TEXT UNIQUE,
        conf TEXT,
        tg TEXT
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS browser(
        rowid INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        user INTEGER NOT NULL,
        sel BOOLEAN NOT NULL DEFAULT 0,
        FOREIGN KEY (user)
            REFERENCES user (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS player(
        rowid INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        user INTEGER NOT NULL,
        sel BOOLEAN NOT NULL DEFAULT 0,
        FOREIGN KEY (user)
            REFERENCES user (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS type(
        rowid INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS playlist(
        rowid INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        user INTEGER NOT NULL,
        type INTEGER NOT NULL,
        dateupdate INTEGER,
        autoupdate INTEGER NOT NULL DEFAULT 0,
        conf TEXT,
        rate REAL,
        playstate TEXT,
        iorder INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (user)
            REFERENCES user (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE,
        FOREIGN KEY (type)
            REFERENCES type (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE,
        UNIQUE(name,user)
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS view_conf(
        rowid INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        playlist INTEGER NOT NULL,
        component INTEGER,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        mime TEXT,
        type INTEGER NOT NULL DEFAULT 0,
        remove BOOLEAN NOT NULL DEFAULT 0,
        UNIQUE(name, playlist, component, type),
        FOREIGN KEY (component)
            REFERENCES playlist_component (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE,
        FOREIGN KEY (playlist)
            REFERENCES playlist (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS playlist_component(
        rowid INTEGER PRIMARY KEY,
        brand TEXT NOT NULL,
        playlist INTEGER NOT NULL,
        parent INTEGER,
        sel BOOLEAN NOT NULL DEFAULT 0,
        title TEXT,
        description TEXT,
        rate REAL,
        filter TEXT,
        conf TEXT,
        FOREIGN KEY (parent)
            REFERENCES playlist_component (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE,
        FOREIGN KEY (playlist)
            REFERENCES playlist (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE,
        UNIQUE(brand, parent, playlist)
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS playlist_item(
        rowid INTEGER PRIMARY KEY,
        title TEXT,
        img TEXT,
        datepub DATETIME,
        link TEXT NOT NULL,
        uid TEXT NOT NULL,
        playlist INTEGER NOT NULL,
        dur INTEGER NOT NULL,
        conf TEXT,
        dl TEXT,
        seen DATETIME,
        iorder INTEGER NOT NULL,
        component INTEGER,
        timeplayed REAL,
        rate REAL,
        UNIQUE(uid, playlist),
        UNIQUE(playlist, iorder),
        FOREIGN KEY (component)
            REFERENCES playlist_component (rowid)
            ON UPDATE CASCADE
            ON DELETE SET NULL,
        FOREIGN KEY (playlist)
            REFERENCES playlist (rowid)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    )
    ''',
    '''
    CREATE INDEX IF NOT EXISTS playlist_item_iorder
        ON playlist_item (iorder)
    '''
]


async def connect_db(args: dict, append):
    create_db = not len(append)
    # db_url = await convert_db1(args)
    db_url = args['dbfile']
    if db_url.endswith('.sqlite') and not db_url.startswith("sqlite://"):
        db_url = "sqlite+aiosqlite:///" + db_url
    engine = create_async_engine(db_url, echo=True)

    def set_sqlite_pragma(dbapi_connection, _connection_record):
        # the sqlite3 driver will not set PRAGMA foreign_keys
        # if autocommit=False; set to True temporarily
        # ac = dbapi_connection.autocommit
        # dbapi_connection.autocommit = True

        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.commit()

        # restore previous autocommit setting
        # dbapi_connection.autocommit = ac
    if db_url.startswith("sqlite"):
        event.listens_for(engine.sync_engine, "connect")(set_sqlite_pragma)
    if create_db:
        async with engine.begin() as conn:
            await conn.run_sync(AlchemicBase.metadata.create_all)
    alc = AlchemicDB(engine)
    processors = dict()
    import importlib
    modules = glob(join(dirname(__file__), "../pls", "*.py*"))
    pls = [splitext(basename(f))[0] for f in modules if isfile(f)]
    types = dict()
    for x in pls:
        if x not in processors:
            try:
                m = importlib.import_module("server.pls." + x)
                cla = getattr(m, "MessageProcessor")
                if cla:
                    dct = dict()
                    for k, v in args.items():
                        if k.startswith(x + '_'):
                            k2 = k[len(x) + 1:]
                            if k2:
                                dct[k2] = v
                        else:
                            dct[k] = v
                    processors[x] = cla(alc, **dct)
                    if x != "common" and create_db:
                        selq = select(Type).where(Type.name == x)
                        out = await AlchemicBase.get_query_result(alc, selq, get_first=True)
                        if not out:
                            out = await alc.upsert(Type(name=x))
                        types[x] = out
            except Exception:
                _LOGGER.warning(traceback.format_exc())
    if create_db:
        await alc.session.flush()
        await alc.commit_and_close_session()
    return alc, processors, types
