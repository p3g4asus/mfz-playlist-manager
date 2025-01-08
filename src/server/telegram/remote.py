from abc import abstractmethod
from datetime import timedelta
import logging
import re
import traceback
from typing import Any, Coroutine, Dict, List, Optional, Tuple, Union
from urllib.parse import ParseResult, parse_qs, urlencode, urlparse, urlunparse

from aiohttp import ClientSession
from telegram_menu import MenuButton, NavigationHandler
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD

from common.user import User
from server.telegram.message import NameDurationStatus, ProcessorMessage, StatusTMessage

_LOGGER = logging.getLogger(__name__)


class RemoteInfo(object):
    END_URL_PATH: str = '-s/play/player_remote_commands.htm'

    @staticmethod
    def is_url_ok(url) -> Tuple[ParseResult, Dict[str, List[str]]]:
        parsed_url = urlparse(url)
        dictspar = parse_qs(parsed_url.query)
        return (parsed_url, dictspar) if parsed_url.scheme and 'name' in dictspar and 'hex' in dictspar and parsed_url.path.endswith(RemoteInfo.END_URL_PATH) else None

    def __init__(self, name: str, url: str, sel: bool) -> None:
        if not (pr := self.is_url_ok(url)):
            raise Exception(f'Invalid remote url {url}')
        self.name: str = name
        self.url: str = url
        self.sel = sel
        self.parsed_url: Tuple[ParseResult, Dict[str, List[str]]] = pr

    @abstractmethod
    def process_incoming_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

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


class RemoteInfoMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, remote_info: RemoteInfo, user: User = None, params: object = None, **argw) -> None:
        self.pi = remote_info
        super().__init__(
            navigation,
            label=self.__class__.__name__ + remote_info.name,
            expiry_period=timedelta(hours=3),
            input_field='Timestamp',
            user=user,
            params=params,
            **argw)

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


class RemoteListMessage(StatusTMessage):
    @classmethod
    def get_string_id_from_class(cls: type[object]):
        if mo := re.search(r'^(.+)ListMessage$', strid := cls.__name__):
            strid = mo.group(1)
        return strid.lower()

    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, strid: str = None, **argw) -> None:
        self.remotes: Dict[str, RemoteInfo] = None
        self.remotes_cache: Dict[str, RemoteInfoMessage] = dict()
        self.current_url = ''
        if not strid:
            strid = self.get_string_id_from_class()
        self.s: str = strid.lower()
        self.S: str = strid.capitalize()
        super().__init__(navigation, label=self.__class__.__name__, input_field=f'{self.S} Url', user=user, params=params, **argw)

    @staticmethod
    @abstractmethod
    def build_remote_info(name: str, url: str, sel: bool) -> RemoteInfo:
        pass

    @staticmethod
    @abstractmethod
    def build_remote_info_message(navigation: NavigationHandler, remote_info: RemoteInfo, user: User = None, params: object = None, **argw) -> RemoteInfoMessage:
        pass

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.IDLE:
            text = text.strip()
            if not self.current_url:
                if RemoteInfo.is_url_ok(text):
                    self.current_url = text
                    await self.edit_or_select()
            elif RemoteInfo.is_url_ok(text):
                self.current_url = text
            else:
                await self.add_remote(self.build_remote_info(text, self.current_url, False))
                self.current_url = ''
                await self.edit_or_select()

    @classmethod
    async def set_user_conf_field(cls, remotes: Dict[str, RemoteInfo], proc: ProcessorMessage, field_id: str = None):
        res = proc.user.conf
        plrs = dict()
        if not field_id:
            field_id = cls.get_string_id_from_class()
        for pin, pi in remotes.items():
            plrs[pin] = dict(url=pi.url, sel=pi.sel)
        res[field_id + 's'] = plrs
        await proc.user.toDB(proc.params.db2)

    @classmethod
    def user_conf_field_to_remotes_dict(cls, navigation: NavigationHandler, proc: ProcessorMessage, sel_only: bool = False, field_id: str = None) -> Tuple[Dict[str, RemoteInfo], Dict[str, RemoteInfoMessage]]:
        remotes = dict()
        remotes_cache = dict()
        if not field_id:
            field_id = cls.get_string_id_from_class()
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
            if piu and (sel or not sel_only):
                remotes[pin] = pi = cls.build_remote_info(pin, piu, sel)
                if navigation and proc:
                    remotes_cache[pin] = cls.build_remote_info_message(navigation, pi, user=proc.user, params=proc.params)
        return (remotes, remotes_cache)

    async def add_remote(self, pi: RemoteInfo):
        self.remotes[pi.name] = pi
        self.remotes_cache[pi.name] = self.build_remote_info_message(self.navigation, pi, user=self.proc.user, params=self.proc.params)
        await self.set_user_conf_field(self.remotes, self.proc)
        await self.edit_or_select()

    async def remote_clicked(self, args: tuple):
        self.current_url = ''
        if self.status == NameDurationStatus.DELETING:
            del self.remotes[args[0]]
            del self.remotes_cache[args[0]]
            await self.set_user_conf_field(self.remotes, self.proc)
            await self.switch_to_idle()
        elif self.status == NameDurationStatus.SORTING:
            self.remotes[args[0]].sel = not self.remotes[args[0]].sel
            await self.set_user_conf_field(self.remotes, self.proc)
            await self.switch_to_idle()
        else:
            await self.remotes_cache[args[0]].edit_or_select()

    async def prepare_for_mod(self, args: tuple, context: Union[CallbackContext, None] = None):
        self.current_url = ''
        await self.switch_to_status(args, context)

    async def update(self, _: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        self.input_field = (f'{self.S} Url' if not self.current_url else f'{self.S} alias') + u' or \U0001F559'
        if self.remotes is None:
            self.remotes, self.remotes_cache = self.user_conf_field_to_remotes_dict(self.navigation, self.proc)
        self.keyboard: List[List["MenuButton"]] = [[]]
        for pin in sorted(self.remotes.keys(), key=str.casefold):
            self.add_button(pin + (u' \U0001F4CD' if self.remotes[pin].sel else ''), self.remote_clicked, args=(pin,), new_row=True)
        if self.status == NameDurationStatus.IDLE:
            if self.remotes:
                self.add_button(u'\U0001F5D1', self.prepare_for_mod, args=(NameDurationStatus.DELETING, ), new_row=True)
                self.add_button(u'\U0001F4CC', self.prepare_for_mod, args=(NameDurationStatus.SORTING, ))
            self.add_button(label=u"\U0001F3E0 Home", callback=self.navigation.goto_back, new_row=True)
            return f'Click {self.s} to open or add new {self.s}'
        else:
            self.add_button(':cross_mark: Abort', self.switch_to_idle, new_row=True)
            return f'Click {self.s} to delete'
