import asyncio
import imghdr
from time import time
import logging
import re
from typing import Any, Coroutine, Dict, List, Optional, Tuple
from urllib.parse import ParseResult

from redis.asyncio.client import Redis
from telegram_menu import MenuButton, NavigationHandler
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD

from common.const import CMD_REMOTEBROWSER_JS, CMD_REMOTEBROWSER_JS_ACTIVATE, CMD_REMOTEBROWSER_JS_CLOSE, CMD_REMOTEBROWSER_JS_GOTO, CMD_REMOTEBROWSER_JS_RELOAD
from common.user import User
from common.utils import Fieldable
from server.telegram.message import NameDurationStatus, ProcessorMessage

from redis import asyncio as aioredis

from server.telegram.remote import RemoteInfo, RemoteInfoMessage, RemoteListMessage

_LOGGER = logging.getLogger(__name__)


class BrowserTab(Fieldable):
    def __init__(self, id: int = None, title: str = None, url: str = None, active: bool = False, ico: str = None, **kwargs):
        self.id = id
        self.title = title
        self.url = url
        self.active = active
        self.ico = ico
        for key, val in kwargs.items():
            setattr(self, key, val)


class BrowserInfo(RemoteInfo):

    def __init__(self, name: str, url: str, sel: bool) -> None:
        super().__init__(name, url, sel)
        pr = self.parsed_url
        self.tabs: Dict[int, BrowserTab] = dict()
        self.tab: BrowserTab = None
        self.base_cmd: ParseResult = pr[0]._replace(path=pr[0].path[1:-len(BrowserInfo.END_URL_PATH)] + f'/rcmd/g{pr[1]["hex"][0]}')

    def process_incoming_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rv = None
        if 'tabs' in data:
            self.tabs.clear()
            self.tab = None
            for t in data['tabs']:
                self.tabs[t['id']] = ct = BrowserTab(**t)
                if ct.active:
                    self.tab = ct

        else:
            for k, v in data.items():
                if (mo := re.search('ic([0-9]+)', k)):
                    tbi = int(mo.group(1))
                    if tbi in self.tabs:
                        self.tabs[tbi].ico = v
        return rv


