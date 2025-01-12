from copy import deepcopy
from html import escape
from urllib.error import HTTPError, URLError
import imghdr
import logging
import re
from time import time
from typing import Any, Coroutine, Dict, List, Optional, Tuple

from redis import asyncio as aioredis
from redis.asyncio.client import Redis
from telegram import LinkPreviewOptions
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD
from telegram_menu import MenuButton, NavigationHandler

from common.const import (CMD_REMOTEBROWSER_JS, CMD_REMOTEBROWSER_JS_ACTIVATE,
                          CMD_REMOTEBROWSER_JS_CLOSE,
                          CMD_REMOTEBROWSER_JS_GOTO, CMD_REMOTEBROWSER_JS_KEY,
                          CMD_REMOTEBROWSER_JS_MUTE,
                          CMD_REMOTEBROWSER_JS_RELOAD)
from common.user import User
from common.utils import Fieldable
from server.telegram.message import NameDurationStatus, ProcessorMessage
from server.telegram.remote import RemoteInfoMessage, RemoteListMessage

_LOGGER = logging.getLogger(__name__)


class BrowserTab(Fieldable):
    def __init__(self, id: int = None, title: str = None, url: str = None, active: bool = False, ico: str = None, muted: bool = False, **kwargs):
        self.id = id
        self.title = title
        self.url = url
        self.active = active
        self.ico = ico
        self.muted = muted
        for key, val in kwargs.items():
            setattr(self, key, val)

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, BrowserTab):
            return self.url == other.url and self.active == other.active and self.id == other.id and other.title == self.title and self.muted == other.muted and self.ico == other.ico
        return False


