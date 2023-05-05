import asyncio
import datetime
import json
import logging
import re
import traceback
from abc import abstractmethod
from aiohttp import ClientSession
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD
from telegram_menu import TelegramMenuSession, BaseMessage, NavigationHandler, ButtonType
from telegram_menu.models import emoji_replace
from typing import Optional, Union
from urllib.parse import urlencode, urlparse
from common.const import CMD_DEL, CMD_DUMP, CMD_REN

from common.playlist import LOAD_ITEMS_ALL, LOAD_ITEMS_NO, LOAD_ITEMS_UNSEEN, Playlist, PlaylistItem, PlaylistMessage

_LOGGER = logging.getLogger(__name__)


class MyNavigationHandler(NavigationHandler):
    """Example of navigation handler, extended with a custom "Back" command."""

    async def goto_back(self) -> int:
        """Do Go Back logic."""
        return await self.select_menu_button("Back")


class ProcessorMessage(object):
    def __init__(self, userid, username, params):
        self.userid = userid
        self.username = username
        self.params = params
        self.processors = params.processors2,
        self.executor = params.executor

    async def process(self, pl):
        for k, p in self.processors.items():
            _LOGGER.debug(f'Checking {k}')
            if p.interested(pl):
                out = await p.process(None, pl, self.userid, self.executor)
                if out:
                    break
                else:
                    return out
        return None


class NameDurationTMessage(BaseMessage, ProcessorMessage):
    def __init__(self, navigation, index, myid, name, secs, thumb, obj, userid, username, params) -> None:
        BaseMessage.__init__(
            self,
            navigation,
            f'{self.__class__.__name__}_{myid}',
            picture=thumb,
            expiry_period=None,
            inlined=True,
            home_after=False,
        )
        ProcessorMessage.__init__(self, userid, username, params)
        self.index = index
        self.id = myid
        self.name = name
        self.secs = secs
        self.thumb = thumb
        self.obj = obj


class PlaylistTMessage(NameDurationTMessage):
    IDLE = 0
    RENAMING = 1
    DELETING = 2

    async def delete_playlist_2(self):
        pl = PlaylistMessage(CMD_DEL, playlistId=self.id)
        pl = await self.process(pl)
        if pl.rv == 0:
            self.edit_message()
            await self.navigation.goto_home()
            pages = PlaylistsPagesTMessage(navigation=self.navigation, userid=self.userid, username=self.username, params=self.params)
            await self.navigation.goto_menu(pages)

    async def rename_playlist_2(self, newname):
        pl = PlaylistMessage(CMD_REN, playlistId=self.id, to=newname)
        pl = await self.process(pl)
        if pl.rv == 0:
            self.name = newname
            await self.edit_message()

    async def delete_playlist(self, data):
        confirm = json.loads(data)
        if confirm:
            await self.delete_playlist_2()
        return ''

    async def rename_playlist(self, data):
        newname = json.loads(data)
        if newname:
            if re.match('[a-zA-Z0-9_]+', newname) and newname != self.name:
                old = self.name
                await self.rename_playlist_2(newname)
                return f'{old} :right_arrow: {newname} :thumbs_up:'
            else:
                return f'{newname} invalid :thumbs_down:'
        else:
            return ''

    async def update(self, context: CallbackContext | None = None) -> str:
        self.add_button(':cross_mark:', self.delete_playlist, web_app_url=f'http://127.0.0.1:{self.params.args["port"]}/static/telegram_web.html?action={self.DELETING}')
        self.add_button(u'\U00002328', self.rename_playlist, web_app_url=f'http://127.0.0.1:{self.params.args["port"]}/static/telegram_web.html?action={self.RENAMING}')


class GroupOfNameDurationItems(object):

    def __init__(self):
        self.items = []
        self.start_item = -1
        self.stop_item = -1

    def is_valid(self):
        return self.start_item or self.stop_item

    def add_item(self, item):
        if not self.items:
            self.start_item = item.index
        self.items.append(item)
        self.stop_item = item.index


class MultipleGroupsOfItems(object):

    def __init__(self):
        self.start_item = -1
        self.stop_item = -1
        self.next_page = MultipleGroupsOfItems()
        self.back_page = None
        self.groups = []

    def is_valid(self):
        return self.start_item >= 0 and self.stop_item >= 0

    def set_start_stop(self, sta, sto):
        self.start_item = sta
        self.stop_item = sto
        self.label = f'{self.__class__.__name__}_{sta}_{sto}'

    def get_next_page(self):
        return self.next_page

    def add_group(self, grp):
        self.groups.append(grp)

    def set_back_page(self, val):
        self.back_page = val


class PageGenerator(object):

    @abstractmethod
    def item_convert(self, item, index):
        return

    @abstractmethod
    async def get_items_list(self):
        return


class PlaylistsPagesGenerator(PageGenerator, ProcessorMessage):
    def __init__(self, userid, username, params):
        ProcessorMessage.__init__(
            self,
            userid,
            username,
            params
        )

    def item_convert(self, item, index, navigation):
        duration = 0
        img = None
        for pli in item.items:
            duration += pli.dur
            if not img:
                img = pli.img
        return PlaylistTMessage(navigation, index, pli.rowid, pli.name, duration, img, item)

    def get_playlist_message(self):
        return PlaylistMessage(CMD_DUMP, useri=self.userid)

    async def get_items_list(self):
        plout = await self.process(self.get_playlist_message())
        return plout.playlists