class BrowserInfoMessage(RemoteInfoMessage):
    def __init__(self, navigation: NavigationHandler, remote_info: BrowserInfo, redis: Redis = None, user: User = None, params: object = None, **argw) -> None:
        super().__init__(navigation, remote_info, user, params, **argw)
        self.time_status: int = 0
        self.info_changed: bool = False
        self.redis = redis
        self.lst_sel: List[str] = []
        self.activate_tab: bool = True
        self.current_tab: BrowserTab = None

    async def close(self, args: tuple):
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_CLOSE, id=self.current_tab.id if self.current_tab else self.pi.tab.id)
        await asyncio.sleep(2.5)
        await self.info()

    async def reload(self, args: tuple):
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_RELOAD, id=self.current_tab.id if self.current_tab else self.pi.tab.id)

    async def activate(self, args: tuple):
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_ACTIVATE, id=self.current_tab.id if self.current_tab else self.pi.tab.id)
        await asyncio.sleep(2.5)
        await self.info()

    async def goto(self, url: str):
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_GOTO, id=self.current_tab.id if self.current_tab else 'New', url=url, act=self.activate_tab)
        await asyncio.sleep(2.5)
        await self.info()

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.DOWNLOADING_WAITING:
            text = text.strip()
            try:
                if (mo := re.search('/ur([0-9]+)', text)):
                    g = int(mo.group(1))
                    url = self.lst_sel[g] if g < len(self.lst_sel) else ''
                else:
                    url = text
                if url:
                    await self.redis.zadd(f'urls_{self.proc.user.rowid}', {url: int(time())})
                    await self.goto(url)
                    await self.switch_to_idle()
            except Exception:
                pass
        elif self.status == NameDurationStatus.IDLE:
            text = text.strip()
            try:
                if (mo := re.search('/ST([0-9]+)', text)):
                    g = int(mo.group(1))
                    self.current_tab = self.pi.tabs[g] if g in self.pi.tabs else None
                    if self.current_tab:
                        await self.info((f'ic{g}',))
            except Exception:
                pass

    async def info(self, args: tuple = None, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        k = 'tabs' if not args or not args[0] else args[0]
        await self.pi.sendGenericCommand(get=[k])
        if k == 'tabs':
            self.current_tab = None
            if self.pi.tab:
                await self.info((f'ic{self.pi.tab.id}',))
                return
        self.info_changed = True
        await self.edit_or_select()

    async def prepare_for_new_tab(self, args: tuple):
        self.activate_tab = True
        self.current_tab = None
        await self.switch_to_status((NameDurationStatus.DOWNLOADING_WAITING, ))

    async def prepare_for_overwrite_tab(self, args: tuple):
        self.activate_tab = True
        if not self.current_tab:
            self.current_tab = self.pi.tab
        await self.switch_to_status((NameDurationStatus.DOWNLOADING_WAITING, ))

    async def toggle_activate(self, args: tuple):
        self.activate_tab = not self.activate_tab
        await self.edit_or_select()

    async def update(self, context: CallbackContext | None = None) -> str:
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = u'Select button'
        if self.status == NameDurationStatus.IDLE:
            self.add_button(u'\U00002139', self.info, args=tuple())
            if self.current_tab or self.pi.tab:
                self.add_button(u'\U0001F501', self.reload)
                self.add_button(u'\U0000274C', self.close)
                if self.current_tab:
                    self.add_button(u'\U0001F7E9', self.activate)
                self.add_button(u'\U0001F310', self.prepare_for_overwrite_tab)
            self.add_button(u'\U0001F310\U00002795', self.prepare_for_new_tab)
            self.add_button(label=u"\U0001F519", callback=self.navigation.goto_back, new_row=True)
            self.picture = None
            if self.current_tab:
                self.picture = self.current_tab.ico if self.current_tab.ico else ''
                if self.picture:
                    if self.picture.startswith('data:') or self.picture.endswith('.svg') or self.picture.endswith('.ico'):
                        try:
                            import urllib
                            from PIL import Image
                            from io import BytesIO
                            response = urllib.request.urlopen(self.picture)
                            try:
                                self.picture = BytesIO(response.file.read())
                            except Exception:
                                self.picture = BytesIO(response.read())
                            if not imghdr.what(self.picture):
                                img = Image.open(self.picture)
                                membuf = BytesIO()
                                img.save(membuf, format="png")
                                membuf.seek(0)
                                self.picture = membuf
                        except Exception:
                            self.picture = ''
                return self.current_tab.title if self.current_tab.title else f'ID = {self.current_tab.id}'
            elif not self.info_changed:
                idx = self.time_status
                self.time_status += 1
                if self.time_status >= len(self.TIMES):
                    self.time_status = 0
                return self.TIMES[idx]
            else:
                self.info_changed = False
                out = ''
                if self.pi.tabs:
                    for i, t in self.pi.tabs.items():
                        if t.active:
                            out += '<b><u>'
                        out += f'/ST{i:07} ' + ('\U0001F6A6' if t.active else '') + f'{t.title[0:200]}{"</u></b>" if t.active else ""}\n'
                        if len(out) > 3900:
                            break
                else:
                    out = 'No Open Tab'
                return out
        elif self.status == NameDurationStatus.DOWNLOADING_WAITING:
            self.input_field = 'url'
            self.picture = None
            try:
                urls = f'urls_{self.proc.user.rowid}'
                await self.redis.zremrangebyscore(urls, '-inf', int(time() - 864000))
                self.lst_sel = await self.redis.zrange(urls, 0, -1, desc=True)
                out = ''
                for i, url in enumerate(self.lst_sel):
                    if not i:
                        out = 'Enter or select url:\n'
                    out += f'/ur{i:07} {url[0:150].decode("utf-8")}\n'
                    if len(out) > 3900:
                        break
                if not out:
                    out = 'Enter url:'
            except Exception:
                out = 'Enter url:'
            self.add_button(u'\U0001F7E9' if self.activate_tab else u'\U00002B1B', self.toggle_activate)
            self.add_button(u'\U00002934', self.switch_to_idle)
            return out


class BrowserListMessage(RemoteListMessage):
    redis: Redis = None

    @staticmethod
    def build_remote_info(name: str, url: str, sel: bool) -> RemoteInfo:
        return BrowserInfo(name, url, sel)

    @staticmethod
    def build_remote_info_message(navigation: NavigationHandler, remote_info: RemoteInfo, user: User = None, params: object = None, **argw) -> RemoteInfoMessage:
        return BrowserInfoMessage(navigation, remote_info, redis=BrowserListMessage.redis, user=user, params=params, **argw)

    @classmethod
    def user_conf_field_to_remotes_dict(cls, navigation: NavigationHandler, proc: ProcessorMessage, sel_only: bool = False, field_id: str = None) -> Tuple[Dict[str, RemoteInfo], Dict[str, RemoteInfoMessage]]:
        if not BrowserListMessage.redis:
            BrowserListMessage.redis = aioredis.from_url(proc.params.args["redis"], encoding="utf-8", decode_responses=False)
        return super(BrowserListMessage, cls).user_conf_field_to_remotes_dict(navigation, proc, sel_only, field_id)
