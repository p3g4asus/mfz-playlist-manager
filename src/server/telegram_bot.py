import asyncio
import logging
import re
from time import time
import traceback
from abc import abstractmethod
from datetime import datetime, timedelta
from enum import Enum, auto
from html import escape
from os import stat
from os.path import exists, isfile, split
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode, urlparse, urlunparse, unquote, parse_qs, ParseResult

import validators
from aiohttp import ClientSession
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD
from telegram_menu import (BaseMessage, ButtonType, NavigationHandler,
                           TelegramMenuSession)
from telegram_menu.models import MenuButton, emoji_replace

from common.const import (CMD_CLEAR, CMD_DEL, CMD_DOWNLOAD, CMD_DUMP, CMD_FOLDER_LIST, CMD_FREESPACE, CMD_IORDER, CMD_MEDIASET_BRANDS, CMD_MEDIASET_LISTINGS, CMD_MOVE, CMD_RAI_CONTENTSET, CMD_RAI_LISTINGS,
                          CMD_REFRESH, CMD_REMOTEPLAY_JS, CMD_REMOTEPLAY_JS_DEL, CMD_REMOTEPLAY_JS_FFW, CMD_REMOTEPLAY_JS_GOTO, CMD_REMOTEPLAY_JS_NEXT, CMD_REMOTEPLAY_JS_PAUSE, CMD_REMOTEPLAY_JS_PREV, CMD_REMOTEPLAY_JS_REW, CMD_REMOTEPLAY_JS_SEC, CMD_REN, CMD_SEEN, CMD_SORT, CMD_TOKEN, CMD_YT_PLAYLISTCHECK)
from common.playlist import (Playlist, PlaylistItem, PlaylistMessage)
from common.user import User

_LOGGER = logging.getLogger(__name__)


def duration2string(secs):
    gg = int(secs / 86400)
    rem = secs % 86400
    hh = int(rem / 3600)
    rem = secs % 3600
    mm = int(rem / 60)
    ss = rem % 60
    if gg > 0:
        return '%dg %02dh %02dm %02ds' % (gg, hh, mm, ss)
    elif hh > 0:
        return '%dh %02dm %02ds' % (hh, mm, ss)
    elif mm > 0:
        return '%dm %02ds' % (mm, ss)
    else:
        return f'{ss}s'


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
        self.items: Dict[str, PlaylistItemTg] = dict()
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
        key = str(rowid)
        if key in self.items:
            itemTg: PlaylistItemTg = self.items[key]
            itemTg.refresh(itemTg.item, itemTg.index)
            return itemTg
        else:
            return None

    def del_item(self, rowid: int) -> PlaylistItemTg:
        for i, it in enumerate(self.playlist.items):
            if it.rowid == rowid:
                del self.playlist.items[i]
                break
        key = str(rowid)
        if key in self.items:
            out = self.items[key]
            del self.items[key]
            self.refresh(self.playlist, self.index)
            return out
        else:
            return None

    def refresh(self, playlist: Playlist, index: int):
        self.playlist = playlist
        self.index = index
        olditems = self.items
        self.items: Dict[str, PlaylistItemTg] = dict()
        real_index = 0
        del_index = 1000000
        for it in playlist.items:
            key = str(it.rowid)
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


_PLAYLIST_CACHE: Dict[str, Dict[str, PlaylistTg]] = dict()


def cache_store(p: Playlist, index=None):
    useris = str(p.useri)
    if useris not in _PLAYLIST_CACHE:
        dep = _PLAYLIST_CACHE[useris] = dict()
    else:
        dep = _PLAYLIST_CACHE[useris]
    pids = str(p.rowid)
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
    useris = str(p.useri)
    dep: dict = _PLAYLIST_CACHE.get(useris, None)
    if dep:
        pids = str(p.rowid)
        if pids in dep:
            del dep[pids]
            for i, pd in enumerate(dep.values()):
                pd.index = i


def cache_on_item_deleted(useri: int, pid: int):
    useris = str(useri)
    dep: dict = _PLAYLIST_CACHE.get(useris, None)
    if dep:
        pids = str(pid)
        if pids in dep:
            plTg = dep[pids]
            plTg.refresh(plTg.playlist, plTg.index)


def cache_del_user(useri: int, playlists: List[Playlist]):
    newdict = dict()
    useris = str(useri)
    newdict = dict() if useris in _PLAYLIST_CACHE else None
    for p in playlists:
        pids = str(p.rowid)
        cache_store(p)
        if newdict is not None:
            newdict[pids] = _PLAYLIST_CACHE[useris][pids]
    if newdict is not None:
        _PLAYLIST_CACHE[useris] = newdict


def cache_get(useri: int, pid: Optional[int] = None) -> Union[List[PlaylistTg], PlaylistTg]:
    useris = str(useri)
    if pid is None:
        dd = _PLAYLIST_CACHE.get(useris, dict())
        pps = []
        for _, p in dd.items():
            if p.message and p.message.has_expired():
                p.message = None
            pps.append(p)
        return pps
    else:
        pids = str(pid)
        dd = _PLAYLIST_CACHE.get(useris, dict()).get(pids, None)
        if dd and dd.message and dd.message.has_expired():
            dd.message = None
        return dd


def cache_get_items(useri: int, pid: int, deleted: Union[bool, Callable[[PlaylistItem], bool]]) -> List[PlaylistItemTg]:
    dd = cache_get(useri, pid)
    return dd.get_items(deleted) if dd else []


def cache_get_item(useri: int, pid: int, itid: int) -> PlaylistItemTg:
    useris = str(useri)
    pids = str(pid)
    dd = _PLAYLIST_CACHE.get(useris, dict()).get(pids)
    return dd.get_item(itid) if dd else None


class MyNavigationHandler(NavigationHandler):
    """Example of navigation handler, extended with a custom "Back" command."""

    async def goto_back(self) -> int:
        """Do Go Back logic."""
        return await self.select_menu_button("Back")


class ProcessorMessage(object):
    def __init__(self, user: User, params):
        self.user = user
        self.params = params
        self.processors = params.processors2
        self.executor = params.telegram_executor

    async def process(self, pl):
        for k, p in self.processors.items():
            _LOGGER.debug(f'Checking {k}')
            if p.interested(pl):
                out = await p.process(None, pl, self.user.rowid, self.executor)
                if out:
                    return out
        return None


class NameDurationStatus(Enum):
    IDLE = auto()
    RETURNING_IDLE = auto()
    DELETING = auto()
    DELETING_CONFIRM = auto()
    RENAMING = auto()
    UPDATING_INIT = auto()
    UPDATING_START = auto()
    UPDATING_STOP = auto()
    UPDATING_RUNNING = auto()
    UPDATING_WAITING = auto()
    SORTING = auto()
    DOWNLOADING = auto()
    DOWNLOADING_WAITING = auto()
    NAMING = auto()
    LISTING = auto()
    MOVING = auto()


class StatusTMessage(BaseMessage):
    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: Optional[timedelta] = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, **argw) -> None:
        super().__init__(navigation, label, picture, expiry_period, inlined, home_after, notification, input_field, **argw)
        self.status = NameDurationStatus.IDLE
        self.sub_status = 0
        self.return_msg = ''
        self.scheduler_job = None
        self.proc = ProcessorMessage(user, params)

    async def edit_or_select(self, context: Optional[CallbackContext] = None):
        try:
            if self.inlined:
                await self.edit_message()
            else:
                await self.navigation.goto_menu(self, context, add_if_present=False)
        except Exception:
            _LOGGER.warning(f'edit error {traceback.format_exc()}')

    async def switch_to_status(self, args, context=None):
        self.status = args[0]
        await self.edit_or_select(context)

    async def switch_to_idle_end(self):
        await self.edit_or_select()

    def scheduler_job_remove(self, name: str = None):
        if self.scheduler_job and not name:
            try:
                _LOGGER.debug(f'Deleting {self.scheduler_job.name} for {id(self)}')
                self.scheduler_job.remove()
            except Exception:
                pass
            self.scheduler_job = None
        elif name:
            try:
                _LOGGER.debug(f'Deleting {name} for {id(self)}')
                self.navigation.scheduler.remove_job(name, 'default')
            except Exception:
                pass

    async def switch_to_idle(self):
        if self.return_msg and self.sub_status != -1000:
            self.status = NameDurationStatus.RETURNING_IDLE
            self.sub_status = -1000
        else:
            self.status = NameDurationStatus.IDLE
            self.sub_status = 0
            self.return_msg = ''
        self.scheduler_job_remove()
        if self.return_msg:
            self.navigation.scheduler.add_job(
                self.switch_to_idle,
                "date",
                id=f"switch_to_idle{id(self)}",
                replace_existing=True,
                run_date=datetime.utcnow() + timedelta(seconds=8 if self.inlined else 0.5)
            )
        await self.switch_to_idle_end()

    async def long_operation_do(self):
        sign = self.sub_status & 512
        self.sub_status &= 0xFF
        if self.sub_status == 10:
            sign = 512
        elif self.sub_status == 0:
            sign = 0
        self.sub_status = (self.sub_status + 1 * (-1 if sign else 1)) | sign
        await self.edit_or_select()

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        return None


