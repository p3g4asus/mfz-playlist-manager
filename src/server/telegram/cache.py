from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union

from common.playlist import Playlist, PlaylistItem

if TYPE_CHECKING:
    from server.telegram.playlist import PlaylistTMessage, PlaylistItemTMessage


class PlaylistItemTg(object):
    def __init__(self, item: PlaylistItem, index: int):
        self.message: PlaylistItemTMessage = None
        self.refresh(item, index)

    def refresh(self, item: PlaylistItem, index: int):
        self.item = item
        self.index = index
        if self.message and self.message.has_expired():
            self.message = None


class PlaylistTg(object):
    def __init__(self, playlist: Playlist, index: int):
        self.message: PlaylistTMessage = None
        self.items: Dict[int, PlaylistItemTg] = dict()
        self.refresh(playlist, index)

    def get_items(self, deleted: Union[bool, Callable[[PlaylistItem], bool]] = False) -> List[PlaylistItemTg]:
        real_index = 0
        del_index = 1000000
        rv = []
        for _, itTg in self.items.items():
            it: PlaylistItem = itTg.item
            if (isinstance(deleted, bool) and (deleted or not it.seen)) or (not isinstance(deleted, bool) and deleted(it)):
                itTg.refresh(it, real_index if not it.seen else del_index)
                rv.append(itTg)
            else:
                itTg.refresh(it, del_index)
            if it.seen:
                del_index += 1
            else:
                real_index += 1
        return rv

    def get_item(self, rowid: int) -> PlaylistItemTg:
        if rowid in self.items:
            itemTg: PlaylistItemTg = self.items[rowid]
            itemTg.refresh(itemTg.item, itemTg.index)
            return itemTg
        else:
            return None

    def del_item(self, rowid: int) -> PlaylistItemTg:
        for i, it in enumerate(self.playlist.items):
            if it.rowid == rowid:
                del self.playlist.items[i]
                break
        if rowid in self.items:
            out = self.items[rowid]
            del self.items[rowid]
            self.refresh(self.playlist, self.index)
            return out
        else:
            return None

    def refresh(self, playlist: Playlist, index: int):
        self.playlist = playlist
        self.index = index
        olditems = self.items
        self.items: Dict[int, PlaylistItemTg] = dict()
        real_index = 0
        del_index = 1000000
        for it in playlist.items:
            it: PlaylistItem
            key = it.rowid
            i = real_index if not it.seen else del_index
            itemTg: PlaylistItemTg
            if key in olditems:
                itemTg = olditems[key]
                itemTg.refresh(it, i)
            else:
                itemTg = PlaylistItemTg(it, i)
            if not it.seen:
                real_index += 1
            else:
                del_index += 1
            self.items[key] = itemTg
        if self.message and self.message.has_expired():
            self.message = None


_PLAYLIST_CACHE: Dict[int, Dict[int, PlaylistTg]] = dict()


def cache_store(p: Playlist, index=None):
    useris = p.useri
    if useris not in _PLAYLIST_CACHE:
        dep = _PLAYLIST_CACHE[useris] = dict()
    else:
        dep = _PLAYLIST_CACHE[useris]
    pids = p.rowid
    if index is None:
        if pids not in dep:
            index = len(dep)
        else:
            index = dep[pids].index
    plaTg: PlaylistTg
    if pids in dep:
        plaTg = dep[pids]
        plaTg.refresh(p, index)
    else:
        dep[pids] = PlaylistTg(p, index)


def cache_del(p: Playlist):
    useris = p.useri
    dep: dict = _PLAYLIST_CACHE.get(useris, None)
    if dep:
        pids = p.rowid
        if pids in dep:
            del dep[pids]
            for i, pd in enumerate(dep.values()):
                pd.index = i


def cache_on_item_deleted(useris: int, pids: int):
    dep: dict = _PLAYLIST_CACHE.get(useris, None)
    if dep:
        if pids in dep:
            plTg = dep[pids]
            plTg.refresh(plTg.playlist, plTg.index)


def cache_on_item_updated(useris: int, it: PlaylistItem):
    dep: dict = _PLAYLIST_CACHE.get(useris, None)
    if dep:
        pids = it.playlist
        if pids in dep:
            plTg: PlaylistTg = dep[pids]
            for i, ito in enumerate(plTg.playlist.items):
                if it.rowid == ito.rowid:
                    plTg.playlist.items[i] = it
                    plTg.refresh(plTg.playlist, plTg.index)
                    break


def cache_del_user(useris: int, playlists: List[Playlist]):
    newdict = dict() if useris in _PLAYLIST_CACHE else None
    for p in playlists:
        pids = p.rowid
        cache_store(p)
        if newdict is not None:
            newdict[pids] = _PLAYLIST_CACHE[useris][pids]
    if newdict is not None:
        _PLAYLIST_CACHE[useris] = newdict


def cache_get(useris: int, pids: Optional[int] = None) -> Union[List[PlaylistTg], PlaylistTg]:
    if pids is None:
        dd = _PLAYLIST_CACHE.get(useris, dict())
        pps = []
        for _, p in dd.items():
            if p.message and p.message.has_expired():
                p.message = None
            pps.append(p)
        return pps
    else:
        dd = _PLAYLIST_CACHE.get(useris, dict()).get(pids, None)
        if dd and dd.message and dd.message.has_expired():
            dd.message = None
        return dd


def cache_get_items(useri: int, pid: int, deleted: Union[bool, Callable[[PlaylistItem], bool]]) -> List[PlaylistItemTg]:
    dd = cache_get(useri, pid)
    return dd.get_items(deleted) if dd else []


def cache_get_item(useris: int, pids: int, itid: int) -> PlaylistItemTg:
    dd = _PLAYLIST_CACHE.get(useris, dict()).get(pids)
    return dd.get_item(itid) if dd else None
