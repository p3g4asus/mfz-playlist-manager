from abc import abstractmethod
from asyncio import Task, create_task, sleep
from datetime import timedelta
import json
import logging
import re
import traceback
from typing import Any, Coroutine, Dict, List, Optional, Tuple, Union
from urllib.parse import ParseResult, parse_qs, urlencode, urlparse, urlunparse

from aiohttp import ClientSession, WSMsgType
from telegram_menu import MenuButton, NavigationHandler
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD

from common.const import CMD_REMOTEPLAY, CMD_REMOTEPLAY_PUSH, CMD_REMOTEPLAY_PUSH_NOTIFY
from common.playlist import PlaylistMessage
from common.user import User
from common.utils import MyEncoder
from server.telegram.message import MyNavigationHandler, NameDurationStatus, ProcessorMessage, StatusTMessage

_LOGGER = logging.getLogger(__name__)


class RemoteInfoMessage(StatusTMessage):
    END_URL_PATH: str = '-s/play/player_remote_commands.htm'

    @staticmethod
    @abstractmethod
    def get_my_hex_prefix() -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_dest_hex_prefix() -> str:
        pass

    @staticmethod
    def is_url_ok(url) -> Tuple[ParseResult, Dict[str, List[str]]]:
        parsed_url = urlparse(url)
        dictspar = parse_qs(parsed_url.query)
        return (parsed_url, dictspar) if parsed_url.scheme and 'name' in dictspar and 'hex' in dictspar and parsed_url.path.endswith(RemoteInfoMessage.END_URL_PATH) else None

    @staticmethod
    def get_string_id_from_class(cls: type[object]):
        if mo := re.search(r'^(.+)(List|Info)Message$', strid := cls.__name__):
            strid = mo.group(1)
        return strid.lower()

    def __init__(self, name: str, url: str, sel: bool, navigation: Optional[NavigationHandler] = None, **argw) -> None:
        super().__init__(
            navigation,
            label=self.__class__.__name__ + name,
            expiry_period=timedelta(hours=3),
            input_field='Timestamp',
            inlined=True,
            **argw)
        if not (pr := self.is_url_ok(url)):
            raise Exception(f'Invalid remote url {url}')
        self.name: str = name
        self.navigation: MyNavigationHandler
        self.task: Optional[Task] = None
        self.paused: bool = False
        self.S = RemoteInfoMessage.get_string_id_from_class(self.__class__).capitalize()
        self.sentinel: Optional[Task] = None
        self.url: str = url
        self.navigation: Optional[NavigationHandler] = navigation
        self.stopped: bool = False
        self.old_picture = None
        self.killed: bool = False
        self.sel = sel
        self.last_send = None
        self.parsed_url: Tuple[ParseResult, Dict[str, List[str]]] = pr
        base_hex = pr[1]['hex'][0]
        self.dest_hex = self.get_dest_hex_prefix() + base_hex
        self.my_hex = self.get_my_hex_prefix() + base_hex
        self.base_cmd: ParseResult = pr[0]._replace(path=pr[0].path[1:-len(RemoteInfoMessage.END_URL_PATH)] + f'/rcmd/{self.dest_hex}')

    @abstractmethod
    def process_incoming_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def notification_has_to_be_sent(self, arg: Dict[str, Any]) -> bool:
        pass

    def stop_sentinel(self):
        if self.sentinel:
            _LOGGER.debug(f'{self.label} Sentinel Stopped {self.my_hex}')
            self.sentinel.cancel()
            self.sentinel = None

    def stop(self):
        self.stopped = True
        self.stop_sentinel()
        if self.task:
            self.task.cancel()
            self.task = None

    def start(self):
        self.stopped = False
        if not self.task:
            self.task = create_task(self.ws_connect())

    def kill_message(self):
        self.killed = self.has_expired()

    def picture_changed(self):
        if not self.old_picture and not self.picture:
            return False
        elif self.old_picture != self.picture:
            self.old_picture = self.picture
            return True
        else:
            return False

    async def remote_send(self):
        if not self.killed and self.navigation._message_queue and self.navigation._message_queue[-1] is self and not self.picture_changed() and (await self.navigation.navigation_schedule_wrapper(self.edit_message(), True)):
            _LOGGER.debug(f'{self.label} remote_send edit_or_select')
        else:
            _LOGGER.debug(f'{self.label} remote_send send')
            if self.killed:
                self.killed = False
                self.time_alive = None
            mid = None
            if self in self.navigation._message_queue:
                mid = self.message_id
                self.navigation._message_queue.remove(self)
            if (mo := re.search(r'(\d+)$', self.label)):
                nn = int(mo.group(1))
                ss = self.label[0:mo.start(1)]
            else:
                nn = 0
                ss = self.label
            nn += 1
            self.label = f'{ss}{nn}'
            await self.send(sync=True)
            if mid is not None:
                self.navigation: MyNavigationHandler
                self.navigation.send_operation_wrapper(self.navigation.delete_message(mid))

    async def noify(self, arg: Dict[str, Any]):
        _LOGGER.debug(f'{self.label} cheking notication for {arg.keys()}')
        if not self.paused and self.notification_has_to_be_sent(arg):
            _LOGGER.debug(f'{self.label} notifying for {arg.keys()}')
            await self.remote_send()

    async def ws_send(self, ws, cmd):
        _LOGGER.debug(f'{self.label} Sending to {self.my_hex} -> {cmd}')
        await ws.send_str(cmd)

    async def ws_sentinel(self, ws, timeout):
        await sleep(timeout)
        if self.task and self.sentinel:
            _LOGGER.debug(f'{self.label} Sentinel Stopping connection {self.my_hex}')
            try:
                await ws.close()
            except Exception:
                pass
            self.sentinel = None

    async def update(self, context: CallbackContext | None = None) -> str:
        self.keyboard: List[List["MenuButton"]] = [[]]
        return f'<b>{self.S} {self.name}{" (paused)" if self.paused else ""}</b> /' + ('restart' if self.paused else 'pause') + '\n'

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if text == '/pause' or text == '/restart':
            if text == '/restart':
                self.paused = False
            elif text == '/pause':
                self.paused = True
            await self.remote_send()

    async def ws_connect(self):
        pr = self.parsed_url
        urlp = pr[0]._replace(path=pr[0].path[1:-len(RemoteInfoMessage.END_URL_PATH)] + f'-ws/{self.my_hex}')._replace(query='')._replace(scheme='wss' if pr[0].scheme.endswith('s') else 'ws')
        urls = urlunparse(urlp)
        session = ClientSession()
        while not self.stopped:
            try:
                _LOGGER.debug(f'{self.label} Connecting to {urls} for {self.my_hex}')
                async with session.ws_connect(urls, heartbeat=5) as ws:
                    _LOGGER.debug(f'{self.label} Opened connection for {self.my_hex}')
                    remplay = json.dumps(PlaylistMessage(CMD_REMOTEPLAY), cls=MyEncoder)
                    rempush = json.dumps(PlaylistMessage(CMD_REMOTEPLAY_PUSH_NOTIFY, fr=self.dest_hex), cls=MyEncoder)
                    self.sentinel = create_task(self.ws_sentinel(ws, 7))
                    await self.ws_send(ws, remplay)
                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            pl = PlaylistMessage(None, cmd := msg.json())
                            _LOGGER.debug(f'{self.label} Receiving in {self.my_hex} -> {cmd}')
                            if pl.c(CMD_REMOTEPLAY):
                                if not pl.rv:
                                    await self.ws_send(ws, rempush)
                                else:
                                    await self.ws_send(ws, remplay)
                            elif pl.c(CMD_REMOTEPLAY_PUSH_NOTIFY):
                                if pl.rv:
                                    await self.ws_send(ws, remplay)
                                else:
                                    self.stop_sentinel()
                            elif pl.c(CMD_REMOTEPLAY_PUSH):
                                arg = None
                                if pl.f('exp'):
                                    self.process_incoming_data(arg := pl.f(pl.what))
                                else:
                                    self.process_incoming_data(arg := {pl.what: pl.f(pl.what)})
                                await self.noify(arg)
                        elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                            _LOGGER.debug(f'{self.label} Closing connection for {self.my_hex} -> msg')
                            break
            except Exception as exc:
                _LOGGER.debug(f'{self.label} Closing connection for {self.my_hex} -> {exc}')
                pass
            self.stop_sentinel()

    async def sendGenericCommand(self, **cmdo: dict) -> Dict[str, Any]:
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
                        rv = self.process_incoming_data(data)
                    except Exception:
                        _LOGGER.warning(traceback.format_exc())
                    return rv