class DeletingTMessage(StatusTMessage):
    async def wait_undo_job(self):
        if self.sub_status <= 0:
            if self.status == NameDurationStatus.DELETING:
                self.scheduler_job_remove()
                await self.delete_item_do()
                await self.switch_to_idle()
        else:
            self.sub_status -= 1
            await self.edit_or_select()

    @abstractmethod
    async def delete_item_do(self):
        return

    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: timedelta | None = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, **argw) -> None:
        self.del_action: str = ''
        super().__init__(navigation, label, picture, expiry_period, inlined, home_after, notification, input_field, user, params, **argw)

    def delete_item_pre_pre(self, args):
        self.del_action = args[0]
        self.delete_item_pre()

    def delete_item_pre(self):
        self.status = NameDurationStatus.DELETING
        self.sub_status = 10
        name: str = f"wait_undo_job{id(self)}"
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.wait_undo_job,
            "interval",
            name=name,
            id=name,
            seconds=1,
            replace_existing=True,
        )

    async def update(self, _: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        if self.status == NameDurationStatus.DELETING:
            self.input_field = u'\U0001F570'
            self.add_button(f':cross_mark: Undo in {self.sub_status} sec', self.switch_to_idle)
        return ''


class PlayerInfo(object):
    END_URL_PATH: str = '-s/play/player_remote_commands.htm'
    DEFAULT_VINFO = dict(title='N/A', durs='0s', tot_n=0, tot_durs='0s', duri=0, chapters=[])
    DEFAULT_PINFO = dict(sec=0)

    @staticmethod
    def is_player_url_ok(url) -> Tuple[ParseResult, Dict[str, List[str]]]:
        parsed_url = urlparse(url)
        dictspar = parse_qs(parsed_url.query)
        return (parsed_url, dictspar) if parsed_url.scheme and 'name' in dictspar and 'hex' in dictspar and parsed_url.path.endswith(PlayerInfo.END_URL_PATH) else None

    def __init__(self, name: str, url: str, sel: bool) -> None:
        if not (pr := self.is_player_url_ok(url)):
            raise Exception(f'Invalid player url {url}')
        self.name: str = name
        self.url: str = url
        self.sel = sel
        self.plnames: List[str] = list(pr[1]['name'])
        self.pinfo: Dict[str, str] = PlayerInfo.DEFAULT_PINFO
        self.vinfo: Dict[str, str] = PlayerInfo.DEFAULT_VINFO
        self.play_url = urlunparse(pr[0]._replace(path=pr[0].path[1:-len(PlayerInfo.END_URL_PATH)] + '-s/play/workout.htm')._replace(query=''))
        self.base_cmd: ParseResult = pr[0]._replace(path=pr[0].path[1:-len(PlayerInfo.END_URL_PATH)] + f'/rcmd/{pr[1]["hex"][0]}')

    async def sendGenericCommand(self, **cmdo):
        urlp = self.base_cmd._replace(query=urlencode(cmdo, doseq=True))
        urls = urlunparse(urlp)
        async with ClientSession() as session:
            async with session.get(urls) as resp:
                if not (resp.status >= 200 and resp.status < 300):
                    return None
                else:
                    try:
                        rv = None
                        data = await resp.json()
                        if 'pinfo' in data:
                            rv = data
                            if isinstance(data['pinfo'], dict):
                                self.pinfo = data['pinfo']
                            else:
                                self.pinfo = PlayerInfo.DEFAULT_PINFO
                        if 'vinfo' in data:
                            rv = data
                            if isinstance(data['vinfo'], dict):
                                self.vinfo = data['vinfo']
                            else:
                                self.vinfo = PlayerInfo.DEFAULT_VINFO
                    except Exception:
                        pass
                    return rv


class PlayerInfoMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, player_info: PlayerInfo, user: User = None, params: object = None, **argw) -> None:
        self.pi = player_info
        self.time_btn: datetime = None
        self.btn_type: int = 0
        self.time_status: int = 0
        self.info_changed: bool = False
        super().__init__(
            navigation,
            label=self.__class__.__name__ + player_info.name,
            expiry_period=timedelta(hours=3),
            input_field='Timestamp',
            user=user,
            params=params)

    def calc_dyn_sec(self):
        if not self.time_btn:
            return 0
        else:
            return (round((datetime.now() - self.time_btn).seconds * 5) + 10) * self.btn_type

    async def refresh_msg(self):
        if self.time_btn:
            passed = (datetime.now() - self.time_btn).seconds
            if passed > 120:
                await self.switch_to_idle()
            else:
                await self.edit_or_select()

    async def play(self, args: tuple):
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_PAUSE)

    async def move(self, args: tuple):
        val = args[0]
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_FFW if val > 0 else CMD_REMOTEPLAY_JS_REW, n=abs(val))

    async def move_pl(self, args: tuple):
        val = args[0]
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_NEXT if val > 0 else (CMD_REMOTEPLAY_JS_PREV if val < 0 else CMD_REMOTEPLAY_JS_DEL))

    async def switch_pl(self, args: tuple):
        val = args[0]
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_GOTO, link=self.pi.play_url + f'?{urlencode(dict(name=val))}')
        await self.switch_to_idle()

    async def move_abs(self, args: tuple):
        val = args[0]
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_SEC, n=val)

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.IDLE:
            text = text.strip()
            try:
                sect = None
                if text.startswith('/TT'):
                    text = text[3:]
                while True:
                    if (mo := re.search(r'^\s*([0-9]+)\s*([msh]?)', text)):
                        sec = int(mo.group(1))
                        um = mo.group(2)
                        if um == 'm':
                            sec *= 60
                        elif um == 'h':
                            sec *= 3600
                        text = text[len(mo.group(0)):]
                        sect = sec if sect is None else sect + sec
                    else:
                        break
                if sect is not None:
                    await self.move_abs((sect, ))
            except Exception:
                pass

    async def info(self, args: tuple):
        await self.pi.sendGenericCommand(get=['vinfo', 'pinfo'])
        self.info_changed = True
        await self.edit_or_select()

    async def manage_state_change(self, args: tuple, context: Optional[CallbackContext] = None):
        btn_id: int = 0
        f = args[0]
        if isinstance(f, int):
            btn_id = f
            args = args[1:]
        _LOGGER.debug(f'btn_id={btn_id} type={self.btn_type}')
        if btn_id and not self.btn_type:
            self.btn_type = btn_id
            self.time_btn = datetime.now()
            name: str = f"manage_state_change{id(self)}"
            self.scheduler_job = self.navigation.scheduler.add_job(
                self.refresh_msg,
                "interval",
                name=name,
                id=name,
                seconds=1,
                replace_existing=True,
            )
            await self.switch_to_status((NameDurationStatus.RENAMING, ), context)
            return
        elif not btn_id and self.btn_type:
            self.btn_type = 0
            self.time_btn = None
            await self.switch_to_idle()
            if args[0] == self.move:
                return
        elif btn_id and self.btn_type and self.btn_type != btn_id:
            self.btn_type = btn_id
            self.time_btn = datetime.now()
            return
        elif btn_id and self.btn_type:
            await self.move((self.calc_dyn_sec(),))
            self.btn_type = 0
            self.time_btn = None
            await self.switch_to_idle()
            return
        await args[0](args[1:])

    TIMES = [
        u'\U0001F55B',
        u'\U0001F550',
        u'\U0001F55C',
        u'\U0001F551',
        u'\U0001F55D',
        u'\U0001F552',
        u'\U0001F55E',
        u'\U0001F553',
        u'\U0001F55F',
        u'\U0001F554',
        u'\U0001F560',
        u'\U0001F555',
        u'\U0001F561',
        u'\U0001F556',
        u'\U0001F562',
        u'\U0001F557',
        u'\U0001F563',
        u'\U0001F558',
        u'\U0001F564',
        u'\U0001F559',
        u'\U0001F565',
        u'\U0001F55A',
        u'\U0001F566',
    ]

    async def update(self, context: CallbackContext | None = None) -> str:
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = u'\U000023F2 Timestamp'
        addtxt = ''
        if self.status == NameDurationStatus.IDLE or self.status == NameDurationStatus.RENAMING:
            self.add_button(u'\U000023EF', self.manage_state_change, args=(self.play,))
            self.add_button(u'\U00002139', self.manage_state_change, args=(self.info, ))
            self.add_button(u'\U000023EE', self.manage_state_change, args=(self.move_pl, -1), new_row=True)
            self.add_button(u'\U000023ED', self.manage_state_change, args=(self.move_pl, +1))
            self.add_button(u'\U000023ED \U0001F5D1', self.manage_state_change, args=(self.move_pl, 0), new_row=True)
            self.add_button(u'\U0001F51C', self.manage_state_change, args=(self.switch_to_status, NameDurationStatus.DOWNLOADING_WAITING, context))
            if self.status == NameDurationStatus.RENAMING:
                if self.btn_type == 1:
                    addtxt = f'{self.calc_dyn_sec()}'
                elif self.btn_type == -1:
                    addtxt = f'{-self.calc_dyn_sec()}'
            self.add_button(u'...\U000023EA', self.manage_state_change, args=(-1, self.move, -1), new_row=True)
            self.add_button(u'\U000023E9...', self.manage_state_change, args=(+1, self.move, +1))
            self.add_button(u'10s\U000023EA', self.manage_state_change, args=(self.move, -10), new_row=True)
            self.add_button(u'\U000023E910s', self.manage_state_change, args=(self.move, +10))
            self.add_button(u'30s\U000023EA', self.manage_state_change, args=(self.move, -30), new_row=True)
            self.add_button(u'\U000023E930s', self.manage_state_change, args=(self.move, +30))
            self.add_button(u'60s\U000023EA', self.manage_state_change, args=(self.move, -60), new_row=True)
            self.add_button(u'\U000023E960s', self.manage_state_change, args=(self.move, +60))
            self.add_button(label=u"\U0001F519", callback=self.navigation.goto_back, new_row=True)
        elif self.status == NameDurationStatus.DOWNLOADING_WAITING:
            self.input_field = u'\U0001F449'
            for plname in self.pi.plnames:
                self.add_button(plname, self.switch_pl, args=(plname, ))
            self.add_button(u'\U00002934', self.switch_to_idle)
        if addtxt:
            rv = ''
            for x in addtxt:
                rv += x + u'\U0000FE0F\U000020E3'
            return rv
        elif not self.info_changed:
            idx = self.time_status
            self.time_status += 1
            if self.time_status >= len(self.TIMES):
                self.time_status = 0
            return self.TIMES[idx]
        else:
            self.info_changed = False
            rv = f'{self.pi.vinfo["title"]}\n'
            rv += u'\U000023F3 ' + f'{self.pi.vinfo["durs"]}\n'
            rv += u'\U0001F4B0 ' + f'{self.pi.vinfo["tot_n"]} ({self.pi.vinfo["tot_durs"]})\n'
            no = int(round(30.0 * (perc := self.pi.pinfo["sec"] / self.pi.vinfo["duri"]))) if self.pi.vinfo["duri"] else (perc := 0)
            rv += f'<code>{duration2string(round(self.pi.pinfo["sec"]))} ({self.pi.vinfo["durs"]})\n[' + (no * 'o') + ((30 - no) * ' ') + f'] {round(perc * 100)}%</code>'
            for ch in self.pi.vinfo["chapters"]:
                rv += f'\n/TT{int(ch["start_time"])}s {ch["title"]}'
            return rv


class PlayerListMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, **argw) -> None:
        self.players: Dict[str, PlayerInfo] = None
        self.players_cache: Dict[str, PlayerInfoMessage] = dict()
        self.current_url = ''
        super().__init__(navigation, label=self.__class__.__name__, input_field='Player Url', user=user, params=params, **argw)

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.IDLE:
            text = text.strip()
            if not self.current_url:
                if PlayerInfo.is_player_url_ok(text):
                    self.current_url = text
                    await self.edit_or_select()
            elif PlayerInfo.is_player_url_ok(text):
                self.current_url = text
            else:
                await self.add_player(PlayerInfo(text, self.current_url, False))
                self.current_url = ''
                await self.edit_or_select()

    @staticmethod
    async def set_user_conf_field(players: Dict[str, PlayerInfo], proc: ProcessorMessage):
        res = proc.user.conf
        plrs = dict()
        for pin, pi in players.items():
            plrs[pin] = dict(url=pi.url, sel=pi.sel)
        res['players'] = plrs
        await proc.user.toDB(proc.params.db2)

    @staticmethod
    def user_conf_field_to_players_dict(navigation: NavigationHandler, proc: ProcessorMessage, sel_only: bool = False) -> Tuple[Dict[str, PlayerInfo], Dict[str, PlayerInfoMessage]]:
        players = dict()
        players_cache = dict()
        usrconf = proc.user.conf
        for pin, pid in usrconf.get('players', dict()).items():
            if isinstance(pid, str):
                piu = pid
                sel = False
            elif isinstance(pid, dict):
                piu = pid['url']
                sel = pid['sel']
            else:
                piu = None
            if piu and (sel or not sel_only):
                players[pin] = pi = PlayerInfo(pin, piu, sel)
                if navigation and proc:
                    players_cache[pin] = PlayerInfoMessage(navigation, pi, user=proc.user, params=proc.params)
        return (players, players_cache)

    async def add_player(self, pi: PlayerInfo):
        self.players[pi.name] = pi
        self.players_cache[pi.name] = PlayerInfoMessage(self.navigation, pi, user=self.proc.user, params=self.proc.params)
        await self.set_user_conf_field(self.players, self.proc)
        await self.edit_or_select()

    async def player_clicked(self, args: tuple):
        self.current_url = ''
        if self.status == NameDurationStatus.DELETING:
            del self.players[args[0]]
            del self.players_cache[args[0]]
            await self.set_user_conf_field(self.players, self.proc)
            await self.switch_to_idle()
        elif self.status == NameDurationStatus.SORTING:
            self.players[args[0]].sel = not self.players[args[0]].sel
            await self.set_user_conf_field(self.players, self.proc)
            await self.switch_to_idle()
        else:
            await self.players_cache[args[0]].edit_or_select()

    async def prepare_for_mod(self, args: tuple, context: Union[CallbackContext, None] = None):
        self.current_url = ''
        await self.switch_to_status(args, context)

    async def update(self, _: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        self.input_field = ('Player Url' if not self.current_url else 'Player alias') + u' or \U0001F559'
        if self.players is None:
            self.players, self.players_cache = self.user_conf_field_to_players_dict(self.navigation, self.proc)
        self.keyboard: List[List["MenuButton"]] = [[]]
        for pin in sorted(self.players.keys(), key=str.casefold):
            self.add_button(pin + (u' \U0001F4CD' if self.players[pin].sel else ''), self.player_clicked, args=(pin,), new_row=True)
        if self.status == NameDurationStatus.IDLE:
            if self.players:
                self.add_button(u'\U0001F5D1', self.prepare_for_mod, args=(NameDurationStatus.DELETING, ), new_row=True)
                self.add_button(u'\U0001F4CC', self.prepare_for_mod, args=(NameDurationStatus.SORTING, ))
            self.add_button(label=u"\U0001F3E0 Home", callback=self.navigation.goto_back, new_row=True)
            return 'Click player to open or add new player'
        else:
            self.add_button(':cross_mark: Abort', self.switch_to_idle, new_row=True)
            return 'Click player to delete'


class RefreshingTMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: Optional[timedelta] = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, playlist: Playlist = None, **argw) -> None:
        super().__init__(navigation, label, picture, expiry_period, inlined, home_after, notification, input_field, user, params, **argw)
        self.playlist = playlist
        self.upd_sta = None
        self.upd_sto = None

    def set_playlist(self, playlist):
        self.playlist = playlist

    async def switch_to_status_cond(self, args, context):
        if self.status != NameDurationStatus.UPDATING_RUNNING:
            return await super().switch_to_status(args, context)

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        if self.status in (NameDurationStatus.UPDATING_INIT, NameDurationStatus.UPDATING_START, NameDurationStatus.UPDATING_STOP, NameDurationStatus.UPDATING_WAITING) or (self.status == NameDurationStatus.IDLE and not self.inlined):
            if self.status == NameDurationStatus.UPDATING_INIT:
                self.upd_sta = datetime.fromtimestamp(int(0 if not self.playlist.dateupdate else self.playlist.dateupdate / 1000))
                self.upd_sto = datetime.now()
                self.status = NameDurationStatus.UPDATING_WAITING
            self.add_button(self.upd_sta.strftime('%Y-%m-%d'), self.switch_to_status, args=(NameDurationStatus.UPDATING_START, ))
            self.add_button(self.upd_sto.strftime('%Y-%m-%d'), self.switch_to_status, args=(NameDurationStatus.UPDATING_STOP, ))
            self.add_button(':cross_mark: Abort Refresh', self.on_refresh_abort_cond, new_row=True)
            self.add_button(u'\U0001F501', self.update_playlist)
            if self.status == NameDurationStatus.UPDATING_START:
                self.input_field = 'Start date (YYMMDD)'
                return '<u>Start date</u> (YYMMDD)'
            elif self.status == NameDurationStatus.UPDATING_STOP:
                self.input_field = 'Stop date (YYMMDD)'
                return '<u>Stop date</u> (YYMMDD)'
            elif self.status == NameDurationStatus.UPDATING_WAITING:
                self.input_field = u'\U0001F449'
                return f'Review params for {self.playlist.name} and update or abort'
        if self.status == NameDurationStatus.UPDATING_RUNNING:
            self.input_field = u'\U0001F570'
            return f'{self.playlist.name} updating {"." * (self.sub_status & 0xFF)}'

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status in (NameDurationStatus.UPDATING_START, NameDurationStatus.UPDATING_STOP):
            text = text.strip()
            try:
                if self.status == NameDurationStatus.UPDATING_START:
                    self.upd_sta = datetime.strptime(f'{text} 00:00:00.1', '%y%m%d %H:%M:%S.%f')
                elif self.status == NameDurationStatus.UPDATING_STOP:
                    self.upd_sto = datetime.strptime(f'{text} 23:59:59.9', '%y%m%d %H:%M:%S.%f')
                self.status = NameDurationStatus.UPDATING_WAITING
                await self.edit_or_select(context)
            except Exception:
                pass

    def update_playlist(self):
        if self.status != NameDurationStatus.UPDATING_RUNNING:
            asyncio.get_event_loop().create_task(self.update_playlist_1())

    async def update_playlist_1(self):
        self.status = NameDurationStatus.UPDATING_RUNNING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id=f"long_operation_do{self.label}",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = PlaylistMessage(CMD_REFRESH, playlist=self.playlist, datefrom=int(self.upd_sta.timestamp() * 1000), dateto=int(self.upd_sto.timestamp() * 1000))
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.playlist = pl.playlist
            cache_store(self.playlist)
            self.return_msg = f'Refresh OK :thumbs_up: ({pl.n_new} new videos)'
        else:
            self.return_msg = f'Error {pl.rv} refreshing {self.playlist.name} :thumbs_down:'
        await self.on_refresh_finish(pl)

    @abstractmethod
    async def on_refresh_finish(self, pl: PlaylistMessage):
        return

    async def on_refresh_abort_cond(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        if self.status != NameDurationStatus.UPDATING_RUNNING:
            return await self.on_refresh_abort(context)

    @abstractmethod
    async def on_refresh_abort(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        return


class NameDurationTMessage(DeletingTMessage):

    async def send(self, context: Optional[CallbackContext] = None):
        if self.inlined:
            await self.prepare_for_sending()
            await self.navigation._send_app_message(self, self.label)
        else:
            await self.navigation.goto_menu(self, context, add_if_present=False)

    async def edit_or_select(self, context: Optional[CallbackContext] = None):
        if self.inlined and self._old_thumb != self.thumb:
            await self.send(context)
        else:
            return await super().edit_or_select(context)

    async def edit_or_select_if_exists(self, delay: float = 0, context: Optional[CallbackContext] = None):
        if self.time_alive and self.refresh_from_cache():
            if delay > 0.0:
                name = f"eos{self.label}"
                self.navigation.scheduler.add_job(
                    self.edit_or_select,
                    "date",
                    id=name,
                    name=name,
                    replace_existing=True,
                    run_date=datetime.utcnow() + timedelta(seconds=delay)
                )
            else:
                await self.edit_or_select()

    async def set_picture_path(self):
        if self._old_thumb != self.thumb:
            self._old_thumb = self.thumb
            headers = {"range": "bytes=0-10", "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/81.0"}
            thumb = unquote(self.thumb[6:]) if self.thumb and self.thumb[0] == '?' else (f'{self.proc.params.link}/{self.proc.params.args["sid"]}-s/{self.thumb[1:]}' if self.thumb and self.thumb[0] == '@' else self.thumb)
            if thumb and validators.url(thumb):
                async with ClientSession() as session:
                    async with session.get(thumb, headers=headers) as resp:
                        if not (resp.status >= 200 and resp.status < 300):
                            self.picture = ''
                        else:
                            self.picture = thumb
            else:
                self.picture = ''

    @abstractmethod
    def refresh_from_cache(self):
        return

    async def prepare_for_sending(self):
        if self.refresh_from_cache():
            await self.set_picture_path()
            return True
        else:
            return False

    def __init__(self, navigation: NavigationHandler, myid: int = None, user: User = None, params: object = None, **argw) -> None:
        self.index = None
        self.id = myid
        self.name = None
        self.secs = None
        self.obj = None
        self.thumb = None
        self._old_thumb = None
        self.deleted = None
        super().__init__(
            navigation=navigation,
            label=f'{self.__class__.__name__}_{myid}_{int(datetime.now().timestamp() * 1000)}',
            picture=self.thumb,
            inlined=True,
            home_after=False,
            expiry_period=timedelta(hours=10),
            user=user,
            params=params,
            **argw
        )
        self.refresh_from_cache()


class PlaylistItemTMessage(NameDurationTMessage):
    def refresh_from_cache(self):
        obj = cache_get_item(self.proc.user.rowid, self.pid, self.id)
        if obj:
            self.obj = obj.item
            obj.message = self
            p = cache_get(self.proc.user.rowid, self.pid)
            self.playlist_name = p.playlist.name
            self.index = obj.index
            self.name = self.obj.title
            self.secs = self.obj.dur
            self.thumb = self.obj.img
            self.deleted = self.obj.seen
            return True
        else:
            return False

    def __init__(self, navigation: NavigationHandler, myid: int = None, user: User = None, params: object = None, pid: int = None, **argw) -> None:
        self.pid = pid
        self.current_sort: str = ''
        super().__init__(navigation, myid, user, params)

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.SORTING:
            text = text.strip()
            if re.match(r'^[0-9]+$', text):
                await self.set_iorder_do(int(text))
                await self.switch_to_idle()

    async def stop_download(self, args, _):
        myid = args[0]
        pl = PlaylistMessage(CMD_DOWNLOAD, playlistitem=myid)
        pl = await self.proc.process(pl)

    def download_format(self, args, context):
        asyncio.get_event_loop().create_task(self.download_format_1(args, context))

    async def download_format_1(self, args, context):
        self.status = NameDurationStatus.DOWNLOADING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id=f"long_operation_do{self.label}",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = PlaylistMessage(CMD_DOWNLOAD,
                             playlistitem=self.id,
                             fmt=args[0],
                             host=f'{self.proc.params.link}/{self.proc.params.args["sid"]}',
                             conv=args[1])
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.obj.dl = pl.playlistitem.dl
            self.return_msg = f'Download OK {split(self.obj.dl)[1]} :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} downloading {self.name} :thumbs_down:'
        await self.switch_to_idle()

    @staticmethod
    def sizeof_fmt(num, suffix="B"):
        for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Yi{suffix}"

    @staticmethod
    def dictget(dcn, key, default=None):
        return dcn[key] if key in dcn and dcn[key] else default

    async def move_to_do(self, args):
        pdst: PlaylistTg
        psrc: PlaylistTg
        pdst, psrc = args
        pl = PlaylistMessage(CMD_MOVE, playlistitem=self.id, playlist=pdst.playlist.rowid)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            cache_store(pl.playlist)
            plTg: PlaylistTg = cache_get(self.proc.user.rowid, pl.playlist.rowid)
            itemTg = cache_get_item(self.proc.user.rowid, pl.playlist.rowid, self.id)
            oldItemTg = psrc.del_item(self.id)
            itemTg.message = oldItemTg.message
            itemTg.message.pid = pl.playlist.rowid
            if itemTg.message:
                await itemTg.message.edit_or_select_if_exists()
            if psrc.message:
                await psrc.message.edit_or_select_items()
                await psrc.message.edit_or_select_if_exists()
            if plTg.message:
                await plTg.message.edit_or_select_items()
                await plTg.message.edit_or_select_if_exists()
            self.return_msg = 'Move OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} Moving {self.name} in {plTg.playlist.name} :thumbs_down:'
        await self.switch_to_idle()

    async def prepare_for_sort(self) -> None:
        self.current_sort = ''
        await self.switch_to_status((NameDurationStatus.SORTING, ))

    async def set_iorder(self) -> None:
        if self.current_sort[0] != u'\U0001F502' or len(self.current_sort) > 1:
            await self.set_iorder_do(int(self.current_sort) if self.current_sort[0] != u'\U0001F502' else self.get_iorder_from_index(int(self.current_sort[1:])))
            await self.switch_to_idle()

    async def add_to_sort(self, args) -> None:
        self.current_sort += f'{args[0]}'
        await self.edit_or_select()

    def get_iorder_from_index(self, index: int) -> int:
        p = cache_get(self.proc.user.rowid, self.pid)
        pis = p.get_items(deleted=False)
        if not index:
            return pis[0].item.iorder - 1
        elif index - 1 < len(pis):
            return pis[index - 1].item.iorder + 1
        else:
            return pis[-1].item.iorder + 1

    async def remove_from_sort(self) -> None:
        if self.current_sort:
            self.current_sort = self.current_sort[0:-1]
            await self.edit_or_select()

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.refresh_from_cache()
        if not self.deleted:
            if self.status == NameDurationStatus.IDLE:
                self.add_button(u'\U0001F5D1', self.delete_item_pre_pre, args=(CMD_SEEN, ))
                self.add_button(u'\U00002211', self.switch_to_status, args=(NameDurationStatus.SORTING, ))
                self.add_button(u'\U0001F517', self.switch_to_status, args=(NameDurationStatus.DOWNLOADING_WAITING, ))
                self.add_button(u'\U0001F4EE', self.switch_to_status, args=(NameDurationStatus.MOVING, ))
                if self.obj.takes_space():
                    self.add_button(u'\U0001F4A3', self.delete_item_pre_pre, args=(CMD_FREESPACE, ))
            elif self.status == NameDurationStatus.MOVING:
                self.input_field = u'\U0001F449'
                pps: List[PlaylistTg] = cache_get(self.proc.user.rowid)
                myself: PlaylistTg = cache_get(self.proc.user.rowid, self.obj.playlist)
                for pp in pps:
                    if pp.playlist.rowid != self.obj.playlist:
                        self.add_button(pp.playlist.name, self.move_to_do, args=(pp, myself))
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
            elif self.status == NameDurationStatus.DOWNLOADING_WAITING:
                self.input_field = u'\U0001F449'
                self.add_button('bestaudio', self.download_format, args=('bestaudio/best', 0))
                self.add_button('best', self.download_format, args=('best', 0))
                self.add_button('worstaudio', self.download_format, args=('worstaudio/worst', 0))
                self.add_button('worst', self.download_format, args=('worst', 0))
                if 'twitch.tv' in self.obj.link:
                    self.add_button('bestaudio os', self.download_format, args=('bestaudio/best', 4))
                    self.add_button('best os', self.download_format, args=('best', 4))
                    self.add_button('worstaudio os', self.download_format, args=('worstaudio/worst', 4))
                    self.add_button('worst os', self.download_format, args=('worst', 4))
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
            elif self.status == NameDurationStatus.DOWNLOADING:
                status = self.proc.processors['common'].status
                self.add_button(f':cross_mark: Abort {self.id}', self.stop_download, args=(self.id, ))
                if 'dlid' in status and status['dlid'] == self.id:
                    self.add_button(':cross_mark::cross_mark: Abort All', self.stop_download, args=(None, ))
                    upd = f'{escape(self.name)} downloading {"." * (self.sub_status & 0xFF)}'
                    if 'dl' in status and 'raw' in status['dl']:
                        dl = status['dl']['raw']
                        upd2 = ''
                        fi = self.dictget(dl, 'fragment_index', self.dictget(dl, 'downloaded_bytes'))
                        fc = self.dictget(dl, 'fragment_count', self.dictget(dl, 'total_bytes', self.dictget(dl, 'total_bytes_estimate')))
                        if isinstance(fi, (int, float)) and isinstance(fc, (int, float)):
                            no = int(round(30.0 * fi / fc))
                            upd2 += '[' + (no * 'o') + ((30 - no) * ' ') + '] '
                        fc = dl.get('speed')
                        if isinstance(fc, (int, float)):
                            upd2 += f'{self.sizeof_fmt(fc, "B/s")} '
                        fc = dl.get('downloaded_bytes')
                        if isinstance(fc, (int, float)):
                            upd2 += f'{self.sizeof_fmt(fc)}'
                        if upd2:
                            upd += '\n<code>' + upd2 + '</code>'
                else:
                    upd = f'{escape(self.name)} waiting in queue {"." * (self.sub_status & 0xFF)}'
                return upd
            elif self.status == NameDurationStatus.SORTING:
                for i in range(10):
                    self.add_button(f'{(i + 1) % 10}' + u'\U0000FE0F\U000020E3', self.add_to_sort, args=((i + 1) % 10, ))
                self.add_button(u'\U000002C2', self.remove_from_sort)
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
                if not self.current_sort:
                    self.add_button(u'\U0001F502', self.add_to_sort, args=(u'\U0001F502', ), new_row=True)
                else:
                    self.add_button(self.current_sort, self.set_iorder, new_row=True)
                self.input_field = f'Enter \U00002211 for {self.name}'
                return f'Enter \U00002211 for <b>{self.name}</b>'
        elif self.status == NameDurationStatus.IDLE:
            self.add_button(u'\U0000267B', self.delete_item_pre_pre, args=(CMD_SEEN, ))
            if self.obj.takes_space():
                self.add_button(u'\U0001F4A3', self.delete_item_pre_pre, args=(CMD_FREESPACE, ))
        upd = await super().update(context)
        if upd:
            return upd
        upd += f'<a href="{self.obj.link}">{self.index + 1})<b> {escape(self.name)}</b> - <i>Id {self.id}</i></a> :memo: {self.playlist_name}\n\U000023F1 {duration2string(self.secs)}\n\U000023F3: {self.obj.datepub}\n'
        if self.obj.conf and 'author' in self.obj.conf and self.obj.conf['author']:
            upd += f'\U0001F64B: {self.obj.conf["author"]}\n'
        upd += f'\U00002211: {self.obj.iorder}'
        mainlnk = f'{self.proc.params.link}/{self.proc.params.args["sid"]}'
        if 'twitch.tv' in self.obj.link:
            lnk = f'{mainlnk}/twi?'
            par = urlencode(dict(link=self.obj.link))
            upd += f'\n<a href="{lnk}{par}">\U0001F7E3 TWI</a>'
        if 'pageurl' in self.obj.conf:
            upd += f'\n<a href="{self.obj.conf["pageurl"]}">\U0001F4C3 Main</a>'
        if not self.obj.dl and self.obj.conf and isinstance(self.obj.conf, dict) and 'todel' in self.obj.conf and self.obj.conf['todel']:
            self.obj.dl = self.obj.conf['todel'][0]
        if isinstance(self.obj.conf, dict) and 'sec' in self.obj.conf:
            upd += f'\n\U000025B6 {duration2string(int(self.obj.conf["sec"]))}'
        if self.obj.dl and exists(self.obj.dl) and isfile(self.obj.dl):
            sta = stat(self.obj.dl)
            upd += f'\n<a href="{mainlnk}/dl/{self.proc.user.token}/{self.id}">DL {self.sizeof_fmt(sta.st_size) if sta else ""}</a>'
        # upd += f'<tg-spoiler><pre>{json.dumps(self.obj.conf, indent=4)}</pre></tg-spoiler>'
        if self.return_msg:
            upd += f'\n<b>{self.return_msg}</b>'
        elif self.deleted:
            upd = f'<s>{upd}</s>'
        return upd

    async def delete_item_do(self):
        if self.del_action == CMD_SEEN:
            pl = PlaylistMessage(CMD_SEEN, playlistitem=self.id, seen=not self.deleted)
            pl = await self.proc.process(pl)
            if pl.rv == 0:
                self.deleted = not self.deleted
                self.obj.seen = not self.obj.seen
                cache_on_item_deleted(self.proc.user.rowid, self.pid)
                plTg = cache_get(self.proc.user.rowid, self.pid)
                if plTg.message:
                    await plTg.message.edit_or_select_items(5)
                    await plTg.message.edit_or_select_if_exists(5)
                self.return_msg = ('Delete' if self.deleted else 'Restore') + ' OK :thumbs_up:'
            else:
                self.return_msg = f'Error {pl.rv} {"deleting" if not self.deleted else "restoring"} {self.name} :thumbs_down:'
        elif self.del_action == CMD_FREESPACE:
            pl = PlaylistMessage(CMD_FREESPACE, playlistitem=self.id)
            pl = await self.proc.process(pl)
            if pl.rv == 0:
                self.obj = pl.playlistitem
                itemTg = cache_get_item(self.proc.user.rowid, self.obj.playlist, self.id)
                itemTg.refresh(pl.playlistitem, itemTg.index)
                self.return_msg = f'Free Space OK (deleted files: {pl.deleted}):thumbs_up:'
            else:
                self.return_msg = f'Error {pl.rv} freeing space of {self.name} :thumbs_down:'

    async def set_iorder_do(self, iorder):
        pl = PlaylistMessage(CMD_IORDER, playlistitem=self.id, iorder=iorder)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            cache_store(pl.playlist)
            plTg = cache_get(self.proc.user.rowid, self.pid)
            if plTg.message:
                await plTg.message.edit_or_select_items()
                await plTg.message.edit_or_select_if_exists()
            self.return_msg = 'IOrder OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} IOrdering {self.name} :thumbs_down:'


class PlaylistTMessage(NameDurationTMessage, RefreshingTMessage):
    def refresh_from_cache(self):
        obj = cache_get(self.proc.user.rowid, self.id)
        if obj:
            self.obj = obj.playlist
            obj.message = self
            self.index = obj.index
            self.name = self.obj.name
            img = None
            self.unseen = 0
            for pli in self.obj.items:
                if not pli.seen:
                    self.unseen += 1
                    if not img:
                        img = pli.img
            self.secs = self.obj.get_duration()
            self.thumb = img
            self.deleted = False
            return True
        else:
            return False

    def __init__(self, navigation: NavigationHandler, myid: int = None, user: User = None, params: object = None, **argw) -> None:
        super().__init__(
            navigation,
            myid=myid,
            user=user,
            params=params)
        self.del_and_recreate = False
        self.set_playlist(self.obj)

    async def edit_or_select_items(self, delay: float = 0):
        itemsTg = cache_get_items(self.proc.user.rowid, self.id, True)
        for itemTg in itemsTg:
            if itemTg.message:
                await itemTg.message.edit_or_select_if_exists(delay)

    async def delete_item_do(self):
        if self.del_action == CMD_DEL:
            pl = PlaylistMessage(CMD_DEL, playlist=self.id)
            pl = await self.proc.process(pl)
            if pl.rv == 0:
                self.deleted = True
                await self.navigation.delete_message(self.message_id)
                itemsTg = cache_get_items(self.proc.user.rowid, self.id, True)
                for itTg in itemsTg:
                    if itTg.message:
                        await self.navigation.delete_message(itTg.message.message_id)
                cache_del(self.obj)
                plsTg: List[PlaylistTg] = cache_get(self.proc.user.rowid)
                for plTg in plsTg:
                    if plTg.message:
                        await plTg.message.edit_or_select_if_exists()
                lmm = self.navigation._menu_queue[-1]
                if isinstance(lmm, PlaylistItemsPagesTMessage) and\
                        lmm.playlist_obj.id == self.id:
                    await self.navigation.goto_back()
                lmm = self.navigation._menu_queue[-1]
                if isinstance(lmm, PlaylistsPagesTMessage):
                    await self.navigation.goto_menu(lmm, None, add_if_present=False)
                self.return_msg = 'Delete OK :thumbs_up:'
            else:
                self.return_msg = f'Error {pl.rv} deleting {self.name} :thumbs_down:'
        else:
            pl = PlaylistMessage(CMD_CLEAR, playlist=self.id)
            pl = await self.proc.process(pl)
            if pl.rv == 0:
                for pli in self.obj.items:
                    if not pli.seen:
                        pli.seen = True
                itemsTg = cache_get_items(self.proc.user.rowid, self.id, True)
                for itemTg in itemsTg:
                    if itemTg.message:
                        itemTg.message.deleted = True
                        itemTg.message.obj.seen = True
                plTg: PlaylistTg = cache_get(self.proc.user.rowid, self.id)
                plTg.refresh(plTg.playlist, plTg.index)
                self.return_msg = 'Clear OK :thumbs_up:'
                self.status = NameDurationStatus.RETURNING_IDLE
                await self.edit_or_select_items()
                await self.edit_or_select_if_exists()
            else:
                self.return_msg = f'Error {pl.rv} clearing {self.name} :thumbs_down:'

    async def rename_playlist_2(self, newname):
        pl = PlaylistMessage(CMD_REN, playlist=self.id, to=newname)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.obj.name = self.name = newname
            lmm = self.navigation._menu_queue[-1]
            if isinstance(lmm, PlaylistsPagesTMessage):
                await self.navigation.goto_menu(lmm, None, add_if_present=False)
            self.return_msg = 'Rename OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} renaming {self.name} :thumbs_down:'

    def sort_playlist(self):
        asyncio.get_event_loop().create_task(self.sort_playlist_1())

    async def switch_to_idle_end(self):
        if self.del_and_recreate:
            self.del_and_recreate = False
            await self.send()
        else:
            await super().switch_to_idle_end()

    async def sort_playlist_1(self):
        self.status = NameDurationStatus.SORTING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id=f"long_operation_do{self.label}",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = PlaylistMessage(CMD_SORT, playlist=self.id)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            cache_store(pl.playlist)
            await self.edit_or_select_items()
            self.del_and_recreate = True
            self.return_msg = 'Sort OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} sorting {self.name} :thumbs_down:'
        await self.switch_to_idle()

    async def on_refresh_finish(self, pl: PlaylistMessage):
        self.del_and_recreate = True
        lmm = self.navigation._menu_queue[-1]
        if isinstance(lmm, PlaylistsPagesTMessage) or\
           (isinstance(lmm, PlaylistItemsPagesTMessage) and lmm.playlist_obj.id == self.id):
            await self.navigation.goto_menu(lmm, None, add_if_present=False)
        await self.edit_or_select_items()
        await self.switch_to_idle()

    async def on_refresh_abort(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.switch_to_idle()

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.RENAMING:
            text = text.strip()
            if re.match(r'^[0-9a-zA-Z_\-]+$', text):
                await self.rename_playlist_2(text)
                await self.switch_to_idle()
        else:
            await super().text_input(text, context)

    async def list_items(self, args, context):
        p = PlaylistItemsPagesTMessage(self.navigation, deleted=args[0], user=self.proc.user, params=self.proc.params, playlist_obj=self)
        if self.navigation._menu_queue and isinstance(self.navigation._menu_queue[-1], PlaylistItemsPagesTMessage):
            await self.navigation.goto_back()
        await self.navigation.goto_menu(p, context)
        if p.first_page.groups:
            grp = p.first_page.groups[0]
            await p.goto_group((grp,), context)

    async def edit_me(self, context=None):
        cls = None
        if self.obj.type == 'youtube':
            cls = YoutubeDLPlaylistTMessage
        elif self.obj.type == 'mediaset':
            cls = MediasetPlaylistTMessage
        elif self.obj.type == 'rai':
            cls = RaiPlaylistTMessage
        elif self.obj.type == 'localfolder':
            cls = LocalFolderPlaylistTMessage

        if cls:
            but = cls(
                self.navigation,
                user=self.proc.user,
                params=self.proc.params,
                playlist=self.obj)
            await self.navigation.goto_menu(but)

    @staticmethod
    def list_items_taking_space(it: PlaylistItem) -> bool:
        return it.takes_space()

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.refresh_from_cache()
        lnk = f'{self.proc.params.link}/{self.proc.params.args["sid"]}'
        if not self.deleted:
            if self.status == NameDurationStatus.IDLE:
                self.add_button(u'\U00002699', self.edit_me)
                self.add_button(u'\U000000AB\U000000BB', self.switch_to_status, args=(NameDurationStatus.RENAMING, ))
                self.add_button(u'\U0001F5D1', self.switch_to_status, args=(NameDurationStatus.DELETING_CONFIRM, ))
                self.add_button(u'\U0001F9F9', self.delete_item_pre_pre, args=(CMD_CLEAR, ))
                self.add_button(u'\U0001F501', self.switch_to_status, args=(NameDurationStatus.UPDATING_INIT, ))
                self.add_button(u'\U00002211', self.sort_playlist)
                self.add_button(':play_button:', btype=ButtonType.LINK, web_app_url=f'{lnk}-s/play/workout.htm?{urlencode(dict(name=self.name))}')
                self.add_button(u'\U0001F4D2', btype=ButtonType.LINK, web_app_url=f'{lnk}-s/index.htm?{urlencode(dict(pid=self.id))}')
                self.add_button(':memo:', self.list_items, args=(False, ))
                self.add_button(':eye:', self.list_items, args=(True, ))
                self.add_button(u'\U0001F4A3', self.list_items, args=(PlaylistTMessage.list_items_taking_space, ))
                # self.add_button(':play_button:', btype=ButtonType.LINK, web_app_url=f'{self.proc.params.link}/{self.proc.params.args["sid"]}-s/play/workout.htm?{urlencode(dict(name=self.name))}')
            elif self.status == NameDurationStatus.RENAMING:
                self.input_field = f'Enter new name for {self.name}'
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
                return f'Enter new name for <b>{self.name}</b>'
            elif self.status == NameDurationStatus.DELETING_CONFIRM:
                self.input_field = u'\U0001F449'
                self.add_button('\U00002705 Yes', self.delete_item_pre_pre, args=(CMD_DEL, ))
                self.add_button(':cross_mark: No', self.switch_to_idle)
                return f'Are you sure to delete <b>{self.name}</b>?'
            elif self.status == NameDurationStatus.SORTING:
                self.input_field = u'\U0001F570'
                return f'{self.name} sorting {"." * (self.sub_status & 0xFF)}'
            else:
                updt = await DeletingTMessage.update(self, context)
                if updt:
                    return updt
                updt = await RefreshingTMessage.update(self, context)
                if updt:
                    return updt
        datepubo = datetime.fromtimestamp(int(self.obj.dateupdate / 1000))
        upd = f'{self.index + 1}) <b>{self.name}</b> - <i>Id {self.id}</i>'
        if self.obj.type == 'youtube':
            upd += '\U0001F534'
        elif self.obj.type == 'rai':
            upd += '\U0001F535'
        elif self.obj.type == 'mediaset':
            upd += '\U00002B24'
        upd += f'\nLength: {self.unseen} \U000023F1 {duration2string(self.obj.get_duration())}\n'
        upd += f':eye: {len(self.obj.items)} \U000023F1 {duration2string(self.obj.get_duration(True))}\n'
        upd += f'Update \U000023F3: {datepubo.strftime("%Y-%m-%d %H:%M:%S")} ' + ("\U00002705" if self.obj.autoupdate else "") + '\n'
        par = urlencode(dict(name=self.name, host=lnk))
        uprefix: str = f'{lnk}/m3u/{self.proc.user.token}?{par}&'
        upd += f'<a href="{uprefix}fmt=m3u">M3U8</a>, <a href="{uprefix}fmt=ely">ELY</a>, <a href="{uprefix}fmt=json">JSON</a>\n'
        upd += f'<a href="{uprefix}fmt=m3u&conv=4">M3U8c4</a>, <a href="{uprefix}fmt=ely&conv=4">ELYc4</a>, <a href="{uprefix}fmt=json&conv=4">JSONc4</a>\n'
        upd += f'<a href="{uprefix}fmt=m3u&conv=2">M3U8c2</a>, <a href="{uprefix}fmt=ely&conv=2">ELYc2</a>, <a href="{uprefix}fmt=json&conv=2">JSONc2</a>'
        # upd += f'<tg-spoiler><pre>{json.dumps(self.obj.conf, indent=4)}</pre></tg-spoiler>'
        if self.return_msg:
            upd += f'\n<b>{self.return_msg}</b>'
        elif self.deleted:
            upd = f'<s>{upd}</s>'
        return upd


class GroupOfNameDurationItems(object):

    def __init__(self):
        self.items: List[NameDurationTMessage] = []
        self.start_item = -1
        self.stop_item = -1

    def is_valid(self):
        return self.start_item >= 0 and self.stop_item >= 0

    def add_item(self, item):
        if not self.items:
            self.start_item = item.index
        self.items.append(item)
        self.stop_item = item.index

    def get_label(self):
        if self.start_item == self.stop_item:
            beginning = f'{self.start_item + 1}) {self.items[0].name}'
            if len(beginning) > 70:
                beginning = beginning[0:70] + '...'
            return f'{beginning} ({duration2string(self.items[0].secs)})'
        else:
            return f'{self.start_item + 1} - {self.stop_item + 1}'


class MultipleGroupsOfItems(object):

    def __init__(self):
        self.start_item: int = -1
        self.stop_item: int = -1
        self.next_page: MultipleGroupsOfItems = None
        self.back_page: MultipleGroupsOfItems = None
        self.groups: List[GroupOfNameDurationItems] = []
        self.first_item_index: int = -1
        self.last_item_index: int = -1

    def is_valid(self):
        return self.start_item >= 0 and self.stop_item >= 0

    def set_start_stop(self, sta: int, sto: int):
        self.start_item = sta
        self.stop_item = sto

    def set_first_last(self, sta: int, sto: int):
        self.first_item_index = sta
        self.last_item_index = sto

    def get_next_page(self):
        return self.next_page

    def add_group(self, grp):
        if not self.groups:
            self.start_item = grp.start_item
        self.stop_item = grp.stop_item
        self.groups.append(grp)

    def set_back_page(self, val):
        self.back_page = val

    def get_label(self):
        if self.start_item == self.stop_item:
            return f'{self.start_item + 1}'
        else:
            return f'{self.start_item + 1} - {self.stop_item + 1}'


class PageGenerator(object):
    def __init__(self, user: User, params) -> None:
        self.proc = ProcessorMessage(user, params)

    @abstractmethod
    def item_convert(self, myid, navigation, **kwargs) -> NameDurationTMessage:
        return

    @abstractmethod
    async def get_items_list(self, deleted=False, **kwargs) -> List[Union[Playlist, PlaylistItem]]:
        return


class PlaylistsPagesGenerator(PageGenerator):

    def item_convert(self, myid, navigation, **_):
        plTg = cache_get(self.proc.user.rowid, myid)
        return plTg.message if plTg and plTg.message and plTg.message.refresh_from_cache() else\
            PlaylistTMessage(navigation, myid, self.proc.user, self.proc.params)

    def get_playlist_message(self, pid=None, deleted=False):
        return PlaylistMessage(CMD_DUMP, useri=self.proc.user.rowid, load_all=1 if deleted else 0, playlist=pid)

    async def get_items_list(self, deleted=False, pid=None):
        plout = await self.proc.process(self.get_playlist_message(pid, deleted))
        cache_del_user(self.proc.user.rowid, plout.playlists)
        return plout.playlists


class PlaylistItemsPagesGenerator(PageGenerator):
    def __init__(self, user: User, params, pid):
        super().__init__(
            user,
            params
        )
        self.pid = pid

    def item_convert(self, myid, navigation):
        itTg = cache_get_item(self.proc.user.rowid, self.pid, myid)
        return itTg.message if itTg and itTg.message and itTg.message.refresh_from_cache() else\
            PlaylistItemTMessage(
                navigation,
                myid=myid,
                user=self.proc.user,
                params=self.proc.params,
                pid=self.pid)

    async def get_items_list(self, deleted=False):
        itemsTg = cache_get_items(self.proc.user.rowid, self.pid, deleted)
        rv = []
        for itTg in itemsTg:
            rv.append(itTg.item)
        return rv


class YesNoTMessage(BaseMessage):
    def __init__(self, navigation: NavigationHandler, labelYes: str, labelNo: str, inputField: str = 'Are you sure?', argsYes=None, argsNo=None) -> None:
        super().__init__(
            navigation,
            self.__class__.__name__,
            expiry_period=timedelta(minutes=30),
            input_field=inputField)
        self.yes_btn = labelYes
        self.no_btn = labelNo
        self.yes_args = argsYes
        self.no_args = argsNo

    async def on_no(self, _: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.navigation.goto_back()

    @abstractmethod
    async def on_yes(self, _: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        pass

    def update(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> str:
        self.add_button(self.yes_btn, self.on_yes, args=self.yes_args)
        self.add_button(self.no_btn, self.on_no, args=self.no_args)
        return self.input_field


class SignOutTMessage(YesNoTMessage):
    def __init__(self, navigation: NavigationHandler) -> None:
        super().__init__(navigation, '\U00002705\U0001F6AA', ':cross_mark:\U0001F6AA')

    async def on_yes(self, _: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.navigation._menu_queue[0].sign_out(_)


class ListPagesTMessage(BaseMessage):

    def __init__(self, update_str: str, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, pagegen: PageGenerator = None, firstpage: Optional[MultipleGroupsOfItems] = None, deleted=False, input_field=None) -> None:
        super().__init__(
            navigation,
            self.__class__.__name__ + f'_{self.get_label_addition()}_' + ('00' if not firstpage else firstpage.get_label()),
            expiry_period=timedelta(hours=2),
            input_field=input_field,
            inlined=False,
            home_after=False,
        )
        self.max_items_per_group = max_items_per_group
        self.max_group_per_page = max_group_per_page
        self.update_str = update_str
        self.first_page = firstpage
        self.deleted = deleted
        self.pagegen = pagegen
        self.sel_players: Dict[str, PlayerInfoMessage] = None

    def get_label_addition(self):
        return ''

    async def put_items_in_pages(self):
        try:
            items = await self.pagegen.get_items_list(self.deleted)
            nitems = len(items)
            self.first_page = thispage = MultipleGroupsOfItems()
            if nitems:
                last_group_items = nitems % self.max_items_per_group
                ngroups = int(nitems / self.max_items_per_group) + (1 if last_group_items else 0)
                if not last_group_items:
                    last_group_items = self.max_items_per_group
                last_page_groups = ngroups % self.max_group_per_page
                npages = int(ngroups / self.max_group_per_page) + (1 if last_page_groups else 0)
                if not last_page_groups:
                    last_page_groups = self.max_group_per_page
                first_item_index = None
                last_item_index = None
                pages: List[MultipleGroupsOfItems] = []
                oldpage = None
                current_item = 0
                for i in range(npages):
                    groups_of_this_page = last_page_groups if i == npages - 1 else self.max_group_per_page
                    for j in range(groups_of_this_page):
                        items_of_this_group = last_group_items if i == npages - 1 and j == groups_of_this_page - 1 else self.max_items_per_group
                        group = GroupOfNameDurationItems()
                        for _ in range(items_of_this_group):
                            item = self.pagegen.item_convert(items[current_item].rowid, self.navigation)
                            group.add_item(item)
                            current_item += 1
                            if current_item == 1:
                                first_item_index = item.index
                            last_item_index = item.index
                        thispage.add_group(group)
                    thispage.set_back_page(oldpage)
                    oldpage = thispage
                    pages.append(thispage)
                    thispage = oldpage.next_page = MultipleGroupsOfItems()
                for p in pages:
                    p.set_first_last(first_item_index, last_item_index)
        except Exception:
            _LOGGER.error(traceback.format_exc())

    async def goto_index(self, index, context=None):
        basepage = self.first_page
        while basepage.back_page:
            basepage = basepage.back_page
        current = 0
        while basepage:
            for g in basepage.groups:
                for _ in g.items:
                    if current == index:
                        await self.goto_group((g,), context)
                        return
                    current += 1
            basepage = basepage.next_page

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        try:
            val = int(text.strip())
        except Exception:
            val = -1
        if val > 0:
            await self.goto_index(val - 1, context)

    async def goto_page(self, args, context=None):
        page, = args
        self.first_page = page
        await self.navigation.goto_menu(self, context, add_if_present=False)

    async def goto_group(self, args, context=None):
        group: GroupOfNameDurationItems = args[0]
        for item in group.items:
            try:
                await item.send(context)
            except Exception:
                _LOGGER.error(f'goto_group error {traceback.format_exc()}')
        self.is_alive()

    def soft_refresh(self):
        basepage = self.first_page
        while basepage.back_page:
            basepage = basepage.back_page
        while basepage:
            for g in basepage.groups:
                for it in g.items:
                    if not it.refresh_from_cache():
                        self.first_page = None
                        return False
            basepage = basepage.next_page
        return True

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        if not self.first_page or not self.soft_refresh():
            await self.put_items_in_pages()
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        if self.first_page:
            self.input_field = f'{self.first_page.first_item_index + 1} - {self.first_page.last_item_index + 1}'\
                if self.first_page.last_item_index != self.first_page.first_item_index else\
                (f'{self.first_page.first_item_index + 1}' if self.first_page.groups else u'\U00002205')
            for grp in self.first_page.groups:
                label = grp.get_label()
                self.add_button(label, self.goto_group, args=(grp,))
            new_row = True
            if self.first_page.back_page:
                self.add_button(f':arrow_left: {self.first_page.back_page.get_label()}', self.goto_page, args=(self.first_page.back_page, ), new_row=new_row)
                new_row = False
            if self.first_page.next_page and self.first_page.next_page.is_valid():
                self.add_button(f'{self.first_page.next_page.get_label()} :arrow_right:', self.goto_page, args=(self.first_page.next_page, ), new_row=new_row)
        else:
            self.input_field = u'\U00002205'
        if self.sel_players is None:
            _, self.sel_players = PlayerListMessage.user_conf_field_to_players_dict(
                self.navigation,
                self.pagegen.proc,
                True)
        new_row = True
        for pi, pim in self.sel_players.items():
            self.add_button(label=u"\U0001F3A6 " + pi, callback=pim, new_row=new_row)
            new_row = False
        return self.update_str


class PlaylistsPagesTMessage(ListPagesTMessage):

    def __init__(self, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, firstpage=None, deleted=False, user=None, params=None) -> None:
        super().__init__(
            update_str=f'List of <b>{user.username}</b> playlists',
            navigation=navigation,
            max_items_per_group=max_items_per_group,
            max_group_per_page=max_group_per_page,
            firstpage=firstpage,
            deleted=deleted,
            pagegen=PlaylistsPagesGenerator(
                user,
                params
            ),
            input_field='Select Playlist'
        )

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        updstr = await super().update(context)
        self.add_button(label=u"\U0001F3E0 Home", callback=self.navigation.goto_home, new_row=True)
        return updstr


class PlaylistItemsPagesTMessage(ListPagesTMessage):

    def __init__(self, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, firstpage=None, deleted=False, user=None, params=None, playlist_obj: Optional[PlaylistTMessage] = None) -> None:
        self.playlist_obj = playlist_obj
        super().__init__(
            update_str=f'List of <b>{playlist_obj.name}</b> items ({playlist_obj.unseen} - \U000023F1 {duration2string(playlist_obj.obj.get_duration())})',
            navigation=navigation,
            max_items_per_group=max_items_per_group,
            max_group_per_page=max_group_per_page,
            firstpage=firstpage,
            deleted=deleted,
            pagegen=PlaylistItemsPagesGenerator(
                user,
                params,
                playlist_obj.id
            )
        )

    def get_label_addition(self):
        return f'{self.playlist_obj.id}'

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        updstr = await super().update(context)
        self.add_button(label=u"\U0001F519", callback=self.navigation.goto_back, new_row=True)
        self.add_button(label=u"\U0001F3E0 Home", callback=self.navigation.goto_home)
        return updstr


class ChangeOrderedOrDeleteOrCancelTMessage(BaseMessage):
    def __init__(self, navigation: NavigationHandler, playlist: Playlist, plinfo: object) -> None:
        super().__init__(
            navigation,
            self.__class__.__name__,
            input_field=plinfo["title"])
        self.playlist = playlist
        self.plinfo = plinfo

    async def toggle_ordered(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        self.plinfo["ordered"] = not self.plinfo["ordered"]
        await self.navigation.goto_menu(self, context, add_if_present=False)

    async def remove(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        for i in range(len(self.playlist.conf['playlists'])):
            p = self.playlist.conf['playlists'][i]
            if p["id"] == self.plinfo["id"]:
                del self.playlist.conf['playlists'][i]
                break
        await self.navigation.goto_back()

    async def update(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = self.plinfo["title"]
        self.add_button('Ordered: ' + ("\U00002611" if self.plinfo["ordered"] else "\U00002610"), self.toggle_ordered, new_row=True)
        self.add_button('Remove: \U0001F5D1', self.remove, new_row=True)
        self.add_button('OK: \U0001F197', self.navigation.goto_back, new_row=True)
        return f'{self.plinfo["title"]} modify'


class PlaylistNamingTMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        self.playlist = playlist
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field='\U0001F50D Playlist link or id' if self.playlist.name else 'Enter Playlist Name',
            user=user,
            params=params)
        if not self.playlist.name:
            self.status = NameDurationStatus.NAMING

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.NAMING:
            text = text.strip()
            if re.match(r'^[0-9a-zA-Z_\-]+$', text):
                self.playlist.name = text
                self.return_msg = f':thumbs_up: New name {text}'
                await self.switch_to_idle()
            else:
                self.return_msg = f':thumbs_down: Invalid name {text}. Please try again'

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        if self.status == NameDurationStatus.NAMING:
            self.input_field = 'Enter Playlist Name'
            if self.playlist.name:
                self.add_button(':cross_mark: Abort Naming', self.switch_to_status, args=(NameDurationStatus.IDLE, ))
            else:
                self.add_button(':cross_mark: Abort', self.navigation.goto_back)
        else:
            self.input_field = '\U0001F50D Playlist link or id'


class YoutubeDLPlaylistTMessage(PlaylistNamingTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        if not playlist:
            playlist = Playlist(
                type='youtube',
                useri=user.rowid,
                autoupdate=False,
                dateupdate=0,
                conf=dict(playlists=[], play=dict()))
        super().__init__(
            navigation,
            user=user,
            params=params,
            playlist=playlist)
        self.checking_playlist = ''
        for p in playlist.conf['playlists']:
            p['ordered'] = p.get('ordered', True)

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.IDLE:
            text = text.strip()
            if text:
                self.checking_playlist = text
                asyncio.create_task(self.check_playlist(text))
        else:
            await super().text_input(text, context)

    async def check_playlist(self, text):
        self.status = NameDurationStatus.DOWNLOADING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="check_playlist",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = PlaylistMessage(CMD_YT_PLAYLISTCHECK, text=text)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            plinfo = pl.playlistinfo
            add = True
            for p in self.playlist.conf['playlists']:
                if p["id"] == plinfo["id"]:
                    self.return_msg = f'\U0001F7E1 {plinfo["title"]} already present!'
                    add = False
                    break
            if add:
                plinfo["ordered"] = True
                self.return_msg = f':thumbs_up: ({plinfo["title"]} - {plinfo["id"]})'
                self.playlist.conf['playlists'].append(plinfo)
        else:
            self.return_msg = f'Error {pl.rv} with playlist {text} :thumbs_down:'
        await self.switch_to_idle()

    async def toggle_autoupdate(self, context: Optional[CallbackContext] = None):
        self.playlist.autoupdate = not self.playlist.autoupdate
        await self.edit_or_select(context)

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        upd = ''
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        await PlaylistNamingTMessage.update(self, context)
        if self.status == NameDurationStatus.IDLE:
            self.input_field = '\U0001F50D Playlist link or id'
            self.add_button(f'Name: {self.playlist.name}', self.switch_to_status, args=(NameDurationStatus.NAMING, ), new_row=True)
            self.add_button('AutoUpdate: ' + ("\U00002611" if self.playlist.autoupdate else "\U00002610"), self.toggle_autoupdate)
            new_row = True
            if self.playlist.conf['playlists']:
                for p in self.playlist.conf['playlists']:
                    self.add_button(('\U00002B83 ' if p["ordered"] else '') + p["title"], ChangeOrderedOrDeleteOrCancelTMessage(self.navigation, playlist=self.playlist, plinfo=p), new_row=True)
                self.add_button(u'\U0001F501', RefreshNewPlaylistTMessage(
                    self.navigation,
                    user=self.proc.user,
                    params=self.proc.params,
                    playlist=self.playlist
                ), new_row=True)
                new_row = False
            self.add_button(':cross_mark: Abort', self.navigation.goto_back, new_row=new_row)
        elif self.status == NameDurationStatus.DOWNLOADING:
            self.input_field = u'\U0001F570'
            upd = f'{escape(self.checking_playlist)} finding playlist info {"." * (self.sub_status & 0xFF)}'
        if self.return_msg:
            upd = f'<b>{self.return_msg}</b>'
        return upd if upd else self.input_field


class LocalFolderPlaylistTMessage(PlaylistNamingTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        if not playlist:
            playlist = Playlist(
                type='localfolder',
                useri=user.rowid,
                autoupdate=False,
                dateupdate=0,
                conf=dict(playlists=dict(), folders=dict(), play=dict()))
        super().__init__(
            navigation,
            user=user,
            params=params,
            playlist=playlist)
        self.listings_changed = False
        self.listings_done = False

    def get_listings_command(self):
        return PlaylistMessage(CMD_FOLDER_LIST)

    async def listing_refresh_1(self, cmd, context):
        self.status = NameDurationStatus.LISTING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="listing_refresh",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = await self.proc.process(cmd)
        if pl.rv == 0:
            self.playlist.conf['folders'] = pl.folders
            self.listings_changed = True
            self.return_msg = ''
        else:
            self.return_msg = f'Error {pl.rv} listing folders :thumbs_down:'
        await self.switch_to_idle()

    async def listings_refresh(self, context: Optional[CallbackContext] = None):
        if self.status == NameDurationStatus.IDLE:
            self.playlist.conf['folders'] = dict()
            cmd = self.get_listings_command()
            asyncio.create_task(self.listing_refresh_1(cmd, context))

    async def toggle_autoupdate(self, context: Optional[CallbackContext] = None):
        self.playlist.autoupdate = not self.playlist.autoupdate
        await self.edit_or_select(context)

    async def toggle_playlist(self, args, context: Optional[CallbackContext] = None):
        pid = args[0]
        if pid in self.playlist.conf['playlists']:
            del self.playlist.conf['playlists'][pid]
        else:
            self.playlist.conf['playlists'][pid] = self.playlist.conf['folders'][pid]
        await self.edit_or_select(context)

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        upd = ''
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        await PlaylistNamingTMessage.update(self, context)
        if self.status == NameDurationStatus.IDLE:
            self.input_field = '\U0001F50D Select folder'
            self.add_button(f'Name: {self.playlist.name}', self.switch_to_status, args=(NameDurationStatus.NAMING, ), new_row=True)
            self.add_button('AutoUpdate: ' + ("\U00002611" if self.playlist.autoupdate else "\U00002610"), self.toggle_autoupdate)
            self.add_button('Refresh Listings', self.listings_refresh)
            new_row = True
            foldd = self.playlist.conf['folders']
            playd = self.playlist.conf['playlists']
            if foldd:
                n_ok: int = 0
                for pid, p in playd.copy().items():
                    sel = pid in foldd
                    if not sel:
                        del playd[pid]
                for pid, p in foldd.items():
                    sel = pid in playd
                    self.add_button(("\U00002611 " if sel else "\U00002610 ") + p["title"], self.toggle_playlist, args=(pid, ), new_row=True)
                    if sel:
                        n_ok += 1
                if n_ok:
                    self.add_button(u'\U0001F501', RefreshNewPlaylistTMessage(
                        self.navigation,
                        user=self.proc.user,
                        params=self.proc.params,
                        playlist=self.playlist
                    ), new_row=True)
                    new_row = False
            elif not self.listings_done:
                self.listings_done = True
                await self.listings_refresh()
            self.add_button(':cross_mark: Abort', self.navigation.goto_back, new_row=new_row)
            if self.listings_changed:
                upd = 'Available folders:\n'
                self.listings_changed = False
                for f in self.playlist.conf['folders']:
                    upd += f['title'] + '\r\n'
        elif self.status == NameDurationStatus.LISTING:
            self.input_field = u'\U0001F570'
            return f'Downloading listings {"." * (self.sub_status & 0xFF)}'
        if self.return_msg:
            upd = f'<b>{self.return_msg}</b>'
        return upd if upd else self.input_field


class SubBrandSelectTMessage(BaseMessage):
    def __init__(self, navigation: NavigationHandler, playlist: Playlist = None) -> None:
        self.playlist = playlist
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field=f'Select content for {playlist.conf["brand"]["title"]}')
        self.compute_id_map()

    def compute_id_map(self):
        self.id_map = dict()
        for i, b in enumerate(self.playlist.conf['subbrands_all']):
            self.id_map[str(b['id'])] = i + 1

    def get_brand_index(self, brand):
        return self.id_map.get(str(brand['id']), 0)

    async def toggle_selected(self, args, context):
        subid, = args
        found = False
        for i in range(len(self.playlist.conf['subbrands'])):
            b = self.playlist.conf['subbrands'][i]
            if b['id'] == subid:
                del self.playlist.conf['subbrands'][i]
                found = True
                break
        if not found:
            for b in self.playlist.conf['subbrands_all']:
                if b['id'] == subid:
                    self.playlist.conf['subbrands'].append(b)
                    break
        await self.navigation.goto_menu(self, context, add_if_present=False)

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = f'Select content for {self.playlist.conf["brand"]["title"]}'
        for b in self.playlist.conf['subbrands_all']:
            subid = b["id"]
            subchk = False
            for b2 in self.playlist.conf['subbrands']:
                if b2['id'] == subid:
                    subchk = True
                    break
            self.add_button(f"[{self.get_brand_index(b)}] {b['title']} - {b['desc']}" + (" \U00002611" if subchk else " \U00002610"), self.toggle_selected, args=(b['id'], ), new_row=True)
        self.add_button('OK: \U0001F197', self.navigation.goto_back, new_row=True)
        return self.input_field


class SelectDayTMessage(BaseMessage):
    def __init__(self, navigation: NavigationHandler, playlist: Playlist = None) -> None:
        self.playlist = playlist
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field='Select day of listing')

    def nearest_weekday(self, weekday):
        d2 = datetime.now()
        v = -1
        sum = 0
        while True:
            if weekday == d2.weekday():
                return d2
            v *= -1
            if v > 0:
                sum += 1
            d2 = datetime.now() + timedelta(days=sum * v)
        return 0

    async def select_day(self, args, context):
        day, = args
        self.playlist.conf['listings_command'] = dict(datestart=int(self.nearest_weekday(day).replace(hour=0, minute=0, second=1).timestamp() * 1000))
        await self.navigation.goto_back()

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = 'Select day of listing'
        d = self.nearest_weekday(0)
        for _ in range(7):
            self.add_button(f'{d:%a}', self.select_day, args=(d.weekday(), ))
            d += timedelta(days=1)
        return self.input_field


class MedRaiPlaylistTMessage(PlaylistNamingTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None, playlist_type: str = None) -> None:
        if not playlist:
            playlist = Playlist(
                type=playlist_type,
                useri=user.rowid,
                autoupdate=False,
                dateupdate=0,
                conf=dict(brand=dict(id=None, desc=None, title=None), subbrands=[], subbrands_all=[], listings_command=None, play=dict()))
        else:
            if 'subbrands_all' not in playlist.conf:
                playlist.conf['subbrands_all'] = []
            playlist.conf['listings_command'] = None
        if not playlist.conf['subbrands_all'] and playlist.conf['subbrands']:
            playlist.conf['subbrands_all'] = playlist.conf['subbrands'].copy()
        if 'title' not in playlist.conf['brand'] and playlist.conf['subbrands']:
            playlist.conf['brand']['title'] = playlist.conf['subbrands'][0]['title']
        super().__init__(
            navigation,
            user=user,
            params=params,
            playlist=playlist)
        self.listings_cache = []
        self.listings_filter = ''
        self.listings_changed = False

    @abstractmethod
    def get_listings_command(self):
        return

    @abstractmethod
    def get_subbrand_command(self):
        return

    async def toggle_autoupdate(self, context: Optional[CallbackContext] = None):
        self.playlist.autoupdate = not self.playlist.autoupdate
        await self.edit_or_select(context)

    async def listing_refresh_1(self, cmd, context):
        self.status = NameDurationStatus.LISTING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="listing_refresh",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = await self.proc.process(cmd)
        if pl.rv == 0:
            self.listings_cache = pl.brands
            self.listings_changed = True
            self.return_msg = ''
        else:
            self.return_msg = f'Error {pl.rv} finding listings :thumbs_down:'
        await self.switch_to_idle()

    async def get_listings_command_params(self):
        return

    async def listings_refresh(self, context: Optional[CallbackContext] = None):
        if self.status == NameDurationStatus.IDLE:
            self.listings_cache = []
            self.playlist.conf['brand']['id'] = None
            self.playlist.conf['subbrands'] = []
            cmd = self.get_listings_command()
            self.playlist.conf['listings_command'] = None
            if not cmd:
                await self.get_listings_command_params()
                return
            asyncio.create_task(self.listing_refresh_1(cmd, context))

    def filter(self, title):
        if not self.listings_filter:
            return True
        else:
            title = title.lower()
            if title in self.listings_filter:
                return True
            else:
                ss = self.listings_filter.split(' ')
                for s in ss:
                    if s.lower() not in title:
                        return False
                return True

    def get_listings_text(self):
        txt = ''
        for i, b in enumerate(self.listings_cache):
            if len(txt) < 3900:
                if self.filter(b['title']):
                    txt += f'\n/brand_{i} {b["title"]} ({b["id"]})'
            else:
                return txt[1:] + '\n...'
        return txt[1:] if txt else f'No Listing{" for " + self.listings_filter if self.listings_filter else ""}'

    def download_subbrand(self):
        asyncio.create_task(self.download_subbrand_1())

    async def download_subbrand_1(self):
        self.status = NameDurationStatus.DOWNLOADING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="listing_refresh",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = await self.proc.process(self.get_subbrand_command())
        if pl.rv == 0:
            self.playlist.conf['subbrands_all'] = pl.brands
            self.playlist.conf['subbrands'] = []
            self.return_msg = ''
            if pl.brands:
                await self.navigation.goto_menu(SubBrandSelectTMessage(self.navigation, playlist=self.playlist))
            else:
                self.return_msg = 'No subbrand found'
        else:
            self.return_msg = f'Error {pl.rv} downloading subbrands :tumbs_down:'
        await self.switch_to_idle()

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, Coroutine[Any, Any, None]]:
        if self.status == NameDurationStatus.IDLE:
            if self.listings_cache:
                if (mo := re.search(r'^/brand_([0-9]+)$', text)):
                    self.playlist.conf['brand'] = self.listings_cache[int(mo.group(1))]
                    self.download_subbrand()
                elif (mo := re.search(r'^/brandid ([0-9a-zA-Z_\-]+)$', text)):
                    self.playlist.conf['brand'] = dict(
                        id=mo.group(1),
                        title=mo.group(1),
                        starttime=int(datetime.now().timestamp() * 1000)
                    )
                    self.download_subbrand()
                else:
                    self.listings_filter = text.strip()
                    self.listings_changed = True
                await self.edit_or_select()
        else:
            await super().text_input(text, context)

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        upd = ''
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        await PlaylistNamingTMessage.update(self, context)
        enteridle = False
        if enteridle or self.status == NameDurationStatus.IDLE:
            if self.listings_cache:
                self.input_field = f'\U0001F53B {self.listings_filter}' if self.listings_filter else '\U0001F53B Filter Listings'
            else:
                self.input_field = 'Please Click a Button'
                if not self.playlist.conf['brand']['id'] and self.get_listings_command():
                    await self.listings_refresh()
            self.add_button(f'Name: {self.playlist.name}', self.switch_to_status, args=(NameDurationStatus.NAMING, ), new_row=True)
            self.add_button('Refresh Listings', self.listings_refresh)
            new_row = True
            if self.playlist.conf['brand']['id']:
                self.add_button('AutoUpdate: ' + ("\U00002611" if self.playlist.autoupdate else "\U00002610"), self.toggle_autoupdate)
                if self.playlist.conf['subbrands_all']:
                    self.add_button(f'{self.playlist.conf["brand"]["title"]} ({self.playlist.conf["brand"]["id"]})' + ('\U00002757' if not self.playlist.conf["subbrands"] else '\U00002714'),
                                    SubBrandSelectTMessage(self.navigation, playlist=self.playlist))
                    if self.playlist.conf["subbrands"]:
                        self.add_button(u'\U0001F501', RefreshNewPlaylistTMessage(
                                        self.navigation,
                                        user=self.proc.user,
                                        params=self.proc.params,
                                        playlist=self.playlist
                                        ), new_row=True)
                        new_row = False
            self.add_button(':cross_mark: Abort', self.navigation.goto_back, new_row=new_row)
            if self.listings_changed:
                upd = self.get_listings_text()
                self.listings_changed = False
        elif self.status == NameDurationStatus.LISTING:
            self.input_field = u'\U0001F570'
            return f'Downloading listings {"." * (self.sub_status & 0xFF)}'
        elif self.status == NameDurationStatus.DOWNLOADING:
            self.input_field = u'\U0001F570'
            return f'Downloading brand content for {self.playlist.conf["brand"]["title"]} {"." * (self.sub_status & 0xFF)}'
        if self.return_msg:
            upd = f'\n<b>{self.return_msg}</b>'
        return upd if upd else self.input_field


class MediasetPlaylistTMessage(MedRaiPlaylistTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        super().__init__(navigation, user, params, playlist, playlist_type='mediaset')

    def get_listings_command(self):
        if self.playlist.conf['listings_command']:
            return PlaylistMessage(CMD_MEDIASET_LISTINGS, **self.playlist.conf['listings_command'])
        else:
            return None

    async def get_listings_command_params(self):
        await self.navigation.goto_menu(SelectDayTMessage(self.navigation, playlist=self.playlist))

    def get_subbrand_command(self):
        return PlaylistMessage(CMD_MEDIASET_BRANDS, brand=int(self.playlist.conf['brand']['id']))


class RaiPlaylistTMessage(MedRaiPlaylistTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        super().__init__(navigation, user, params, playlist, playlist_type='rai')

    def get_listings_command(self):
        return PlaylistMessage(CMD_RAI_LISTINGS)

    def get_subbrand_command(self):
        return PlaylistMessage(CMD_RAI_CONTENTSET, brand=self.playlist.conf['brand']['id'])


class RefreshNewPlaylistTMessage(RefreshingTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field=f'Refresh {playlist.name}',
            user=user,
            params=params,
            playlist=playlist)
        self.status = NameDurationStatus.UPDATING_INIT

    async def on_refresh_finish(self, pl: PlaylistMessage):
        await self.switch_to_idle()
        if pl.rv == 0:
            await self.navigation.goto_home()
            await self.navigation._menu_queue[0].list_page_of_playlists(None)

    async def on_refresh_abort(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.navigation.goto_back()

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        upd = await super().update(context)
        self.input_field = f'Refresh {self.playlist.name}'
        if not upd:
            upd = ''
        if self.return_msg:
            upd += f'\n{self.return_msg}'
        return upd if upd else self.input_field


class PlaylistAddTMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None) -> None:
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field='Select Playlist Type',
            user=user,
            params=params)

    def update(self, _: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.add_button('\U0001F534 YoutubeDL', YoutubeDLPlaylistTMessage(self.navigation, user=self.proc.user, params=self.proc.params))
        self.add_button('\U0001F535 Rai', RaiPlaylistTMessage(self.navigation, user=self.proc.user, params=self.proc.params))
        self.add_button('\U00002B24 Mediaset', MediasetPlaylistTMessage(self.navigation, user=self.proc.user, params=self.proc.params))
        self.add_button('\U0001F4C2 Folder', LocalFolderPlaylistTMessage(self.navigation, user=self.proc.user, params=self.proc.params))
        self.add_button(':cross_mark: Abort', self.navigation.goto_back, new_row=True)
        self.input_field = 'Select Playlist Type'
        return self.input_field

# test 16 Nov 2014 humansafari e https://www.youtube.com/@HumanSafari/videos e https://www.youtube.com/@safariumano/videos


class SignUpTMessage(BaseMessage):
    """Single action message."""
    STATUS_IDLE = 0
    STATUS_REGISTER = 2

    def __init__(self, navigation: MyNavigationHandler, params=None) -> None:
        """Init SignUpTMessage class."""
        super().__init__(
            navigation,
            self.__class__.__name__,
            expiry_period=None,
            inlined=False,
            home_after=False,
            input_field='Sign Up procedure'
        )
        self.status = SignUpTMessage.STATUS_IDLE
        self.url = ''
        self.params = params
        self.user_data = None

    def update(self, context: Optional[CallbackContext] = None) -> str:
        """Update message content."""
        if self.status == SignUpTMessage.STATUS_IDLE:
            self.input_field = "Please insert auth link"
        else:
            self.input_field = 'Please insert the token code'
        if context:
            self.user_data = context.user_data.setdefault('user_data', dict())
        return self.input_field

    async def text_input(self, text: str, context: Optional[CallbackContext] = None) -> None:
        """Receive text from console. If used, this function must be instantiated in the child class."""
        if text:
            if self.status != SignUpTMessage.STATUS_REGISTER:
                self.url = text
                url = f'{text}?{urlencode(dict(act="start", username=self.navigation.user_name))}'
            else:
                url = f'{self.url}?{urlencode(dict(act="finish", token=text, username=self.navigation.user_name))}'

            async with ClientSession() as session:
                async with session.get(url) as resp:
                    keyboard = self.gen_keyboard_content()
                    finished = False
                    if resp.status >= 200 and resp.status < 300:
                        if self.status == SignUpTMessage.STATUS_IDLE:
                            content = ':thumbs_up: Please insert the token code'
                            self.status = SignUpTMessage.STATUS_REGISTER
                        else:
                            content = ':thumbs_up: Restart the bot with /start command'
                            self.status = SignUpTMessage.STATUS_IDLE
                            finished = True
                            ps = urlparse(self.url)
                            self.user_data['link'] = f'{ps.scheme}://{ps.netloc}'
                    else:
                        content = f':thumbs_down: Error is <b>{str(await resp.read())} ({resp.status})</b>. <i>Please try again inserting link.</i>'
                        self.status = SignUpTMessage.STATUS_IDLE

                    await self.navigation.send_message(emoji_replace(content), keyboard)
                    if finished:
                        idmsg = await self.navigation.goto_home()
                        await self.navigation.delete_message(self.message_id)
                        await self.navigation.delete_message(idmsg)
            _LOGGER.info(f"Handle for {text}")


class TokenMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, **argw) -> None:
        super().__init__(navigation, label=f'{self.__class__.__name__}{id(self)}', inlined=True, expiry_period=timedelta(minutes=1), user=user, params=params, **argw)

    async def token_refresh(self, context: Optional[CallbackContext] = None):
        self.status = NameDurationStatus.UPDATING_RUNNING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id=f"long_operation_do{self.label}",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = PlaylistMessage(CMD_TOKEN, refresh=1)
        opt = time()
        pl = await self.proc.process(pl)
        df = time() - opt
        if df < 1.5:
            await asyncio.sleep(1.5 - df)
        if pl.rv == 0:
            self.proc.user.token = pl.token
            self.return_msg = ':thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} refreshing token :thumbs_down:'
        await self.switch_to_idle()

    async def update(self, context: CallbackContext | None = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        msg = self.proc.user.token
        if self.status == NameDurationStatus.IDLE:
            self.add_button(u'\U0001F503', self.token_refresh)
            # self.add_button(label=u"\U0001F519", callback=self.navigation.goto_back)
        elif self.status == NameDurationStatus.UPDATING_RUNNING:
            msg = f'Token updating {"." * (self.sub_status & 0xFF)}'
        return msg if not self.return_msg else f'{msg}\n<b>{self.return_msg}</b>'


class StartTMessage(BaseMessage):
    """Start menu, create all app sub-menus."""

    @staticmethod
    async def check_if_username_registred(db, tg) -> User:
        users: list[User] = await User.loadbyid(db, tg=tg)
        if users:
            return users[0]
        else:
            return None

    async def sign_out(self, context):
        if self.user:
            self.user.tg = None
            await self.user.toDB(self.params.db2)
        self.user = self.link = None
        await self.navigation.goto_home(context)

    async def list_page_of_playlists(self, page, context: Optional[CallbackContext] = None):
        if self.playlists_lister:
            await self.playlists_lister.goto_page((page, ), context)

    def cache_clear(self, context: Optional[CallbackContext] = None):
        cache_del_user(self.user.rowid, [])

    async def async_init(self, context: Optional[CallbackContext] = None):
        res = await self.check_if_username_registred(self.params.db2, self.navigation.user_name)
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        if context:
            self.user_data = context.user_data.setdefault('user_data', dict(link=''))
            if 'link' in self.user_data:
                self.link = self.user_data['link']
        if res and self.link:
            if self.user:
                self.user.cp(**res.toJSON())
            else:
                self.user = res
            self.params.link = self.link
            # second_menu = SecondMenuMessage(navigation, update_callback=message_args)
            self.proc = ProcessorMessage(res, self.params)
            if not res.token:
                pl = PlaylistMessage(CMD_TOKEN, refresh=1)
                pl = await self.proc.process(pl)
                res.token = pl.token
            self.playlists_lister = PlaylistsPagesTMessage(
                self.navigation,
                max_group_per_page=6,
                max_items_per_group=1,
                params=self.params,
                user=self.user)
            listall = PlaylistsPagesTMessage(
                self.navigation,
                max_group_per_page=6,
                max_items_per_group=1,
                params=self.params,
                deleted=True,
                user=self.user)
            self.add_button(label=":memo: List", callback=self.playlists_lister)
            self.add_button(label=":eye: All", callback=listall)
            self.add_button(label="\U00002B55 Message Cache Clear", callback=self.cache_clear)
            self.add_button(label="\U0001F3A7 Player", callback=PlayerListMessage(self.navigation, user=self.user, params=self.params))
            self.add_button(label="\U00002795 Add", callback=PlaylistAddTMessage(self.navigation, user=self.user, params=self.params))
            self.add_button(label="\U000026D7 Token", callback=TokenMessage(self.navigation, user=self.user, params=self.params))
            self.add_button(label="\U0001F6AA Sign Out", callback=SignOutTMessage(self.navigation))
        else:
            self.user = None
            self.proc = None
            action_message = SignUpTMessage(self.navigation, params=self.params)
            # second_menu = SecondMenuMessage(navigation, update_callback=message_args)
            self.add_button(label=":writing_hand: Sign Up", callback=action_message)
            # self.add_button(label="Second menu", callback=second_menu)

    def __init__(self, navigation: MyNavigationHandler, message_args) -> None:
        """Init StartTMessage class."""
        super().__init__(navigation, self.__class__.__name__)
        self.params = message_args[0]
        _LOGGER.debug(f'Start Message {message_args[0].args}')
        self.user: User = None
        self.link = None
        self.playlists_lister = None
        self.proc: ProcessorMessage = None

        # define menu buttons

    async def update(self, context: Optional[CallbackContext] = None):
        await self.async_init(context)
        if self.user:
            content = f'Hello <b>{self.user.username}</b> :musical_note:'
            self.input_field = emoji_replace(f'Hello {self.user.username} :musical_note:')
        else:
            content = self.input_field = emoji_replace('Hello: please click :writing_hand: Sign Up')
        return content

    @staticmethod
    def run_and_notify() -> str:
        """Update message content."""
        return "This is a notification"

    async def text_input(self, text: str, context: Optional[CallbackContext] = None) -> None:
        """Receive text from console. If used, this function must be instantiated in the child class."""
        _LOGGER.info(f"Handle for {text}")


async def stop_telegram_bot():
    raise SystemExit


def start_telegram_bot(params, loop):
    logging.getLogger('hpack.hpack').setLevel(logging.INFO)
    loop = asyncio.set_event_loop(loop)
    api_key = params.args['telegram']
    _LOGGER.info(f'Starting bot with {params} in loop {id(loop)}')
    TelegramMenuSession(api_key, persistence_path=params.args['pickle']).start(start_message_class=StartTMessage, start_message_args=[params], navigation_handler_class=MyNavigationHandler, stop_signals=())