class BrowserInfoMessage(RemoteInfoMessage):

    def __init__(self, name: str, url: str, sel: bool, navigation: Optional[NavigationHandler], redis: Redis = None, user: User = None) -> None:
        super().__init__(name, url, sel, navigation, link_preview=LinkPreviewOptions(is_disabled=True))
        self.tabs: Dict[int, BrowserTab] = dict()
        self.tab: BrowserTab = None
        self.current_tab: BrowserTab = None
        self.time_status: int = 0
        self.redis = redis
        self.lst_sel: List[Tuple[str, float]] = []
        self.activate_tab: bool = True
        self.user: User = user
        self.modification_made: bool = False

    @staticmethod
    def get_my_hex_prefix() -> str:
        return 'i'

    @staticmethod
    def get_dest_hex_prefix():
        return 'g'

    def process_incoming_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rv = None
        self.modification_made = False
        oldtabs = None
        if 'tabs' in data:
            oldtabs = self.tabs.copy()
            self.tabs.clear()
            self.tab = None
            for t in data['tabs']:
                if (tbi := t['id']) in oldtabs:
                    oldico = oldtabs[tbi].ico
                else:
                    oldico = None
                    self.modification_made = True
                self.tabs[tbi] = ct = BrowserTab(**t)
                if not ct.ico and oldico:
                    ct.ico = oldico
                if ct.active:
                    self.tab = ct
        else:
            for k, v in data.items():
                if (mo := re.search('ic([0-9]+)', k)):
                    tbi = int(mo.group(1))
                    if tbi in self.tabs and (t := self.tabs[tbi]).ico != v:
                        t = deepcopy(t)
                        t.ico = v
                        self.tabs[tbi] = t
                        self.modification_made = True
        if not self.modification_made and oldtabs is not None:
            self.modification_made = oldtabs != self.tabs
        return rv

    PIN_TIME = 31536000 * 300

    async def close(self, args: tuple):
        t = self.current_tab
        self.current_tab = None
        self.picture = None
        await self.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_CLOSE, id=t.id if t else self.tab.id)

    async def reload(self, args: tuple):
        await self.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_RELOAD, id=self.current_tab.id if self.current_tab else self.tab.id)

    async def toggle_mute(self, args: tuple):
        await self.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_MUTE, id=self.current_tab.id if self.current_tab else self.tab.id, yes=1 if args[0] == u'\U0001F507' else 0)

    async def key(self, args: tuple):
        await self.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_KEY, comp=args[0], id=self.current_tab.id if self.current_tab else self.tab.id)

    async def activate(self, args: tuple):
        await self.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_ACTIVATE, id=self.current_tab.id if self.current_tab else self.tab.id)

    async def goto(self, url: str):
        await self.sendGenericCommand(cmd=CMD_REMOTEBROWSER_JS, sub=CMD_REMOTEBROWSER_JS_GOTO, id=self.current_tab.id if self.current_tab else 'New', url=url, act=self.activate_tab)

    def set_picture_for_current_tab(self):
        # self.picture = None
        # return
        self.picture = self.current_tab.ico if self.current_tab and self.current_tab.ico else ''
        if self.picture:
            if self.picture.startswith('data:') or self.picture.endswith('.svg') or self.picture.endswith('.ico'):
                try:
                    import urllib
                    from io import BytesIO

                    from PIL import Image
                    response = urllib.request.urlopen(self.picture, timeout=3)
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
                except (Exception, HTTPError, URLError):
                    self.picture = ''

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.lst_sel and (mo := re.search('/(u|p)p([0-9]+)', text)) and (g := int(mo.group(2))) < len(self.lst_sel):
            score = int(time() + (0 if mo.group(1) == 'u' else BrowserInfoMessage.PIN_TIME))
            await self.redis.zadd(f'urls_{self.user.rowid}', {self.lst_sel[g][0]: score})
            if self.status == NameDurationStatus.DOWNLOADING_WAITING:
                await self.remote_send()
        elif self.status == NameDurationStatus.DOWNLOADING_WAITING:
            text = text.strip()
            try:
                score = time()
                if (mo := re.search('/ur([0-9]+)', text)):
                    g = int(mo.group(1))
                    url = self.lst_sel[g][0] if g < len(self.lst_sel) else ''
                    if self.lst_sel[g][1] > score:
                        score += BrowserInfoMessage.PIN_TIME
                else:
                    url = text
                if url:
                    await self.redis.zadd(f'urls_{self.user.rowid}', {url: int(score)})
                    await self.goto(url)
                    await self.switch_to_idle()
            except Exception:
                pass
        elif self.status == NameDurationStatus.UPDATING_INIT:
            self.picture = None
            try:
                if (mo := re.search('/ST([0-9]+)', text)):
                    g = int(mo.group(1))
                    tab = self.tabs[g] if g in self.tabs else None
                    if tab:
                        self.current_tab = tab
                        self.set_picture_for_current_tab()
                        self.status = NameDurationStatus.IDLE
                        await self.remote_send()
            except Exception:
                pass
        elif self.status == NameDurationStatus.IDLE:
            text = text.strip()
            try:
                if (mo := re.search('^/k(.+)$', text)):
                    await self.key((mo.group(1), ))
            except Exception:
                pass

    def notification_has_to_be_sent(self, arg):
        if self.current_tab:
            if ('tabs' in arg or f'ic{self.current_tab.id}' in arg) and self.current_tab.id in self.tabs and (t := self.tabs[self.current_tab.id]) != self.current_tab:
                self.current_tab = t
                self.set_picture_for_current_tab()
                return True
            elif 'tabs' in arg and self.current_tab.id not in self.tabs:
                self.current_tab = None
                self.picture = None
                return True
        else:
            return 'tabs' in arg and self.modification_made
        return False

    async def info(self, args: tuple = None, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        self.current_tab = None
        self.picture = None
        await self.remote_send()

    async def prepare_for_new_tab(self, args: tuple):
        self.activate_tab = True
        self.current_tab = None
        self.picture = None
        self.status = NameDurationStatus.DOWNLOADING_WAITING
        await self.remote_send()

    async def prepare_for_overwrite_tab(self, args: tuple):
        self.activate_tab = True
        if not self.current_tab:
            self.current_tab = self.tab
            self.set_picture_for_current_tab()
        self.status = NameDurationStatus.DOWNLOADING_WAITING
        await self.remote_send()

    async def prepare_for_current_tab(self, args: tuple, context: Optional[CallbackContext] = None):
        self.picture = None
        self.status = NameDurationStatus.UPDATING_INIT
        await self.remote_send()

    async def toggle_activate(self, args: tuple):
        self.activate_tab = not self.activate_tab
        await self.remote_send()

    def list_tabs(self, links: bool = False) -> str:
        out = ''
        if self.tabs:
            linklen = 0
            for i, t in self.tabs.items():
                if t.active:
                    out += '<b><u>'
                if not links:
                    linklen += len(urladd := f'<a href="{t.url}">') + 4
                else:
                    urladd = ''
                out += (f'/ST{i:07} ' if links else f'{i:07}) ') + ('\U0001F6A6' if t.active else ('<code>' if links else '')) + (urladd if not links else '') + f'{escape(t.title[0:200])}' + (u'\U0001F507' if t.muted else '') + f'{"</a>" if not links else ""}{"</u></b>" if t.active else ("</code>" if links else "")}\n'
                if len(out) - linklen > 3900:
                    break
        else:
            out += 'No Open Tab'
        return out

    async def update(self, context: CallbackContext | None = None) -> str:
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = u'Select button'
        if not self.current_tab:
            self.picture = None
        out = f'<b>Browser {self.name}</b>\n'
        if self.status == NameDurationStatus.UPDATING_INIT:
            out += self.list_tabs(True)
            self.add_button(u'\U0001F519', self.switch_to_idle)
        elif self.status == NameDurationStatus.IDLE:
            self.add_button(u'\U00002139', self.info, args=tuple())
            if self.current_tab or self.tab:
                self.add_button(u'\U0001F501', self.reload)
                self.add_button(u'\U0000274C', self.close, new_row=True)
                btn = u'\U0001F507' if (self.current_tab and not self.current_tab.muted) or (not self.current_tab and not self.tab.muted) else u'\U0001F50A'
                self.add_button(btn, self.toggle_mute, args=(btn, ))
                if self.current_tab:
                    self.add_button(u'\U0001F7E9', self.activate)
                self.add_button(u'\U0001F310', self.prepare_for_overwrite_tab, new_row=True)
            self.add_button(u'\U0001F310\U00002795', self.prepare_for_new_tab)
            self.add_button(u'\U0000270E', self.prepare_for_current_tab)
            if self.tab:
                self.add_button('s', self.key, args=('s', ), new_row=True)
                self.add_button('d', self.key, args=('d', ))
                self.add_button('g', self.key, args=('g', ))
                self.add_button('k', self.key, args=('k', ))
                self.add_button('1.0x', self.key, args=('g', ))
                self.add_button('1.5x', self.key, args=('g' + ('d' * 5), ))
                self.add_button('1.7x', self.key, args=('g' + ('d' * 7), ))
                self.add_button('2.0x', self.key, args=('g' + ('d' * 10), ))
                self.add_button(u'\U00002190', self.key, args=('[ArrowLeft]', ))
                self.add_button(u'\U00002192', self.key, args=('[ArrowRight]', ))
                self.add_button(u'\U00002193', self.key, args=('[ArrowDown]', ))
                self.add_button(u'\U00002191', self.key, args=('[ArrowUp]', ))
            if (t := self.current_tab):
                out += f'<a href="{t.url}">' + (escape(t.title) if t.title else f'ID = {t.id}') + '</a> ' + (u'\U0001F507' if t.muted else '') + ' ' + (u'\U0001F7E9' if t.active else u'\U00002B1B')
            else:
                out += self.list_tabs()
        elif self.status == NameDurationStatus.DOWNLOADING_WAITING:
            self.input_field = 'url'
            try:
                urls = f'urls_{self.user.rowid}'
                await self.redis.zremrangebyscore(urls, '-inf', int(time() - 864000))
                self.lst_sel = await self.redis.zrange(urls, 0, -1, desc=True, withscores=True)
                for i, scurl in enumerate(self.lst_sel):
                    if not i:
                        out += 'Enter or select url:\n'
                    url, score = scurl
                    pinned = score > time()
                    out += f'/ur{i:07} <code>{url[0:150].decode("utf-8")}</code> ' + (f'\U0001F4CD (/up{i:07})' if pinned else f'\U0001F4CC (/pp{i:07})') + '\n'
                    if len(out) > (3700 if not self.picture else 920):
                        break
                if not out:
                    out += 'Enter url:'
            except Exception:
                out += 'Enter url:'
            self.add_button(u'\U0001F7E9' if self.activate_tab else u'\U00002B1B', self.toggle_activate)
            self.add_button(u'\U00002934', self.switch_to_idle)
        return out


class BrowserListMessage(RemoteListMessage):
    redis: Redis = None

    @staticmethod
    def build_remote_info_message(name: str, url: str, sel: bool, navigation: NavigationHandler, user: User) -> RemoteInfoMessage:
        return BrowserInfoMessage(name, url, sel, navigation, redis=BrowserListMessage.redis, user=user)

    @classmethod
    def user_conf_field_to_remotes_dict(cls, navigation: NavigationHandler, proc: ProcessorMessage, sel_only: bool = False, field_id: str = None) -> Dict[str, RemoteInfoMessage]:
        if not BrowserListMessage.redis:
            BrowserListMessage.redis = aioredis.from_url(proc.params.args["redis"], encoding="utf-8", decode_responses=False)
        return super(BrowserListMessage, cls).user_conf_field_to_remotes_dict(navigation, proc, sel_only, field_id)
