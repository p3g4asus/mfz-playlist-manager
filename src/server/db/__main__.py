
import argparse
import asyncio
import logging


from os.path import join, split

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.schema import CreateTable
from sqlalchemy import MetaData, select, text


_LOGGER = logging.getLogger(__name__)
TABLE_ORDER = [
    "type",
    "user",
    "playlist",
    "browser",
    "player",
    "playlist_component",
    "playlist_item",
    "view_conf"
]

DEST_SCHEMA = """\
CREATE TABLE type (
        rowid BIGINT AUTO_INCREMENT,
        name TEXT NOT NULL,
        PRIMARY KEY (rowid),
        UNIQUE (name)
);
CREATE TABLE user (
        rowid BIGINT AUTO_INCREMENT,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        tg TEXT,
        conf TEXT,
        token TEXT,
        PRIMARY KEY (rowid),
        UNIQUE (username),
        UNIQUE (token)
);
CREATE TABLE playlist (
        rowid BIGINT AUTO_INCREMENT,
        name TEXT NOT NULL,
        user BIGINT NOT NULL,
        type BIGINT NOT NULL,
        conf TEXT,
        dateupdate BIGINT,
        autoupdate INTEGER DEFAULT '0' NOT NULL,
        iorder BIGINT DEFAULT 0 NOT NULL,
        rate REAL,
        playstate TEXT,
        PRIMARY KEY (rowid),
        FOREIGN KEY(user) REFERENCES user (rowid) ON UPDATE CASCADE ON DELETE CASCADE,
        FOREIGN KEY(type) REFERENCES type (rowid) ON UPDATE CASCADE ON DELETE CASCADE,
        UNIQUE (name, user),
        UNIQUE (iorder, user)
);
CREATE TABLE browser (
        rowid BIGINT AUTO_INCREMENT,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        user BIGINT NOT NULL,
        sel BOOLEAN DEFAULT 0 NOT NULL,
        PRIMARY KEY (rowid),
        FOREIGN KEY(user) REFERENCES user (rowid)
            ON UPDATE CASCADE ON DELETE CASCADE,
        UNIQUE (name, user)
);
CREATE TABLE player (
        rowid BIGINT AUTO_INCREMENT,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        user BIGINT NOT NULL,
        sel BOOLEAN DEFAULT 0 NOT NULL,
        PRIMARY KEY (rowid),
        FOREIGN KEY(user) REFERENCES user (rowid)
            ON UPDATE CASCADE ON DELETE CASCADE,
        UNIQUE (name, user)
);
CREATE TABLE playlist_component (
        rowid BIGINT AUTO_INCREMENT,
        brand TEXT NOT NULL,
        playlist BIGINT NOT NULL,
        parent BIGINT,
        sel BOOLEAN DEFAULT 0 NOT NULL,
        title TEXT,
        description TEXT,
        rate REAL,
        filter TEXT,
        conf TEXT,
        PRIMARY KEY (rowid),
        FOREIGN KEY(playlist) REFERENCES playlist (rowid)
            ON UPDATE CASCADE ON DELETE CASCADE,
        FOREIGN KEY(parent) REFERENCES playlist_component (rowid)
            ON UPDATE CASCADE ON DELETE CASCADE,
        UNIQUE (brand, parent, playlist)
);
CREATE TABLE playlist_item (
        rowid BIGINT AUTO_INCREMENT,
        title TEXT,
        img TEXT,
        datepub DATETIME,
        link TEXT NOT NULL,
        uid TEXT NOT NULL,
        playlist BIGINT NOT NULL,
        dur INTEGER NOT NULL,
        conf TEXT,
        iorder INTEGER NOT NULL,
        dl TEXT,
        seen DATETIME,
        timeplayed REAL,
        component BIGINT,
        rate REAL,
        PRIMARY KEY (rowid),
        FOREIGN KEY(playlist) REFERENCES playlist (rowid) ON DELETE CASCADE ON UPDATE CASCADE,
        FOREIGN KEY(component) REFERENCES playlist_component (rowid) ON UPDATE CASCADE ON DELETE SET NULL,
        UNIQUE (uid, playlist),
        UNIQUE (playlist, iorder)
);
CREATE TABLE view_conf (
        rowid BIGINT AUTO_INCREMENT,
        name TEXT NOT NULL,
        playlist BIGINT NOT NULL,
        component BIGINT,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        mime TEXT,
        type INTEGER DEFAULT 0 NOT NULL,
        remove BOOLEAN DEFAULT 0 NOT NULL,
        PRIMARY KEY (rowid),
        FOREIGN KEY(playlist) REFERENCES playlist (rowid) ON UPDATE CASCADE ON DELETE CASCADE,
        FOREIGN KEY(component) REFERENCES playlist_component (rowid) ON UPDATE CASCADE ON DELETE CASCADE,
        UNIQUE (name, playlist, component, type)
);
"""


