import asyncio
from datetime import timedelta
from time import sleep
import logging
from typing import List, Optional
from urllib.parse import urlencode, urlparse
from aiohttp import ClientSession
from telegram_menu import BaseMessage, MenuButton, NavigationHandler, TelegramMenuSession
from telegram_menu.models import emoji_replace
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD

from common.const import CMD_TOKEN
from common.playlist import PlaylistMessage
from common.user import User
from server.telegram.browser import BrowserListMessage
from server.telegram.playlist import PlaylistAddTMessage, PlaylistsPagesTMessage
from server.telegram.cache import cache_del_user
from server.telegram.message import MyNavigationHandler, ProcessorMessage, YesNoTMessage
from server.telegram.player import PlayerListMessage
from server.telegram.token import TokenMessage
from server.telegram.user import UserSettingsMessage


_LOGGER = logging.getLogger(__name__)

__bot_stopped = True


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
                        idmsg = await self.navigation.goto_home(sync=True)
                        await self.navigation.delete_message(self.message_id)
                        await self.navigation.delete_message(idmsg)
            _LOGGER.info(f"Handle for {text}")


class SignOutTMessage(YesNoTMessage):
    def __init__(self, navigation: NavigationHandler) -> None:
        super().__init__(navigation, '\U00002705\U0001F6AA', ':cross_mark:\U0001F6AA')

    async def on_yes(self, _: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.navigation._menu_queue[0].sign_out(_)


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

    async def list_page_of_playlists(self, page, context: Optional[CallbackContext] = None, sync: bool = False):
        if self.playlists_lister:
            await self.playlists_lister.goto_page((page, ), context, sync)

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
            self.add_button(label="\U0001F3A7 Player", callback=PlayerListMessage(self.navigation, user=self.user, params=self.params))
            self.add_button(label="\U0001F4D9 Browser", callback=BrowserListMessage(self.navigation, user=self.user, params=self.params))
            self.add_button(label="\U00002795 Add", callback=PlaylistAddTMessage(self.navigation, user=self.user, params=self.params))
            self.add_button(label="\U000026D7 Token", callback=TokenMessage(self.navigation, user=self.user, params=self.params))
            self.add_button(label='\U00002699 Settings', callback=UserSettingsMessage(self.navigation, user=self.user, params=self.params))
            self.add_button(label="\U00002B55 Message Cache Clear", callback=self.cache_clear)
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
        super().__init__(navigation, self.__class__.__name__, expiry_period=timedelta(weeks=500))
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

    def slash_message_processed(self, text: str) -> bool:
        return False

    async def text_input(self, text: str, context: Optional[CallbackContext] = None) -> None:
        """Receive text from console. If used, this function must be instantiated in the child class."""
        _LOGGER.info(f"Handle for {text}")


async def stop_telegram_bot():
    global __bot_stopped
    __bot_stopped = True
    raise SystemExit


def start_telegram_bot(params, loop):
    global __bot_stopped
    __bot_stopped = False
    logging.getLogger('hpack.hpack').setLevel(logging.INFO)
    loop = asyncio.set_event_loop(loop)
    api_key = params.args['telegram']
    while True:
        _LOGGER.info(f'Starting bot with {params} in loop {id(loop)}')
        TelegramMenuSession(api_key, persistence_path=params.args['pickle']).start(start_message_class=StartTMessage, start_message_args=[params], navigation_handler_class=MyNavigationHandler, stop_signals=())
        if __bot_stopped:
            _LOGGER.info('Exiting telegram session...')
            break
        else:
            _LOGGER.warning('Bot crashed: restarting in 7 seconds')
            sleep(7)