class RemoteListMessage(StatusTMessage):

    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, strid: str = None, **argw) -> None:
        self.current_url = ''
        if not strid:
            strid = RemoteInfoMessage.get_string_id_from_class(self.__class__)
        self.s: str = strid.lower()
        self.S: str = strid.capitalize()
        super().__init__(navigation, label=self.__class__.__name__, input_field=f'{self.S} Url', user=user, params=params, **argw)

    @staticmethod
    @abstractmethod
    def build_remote_info_message(name: str, url: str, sel: bool, navigation: NavigationHandler, user: User) -> RemoteInfoMessage:
        pass

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.IDLE:
            text = text.strip()
            if not self.current_url:
                if RemoteInfoMessage.is_url_ok(text):
                    self.current_url = text
                    await self.edit_or_select()
            elif RemoteInfoMessage.is_url_ok(text):
                self.current_url = text
            else:
                await self.add_remote(self.build_remote_info_message(text, self.current_url, False, self.navigation, self.proc.user))
                self.current_url = ''
                await self.edit_or_select()

    @classmethod
    async def set_user_conf_field(cls, remotes_cache: Dict[str, RemoteInfoMessage], proc: ProcessorMessage, field_id: str = None):
        res = proc.user.conf
        plrs = dict()
        if not field_id:
            field_id = RemoteInfoMessage.get_string_id_from_class(cls)
        for pin, pi in remotes_cache.items():
            plrs[pin] = dict(url=pi.url, sel=pi.sel)
        res[field_id + 's'] = plrs
        await proc.user.toDB(proc.params.db2)

    @classmethod
    def user_conf_field_to_remotes_dict(cls, navigation: NavigationHandler, proc: ProcessorMessage, sel_only: bool = False, field_id: str = None) -> Dict[str, RemoteInfoMessage]:
        rid = proc.user.rowid
        if not hasattr(cls, 'remotes_cache_u'):
            cls.remotes_cache_u: Dict[int, Dict[str, RemoteInfoMessage]] = dict()
        if rid not in cls.remotes_cache_u:
            remotes_cache = cls.remotes_cache_u[rid] = dict()
            if not field_id:
                field_id = RemoteInfoMessage.get_string_id_from_class(cls)
            usrconf = proc.user.conf
            for pin, pid in usrconf.get(field_id + 's', dict()).items():
                if isinstance(pid, str):
                    piu = pid
                    sel = False
                elif isinstance(pid, dict):
                    piu = pid['url']
                    sel = pid['sel']
                else:
                    piu = None
                if piu:
                    remotes_cache[pin] = pi = cls.build_remote_info_message(pin, piu, sel, navigation, proc.user)
                    if sel:
                        pi.start()
        else:
            remotes_cache = cls.remotes_cache_u[rid]
        if sel_only:
            remotes_cache = {pin: pi for pin, pi in remotes_cache.items() if pi.sel}
        return remotes_cache

    async def add_remote(self, pi: RemoteInfoMessage):
        rid = self.proc.user.rowid
        remotes_cache = self.remotes_cache_u[rid]
        remotes_cache[pi.name] = pi
        if pi.sel:
            pi.start()
        await self.set_user_conf_field(remotes_cache, self.proc)
        await self.edit_or_select()

    async def remote_clicked(self, args: tuple):
        self.current_url = ''
        idx = args[0]
        rid = self.proc.user.rowid
        remotes_cache: Dict[str, RemoteInfoMessage] = self.remotes_cache_u[rid]
        pi = remotes_cache[idx]
        if self.status == NameDurationStatus.DELETING:
            pi.stop()
            await pi.navigation._delete_queued_message(pi)
            del remotes_cache[idx]
            await self.set_user_conf_field(remotes_cache, self.proc)
            await self.switch_to_idle()
        elif self.status == NameDurationStatus.SORTING:
            pi.sel = not pi.sel
            if pi.sel:
                pi.start()
            else:
                pi.stop()
            await self.set_user_conf_field(remotes_cache, self.proc)
            await self.switch_to_idle()
        else:
            await remotes_cache[idx].remote_send()

    async def prepare_for_mod(self, args: tuple, context: Union[CallbackContext, None] = None):
        self.current_url = ''
        await self.switch_to_status(args, context)

    async def update(self, _: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        self.input_field = (f'{self.S} Url' if not self.current_url else f'{self.S} alias') + u' or \U0001F559'
        rid = self.proc.user.rowid
        if not hasattr(self, 'remotes_cache_u') or rid not in self.remotes_cache_u:
            remotes_cache = self.user_conf_field_to_remotes_dict(self.navigation, self.proc)
        else:
            remotes_cache = self.remotes_cache_u[rid]
        self.keyboard: List[List["MenuButton"]] = [[]]
        for pin in sorted(remotes_cache.keys(), key=str.casefold):
            self.add_button(pin + (u' \U0001F4CD' if remotes_cache[pin].sel else ''), self.remote_clicked, args=(pin,), new_row=True)
        if self.status == NameDurationStatus.IDLE:
            if remotes_cache:
                self.add_button(u'\U0001F5D1', self.prepare_for_mod, args=(NameDurationStatus.DELETING, ), new_row=True)
                self.add_button(u'\U0001F4CC', self.prepare_for_mod, args=(NameDurationStatus.SORTING, ))
            self.add_button(label=u"\U0001F3E0 Home", callback=self.navigation.goto_back, new_row=True)
            return f'Click {self.s} to open or add new {self.s}'
        else:
            self.add_button(':cross_mark: Abort', self.switch_to_idle, new_row=True)
            return f'Click {self.s} to delete'