class ListPagesTMessage(BaseMessage, PageGenerator):

    def __init__(self, label: str, update_str: str, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6) -> None:
        BaseMessage.__init__(
            self,
            navigation,
            label,
            expiry_period=None,
            inlined=False,
            home_after=False,
        )
        self.max_items_per_group = max_items_per_group
        self.max_group_per_page = max_group_per_page
        self.update_str = update_str
        self.first_page = None

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        items = await self.get_items_list()
        nitems = len(items)
        last_group_items = nitems % self.max_items_per_group
        ngroups = int(nitems / self.max_items_per_group) + (1 if last_group_items else 0)
        last_page_groups = ngroups % self.max_group_per_page
        npages = int(ngroups / self.max_group_per_page) + (1 if last_page_groups else 0)
        if nitems:
            oldpage = None
            self.first_page = thispage = MultipleGroupsOfItems()
            current_item = 0
            for i in range(npages):
                groups_of_this_page = last_page_groups if i == npages - 1 else self.max_group_per_page
                start = current_item
                for j in range(groups_of_this_page):
                    items_of_this_group = last_group_items if i == npages - 1 and j == groups_of_this_page - 1 else self.max_items_per_group
                    group = GroupOfNameDurationItems(navigation=self.navigation)
                    thispage.add_group(group)
                    for k in range(items_of_this_group):
                        item = self.item_convert(items[current_item], current_item)
                        group.add_item(item)
                        if k == items_of_this_group - 1:
                            thispage.set_start_stop(start, current_item)
                        current_item += 1
                thispage.set_back_page(oldpage)
                oldpage = thispage
                thispage = thispage.get_next_page()

        return self.update_str


class PlaylistsPagesTMessage(ListPagesTMessage):

    def __init__(self, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, userid=None, username=None, params=None) -> None:
        PlaylistsPagesTMessage.__init__(
            self,
            self.__class__.__name__,
            f'List of <b>{username}</b> playlists',
            navigation,
            max_items_per_group,
            max_group_per_page
        )
        PlaylistsPagesGenerator.__init__(
            self,
            userid,
            username,
            params
        )


class SignUpTMessage(BaseMessage):
    """Single action message."""
    STATUS_IDLE = 0
    STATUS_REGISTER = 2

    def __init__(self, navigation: MyNavigationHandler, message_args=None) -> None:
        """Init SignUpTMessage class."""
        super().__init__(
            navigation,
            self.__class__.__name__,
            expiry_period=None,
            inlined=False,
            home_after=False,
        )
        self.status = SignUpTMessage.STATUS_IDLE
        self.url = ''
        self.params = message_args[0]
        self.user_data = None

    def update(self, context: Optional[CallbackContext] = None) -> str:
        """Update message content."""
        content = "Please insert auth link"
        if content:
            self.user_data = context.user_data.setdefault('user_data', dict())
        return content

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


class StartTMessage(BaseMessage):
    """Start menu, create all app sub-menus."""

    @staticmethod
    async def check_if_username_registred(db, tg):
        res = None
        try:
            async with db.execute(
                '''
                SELECT username, rowid FROM user
                WHERE tg = ?
                ''', (tg,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    res = dict(userid=row['rowid'], username=row['username'])
        except Exception:
            _LOGGER.warning(f"TGDB access error: {traceback.format_exc()}")
        return res

    async def async_init(self):
        res = await self.check_if_username_registred(self.params.db2, self.navigation.user_name)
        if res:
            action_message = PlaylistsPagesTMessage(
                self.navigation,
                params=self.params,
                userid=res['userid'],
                username=res['username'],
                params=self.params)
            # second_menu = SecondMenuMessage(navigation, update_callback=message_args)
            self.add_button(label=":memo: List", callback=action_message)
            self.uid = res['userid']
            self.username = res['username']
        else:
            action_message = SignUpTMessage(self.navigation, message_args=[self.params])
            # second_menu = SecondMenuMessage(navigation, update_callback=message_args)
            self.add_button(label=":writing_hand: Sign Up", callback=action_message)
            # self.add_button(label="Second menu", callback=second_menu)

    def __init__(self, navigation: MyNavigationHandler, message_args) -> None:
        """Init StartTMessage class."""
        super().__init__(navigation, self.__class__.__name__)
        self.params = message_args[0]
        _LOGGER.debug(f'Start Message {message_args[0].args}')
        self.username = None
        self.uid = None
        # define menu buttons

    async def update(self):
        await self.async_init()
        if self.username:
            return f'Hello <b>{self.username}</b> :musical_note:'
        else:
            return 'Hello: please click :writing_hand: Sign Up'

    @staticmethod
    def run_and_notify() -> str:
        """Update message content."""
        return "This is a notification"

    async def text_input(self, text: str, context: Optional[CallbackContext] = None) -> None:
        """Receive text from console. If used, this function must be instantiated in the child class."""
        _LOGGER.info(f"Handle for {text}")


def stop_telegram_bot():
    raise SystemExit


def start_telegram_bot(params, loop):
    logging.getLogger('hpack.hpack').setLevel(logging.INFO)
    loop = asyncio.set_event_loop(loop)
    api_key = params.args['telegram']
    _LOGGER.info(f'Starting bot with {params} in loop {id(loop)}')
    TelegramMenuSession(api_key, persistence_path=params.args['pickle']).start(start_message_class=StartTMessage, start_message_args=[params], navigation_handler_class=MyNavigationHandler, stop_signals=())
