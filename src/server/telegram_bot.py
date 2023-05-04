import asyncio
import datetime
import json
import logging
import traceback
from aiohttp import ClientSession
from telegram.ext._callbackcontext import CallbackContext
from telegram_menu import TelegramMenuSession, BaseMessage, NavigationHandler
from telegram_menu.models import emoji_replace
from typing import Optional
from urllib.parse import urlencode
from common.const import CMD_DUMP

from common.playlist import LOAD_ITEMS_ALL, LOAD_ITEMS_NO, LOAD_ITEMS_UNSEEN, Playlist, PlaylistItem, PlaylistMessage

_LOGGER = logging.getLogger(__name__)


class MyNavigationHandler(NavigationHandler):
    """Example of navigation handler, extended with a custom "Back" command."""

    async def goto_back(self) -> int:
        """Do Go Back logic."""
        return await self.select_menu_button("Back")


class ProcessorMessage(object):
    def __init__(self, userid, processors, executor):
        self.userid = userid
        self.processors = processors
        self.executor = executor

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


class ListPlMessage(BaseMessage, ProcessorMessage):
    """Single action message."""

    LABEL = "listpl"
    MAX_ITEMS = 5
    MAX_BUTTONS = 6

    def __init__(self, navigation: MyNavigationHandler, message_args=None, userid=None, button_offset=-1, playlists=None) -> None:
        """Init SignUpAppMessage class."""
        BaseMessage.__init__(
            navigation,
            ListPlMessage.LABEL,
            expiry_period=None,
            inlined=False,
            home_after=False,
        )
        ProcessorMessage.__init__(userid, message_args[0].processors2, message_args[0].executor)
        self.loop = asyncio.get_event_loop()
        self.params = message_args[0]
        self.user_data = dict()
        self.button_offset = button_offset
        self.playlists = playlists

    def get_playlist_message(self):
        return PlaylistMessage(CMD_DUMP, useri=self.userid)

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        if not self.user_data:
            self.user_data = context.user_data.setdefault('user_data', dict())
        if not self.playlists:
            plout = await self.process(self.get_playlist_message())
            self.playlists = plout.playlists
        if self.button_offset < 0:
            ln = len(plout.playlists)
            nbuttons = int(ln / ListPlMessage.MAX_ITEMS)
            last_button_items = ln % ListPlMessage.MAX_ITEMS
            npages = int(nbuttons / ListPlMessage.MAX_BUTTONS)
            last_pages_buttons = npages % ListPlMessage.MAX_BUTTONS
        if ln:
            for i in range(ListPlMessage.MAX_BUTTONS):
                if i ==
            

        """Update message content."""
        content = "Things remembered:\n" + ('\n'.join(self.user_data['words']))
        return content

    async def text_input(self, text: str, context: Optional[CallbackContext] = None) -> None:
        """Receive text from console. If used, this function must be instantiated in the child class."""
        words = self.user_data['words']
        if text.startswith('$') and len(text[1:].strip()) > 0 and not text[1:].strip() in words:
            words.append(text[1:].strip())


class SignUpAppMessage(BaseMessage):
    """Single action message."""

    LABEL = "signup"  # la label è usata nei bottoni inlined per capire che bottone è stato premuto
    STATUS_IDLE = 0
    STATUS_REGISTER = 2

    def __init__(self, navigation: MyNavigationHandler, message_args=None) -> None:
        """Init SignUpAppMessage class."""
        super().__init__(
            navigation,
            SignUpAppMessage.LABEL,
            expiry_period=None,
            inlined=False,
            home_after=False,
        )
        self.status = SignUpAppMessage.STATUS_IDLE
        self.url = ''
        self.params = message_args[0]

    def update(self) -> str:
        """Update message content."""
        content = "Please insert auth link"
        return content

    async def text_input(self, text: str, context: Optional[CallbackContext] = None) -> None:
        """Receive text from console. If used, this function must be instantiated in the child class."""
        if text:
            if self.status != SignUpAppMessage.STATUS_REGISTER:
                self.url = text
                url = f'{text}?{urlencode(dict(act="start", username=self.navigation.user_name))}'
            else:
                url = f'{self.url}?{urlencode(dict(act="finish", token=text, username=self.navigation.user_name))}'

            async with ClientSession() as session:
                async with session.get(url) as resp:
                    keyboard = self.gen_keyboard_content()
                    finished = False
                    if resp.status >= 200 and resp.status < 300:
                        if self.status == SignUpAppMessage.STATUS_IDLE:
                            content = ':thumbs_up: Please insert the token code'
                            self.status = SignUpAppMessage.STATUS_REGISTER
                        else:
                            content = ':thumbs_up: Restart the bot with /start command'
                            self.status = SignUpAppMessage.STATUS_IDLE
                            finished = True
                    else:
                        content = f':thumbs_down: Error is <b>{str(await resp.read())} ({resp.status})</b>. <i>Please try again inserting link.</i>'
                        self.status = SignUpAppMessage.STATUS_IDLE

                    await self.navigation.send_message(emoji_replace(content), keyboard)
                    if finished:
                        idmsg = await self.navigation.goto_home()
                        await self.navigation.delete_message(self.message_id)
                        await self.navigation.delete_message(idmsg)
            _LOGGER.info(f"Handle for {text}")


class StartMessage(BaseMessage):
    """Start menu, create all app sub-menus."""

    LABEL = "start"

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
            action_message = ListPlMessage(self.navigation, message_args=[self.params], userid=res['userid'])
            # second_menu = SecondMenuMessage(navigation, update_callback=message_args)
            self.add_button(label="📝 List", callback=action_message)
            self.uid = res['userid']
            self.username = res['username']
        else:
            action_message = SignUpAppMessage(self.navigation, message_args=[self.params])
            # second_menu = SecondMenuMessage(navigation, update_callback=message_args)
            self.add_button(label="✍ Sign Up", callback=action_message)
            # self.add_button(label="Second menu", callback=second_menu)

    def __init__(self, navigation: MyNavigationHandler, message_args) -> None:
        """Init StartMessage class."""
        super().__init__(navigation, StartMessage.LABEL)
        self.params = message_args[0]
        _LOGGER.debug(f'Start Message {message_args[0].args}')
        self.username = None
        self.uid = None
        # define menu buttons

    async def update(self):
        await self.async_init()
        if self.username:
            return f'Hello <b>{self.username}</b> 🎵'
        else:
            return 'Hello: please click ✍ Sign Up'

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
    TelegramMenuSession(api_key, persistence_path=params.args['pickle']).start(start_message_class=StartMessage, start_message_args=[params], navigation_handler_class=MyNavigationHandler, stop_signals=())