async def convert_db1(args):
    import json
    import shutil
    import aiosqlite
    from common.olddb.user import User
    from common.const import DOWNLOADED_SUFFIX
    from common.olddb.playlist import LOAD_ITEMS_ALL, Playlist
    src = args['dbfile']
    dst = join(split(src)[0], 'dbconv.sqlite') if 'to' not in args else args['to']
    shutil.copyfile(src, dst)
    db = await aiosqlite.connect(dst)
    db.row_factory = aiosqlite.Row
    # convert old db to new one if needed
    try:
        await db.execute("SELECT * FROM playlist_component")
    except aiosqlite.OperationalError:
        qc = '''
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
            '''
        await db.execute(qc),
        qc = '''
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
            '''
        await db.execute(qc)
        uss = await User.loadbyid(db)
        for us in uss:
            _LOGGER.debug(f'Processing user {us.rowid} for db conversion {us.username} conf {us.conf}')
            for idv, brs in us.conf.get('browsers', dict()).items():
                await db.execute('INSERT INTO browser(name, url, user, sel) VALUES (?, ?, ?, ?)', (idv, brs['url'], us.rowid, brs['sel']))
            for idv, brs in us.conf.get('players', dict()).items():
                await db.execute('INSERT INTO player(name, url, user, sel) VALUES (?, ?, ?, ?)', (idv, brs['url'], us.rowid, brs['sel']))
            if 'browsers' in us.conf:
                del us.conf['browsers']
            if 'players' in us.conf:
                del us.conf['players']
            await db.execute('UPDATE user SET conf=? WHERE rowid=?', (json.dumps(us.conf) if us.conf else None, us.rowid))
        pps = await Playlist.loadbyid(db, loaditems=LOAD_ITEMS_ALL)
        qc = '''
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
            '''
        await db.execute(qc)
        qc = '''
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
                '''
        await db.execute(qc)
        qc = 'ALTER TABLE playlist ADD COLUMN rate REAL'
        await db.execute(qc)
        qc = 'ALTER TABLE playlist ADD COLUMN playstate TEXT'
        await db.execute(qc)
        qc = 'ALTER TABLE playlist_item ADD COLUMN timeplayed REAL'
        await db.execute(qc)
        qc = 'ALTER TABLE playlist_item ADD COLUMN component INTEGER REFERENCES playlist_component(rowid) ON UPDATE CASCADE ON DELETE SET NULL'
        await db.execute(qc)
        qc = 'ALTER TABLE playlist_item ADD COLUMN rate REAL'
        await db.execute(qc)
        for pp in pps:
            _LOGGER.debug(f'Processing playlist {pp.rowid} for db conversion {pp.name} conf {pp.conf}')
            allcomps = dict()
            if 'playlists_all' in pp.conf and (plad := pp.conf['playlists_all']):
                pld = pp.conf['playlists']
                brdd = pp.conf['brand']
                del pp.conf['playlists_all']
                del pp.conf['playlists']
                del pp.conf['brand']
                async with db.cursor() as cursor:
                    await cursor.execute('INSERT INTO playlist_component(brand, playlist, sel, parent, title, description, rate, filter, conf) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (brdd['id'], pp.rowid, True, None, brdd['title'], brdd['desc'], None, None, None))
                    brdd_rid = cursor.lastrowid
                    # allcomps[brdd['id']] = cursor.lastrowid
                for _, b in plad.items():
                    async with db.cursor() as cursor:
                        await cursor.execute('INSERT INTO playlist_component(brand, playlist, sel, parent, title, description, rate, filter, conf) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (b['id'], pp.rowid, str(b['id']) in pld, brdd_rid, b['title'], b['desc'], None, None, None))
                        allcomps[f"{brdd['id']}_{b['id']}"] = cursor.lastrowid
                        allcomps[b['id']] = cursor.lastrowid
            elif 'folders' in pp.conf and (fld := pp.conf['folders']):
                pld = pp.conf['playlists']
                del pp.conf['folders']
                del pp.conf['playlists']
                for idv, f in fld.items():
                    cnf = f.copy()
                    del cnf['id']
                    del cnf['title']
                    del cnf['description']
                    cnf = json.dumps(cnf)
                    async with db.cursor() as cursor:
                        await cursor.execute('INSERT INTO playlist_component(brand, playlist, sel, parent, title, description, rate, filter, conf) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (f['id'], pp.rowid, str(f['id']) in pld, None, f['title'], f['description'], None, None if not f.get('params') else json.dumps(f['params']), cnf))
                        allcomps[idv] = cursor.lastrowid
            else:
                pld = pp.conf['playlists']
                del pp.conf['playlists']
                for idv, f in pld.items():
                    cnf = f.copy()
                    del cnf['id']
                    del cnf['title']
                    del cnf['description']
                    if 'params' in cnf:
                        del cnf['params']
                    cnf = json.dumps(cnf)
                    async with db.cursor() as cursor:
                        await cursor.execute('INSERT INTO playlist_component(brand, playlist, sel, parent, title, description, rate, filter, conf) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (f['id'], pp.rowid, True, None, f['title'], f['description'], None, None if not f.get('params') else json.dumps(f['params']), cnf))
                        allcomps[idv] = cursor.lastrowid
            if (plad := pp.conf.get('play')):
                del pp.conf['play']
                for k, names in plad.items():
                    if k != 'id' and k != 'rate' and k != 'rates':
                        _LOGGER.debug(f'Processing view {k} for playlist {pp.rowid} -> {names}')
                        for k2, v2 in names.items():
                            flg = 0
                            if 'default' in k2:
                                flg |= 1
                            if k2.endswith(DOWNLOADED_SUFFIX):
                                k2 = k2[:-len(DOWNLOADED_SUFFIX)]
                                flg |= 2
                            if k2 not in allcomps:
                                if not (flg & 1):
                                    _LOGGER.warning(f'VIEWCONFPL Component {k2} not found for playlist {pp.rowid} during db conversion')
                                    continue
                            async with db.cursor() as cursor:
                                await cursor.execute('INSERT INTO view_conf(name, playlist, component, width, height, mime, type, remove) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (k, pp.rowid, allcomps.get(k2), v2['width'], v2['height'], v2.get('mime') if v2.get('mime') else None, flg, v2['remove_end']))
                    elif k == 'id':
                        await db.execute('UPDATE playlist SET playstate=? WHERE rowid=?', (names, pp.rowid))
                    elif k == 'rate':
                        await db.execute('UPDATE playlist SET rate=? WHERE rowid=?', (names, pp.rowid))
                    elif k == 'rates':
                        for k3, v3 in names.items():
                            if k3 in allcomps:
                                await db.execute('UPDATE playlist_component SET rate=? WHERE rowid=?', (v3, allcomps[k3]))
                            else:
                                _LOGGER.warning(f'RATEPL Component {k3} not found for playlist {pp.rowid} during db conversion while setting rates')
            if 'listings_command' in pp.conf:
                del pp.conf['listings_command']
            await db.execute('UPDATE playlist SET conf=? WHERE rowid=?', (json.dumps(pp.conf) if pp.conf else None, pp.rowid))
            for it in pp.items:
                cnf = it.conf.copy()
                if cnf.get('rate') is not None:
                    rate = cnf['rate']
                    del cnf['rate']
                else:
                    rate = None
                if cnf.get('sec') is not None:
                    sec = cnf['sec']
                    del cnf['sec']
                else:
                    sec = None
                component = cnf.get('playlist')
                if component is not None:
                    del cnf['playlist']
                    component = allcomps.get(component)
                if 'brand' in cnf:
                    del cnf['brand']
                if 'progid' in cnf:
                    del cnf['progid']
                if not component:
                    _LOGGER.warning(f'ITEMPL Component {it.playlist}{cnf} not found for playlist {pp.rowid} during db conversion while processing items')
                await db.execute('UPDATE playlist_item SET timeplayed=?, rate=?, component=?, conf=? WHERE rowid=?', (sec, rate, component, json.dumps(cnf) if cnf else None, it.rowid))
        await db.commit()
    await db.close()
    return dst


async def copy_database_async(
    source_engine: AsyncEngine,
    target_engine: AsyncEngine,
    chunk_size: int = 1000
) -> None:
    source_metadata = MetaData()

    # Riflette schema dal sorgente
    async with source_engine.connect() as src_conn:
        await src_conn.run_sync(source_metadata.reflect)
    tabo = dict()
    for table in source_metadata.sorted_tables:
        print(CreateTable(table))  # Debug: mostra SQL di creazione tabelle
        tabo[table.name] = table
    # Prepara schema target
    async with target_engine.begin() as dst_conn:
        for table_name in reversed(TABLE_ORDER):
            await dst_conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        instructions = DEST_SCHEMA.split(';')
        for instr in instructions:
            if instr.strip():
                await dst_conn.execute(text(instr))

    # Copia dati
    async with source_engine.connect() as src_conn, target_engine.begin() as dst_conn:

        for table_name in TABLE_ORDER:
            table = tabo[table_name]
            # await dst_conn.execute(table.delete())
            result = await src_conn.stream(select(table))
            async for rows in result.mappings().partitions(chunk_size):
                batch = [dict(r) for r in rows]
                if batch:
                    await dst_conn.execute(table.insert(), batch)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Copia/converti schema e dati tra database con SQLAlchemy async."
    )
    parser.add_argument(
        "--source-url",
        required=True,
        help="URL DB sorgente (es. sqlite+aiosqlite:///path/source.db)",
    )
    parser.add_argument(
        "--target-url",
        required=True,
        help="URL DB target (es. mysql+aiomysql://user:pass@host/db?charset=utf8mb4)",
    )
    parser.add_argument(
        "--operation",
        required=True,
        choices=["copy", "convert"],
        help="copy=append su schema esistente, convert=ricrea schema target e copia dati",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=2000,
        help="Numero righe per batch insert",
    )
    parser.add_argument(
        "--echo",
        default=False,
        action="store_true",
        help="Abilita log SQLAlchemy",
    )
    parser.add_argument(
        "--yes",
        default=False,
        action="store_true",
        help="Conferma operazione senza prompt",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    if not args.yes:
        print(f"Operazione: {args.operation}")
        print(f"DB sorgente: {args.source_url}")
        print(f"DB target: {args.target_url}")
        print(f"Chunk size: {args.chunk_size}")
        print(f"Echo SQL: {args.echo}")
        confirm = input("Procedere? (y/N): ").strip().lower()
        if confirm != 'y':
            print("Operazione annullata.")
            return
    if args.operation == "convert":
        await convert_db1(dict(dbfile=args.source_url.split("///")[-1], to=args.target_url.split("///")[-1]))
    elif args.operation == "copy":
        source_engine = create_async_engine(args.source_url, echo=args.echo)
        target_engine = create_async_engine(args.target_url, echo=args.echo)

        try:
            await copy_database_async(
                source_engine=source_engine,
                target_engine=target_engine,
                chunk_size=args.chunk_size
            )
        finally:
            await source_engine.dispose()
            await target_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
