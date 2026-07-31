import logging
from typing import Any, Dict, List, Optional

from telegram_menu import NavigationHandler
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD

from common.const import CMD_REMOTEDESKTOP_JS
from common.user_alc_ses import User
from server.telegram.message import NameDurationStatus
from server.telegram.remote import RemoteInfoMessage, RemoteListMessage

_LOGGER = logging.getLogger(__name__)


class DesktopInfoMessage(RemoteInfoMessage):

    def __init__(self, name: str, url: str, sel: bool, navigation: NavigationHandler, remoteid: int) -> None:
        RemoteInfoMessage.__init__(self, name, url, sel, navigation, remoteid)
        self.commands: List[str] = []
        self.last_commands: List[str] = []

    @staticmethod
    def get_my_hex_prefix() -> str:
        return 'k'

    @staticmethod
    def get_dest_hex_prefix():
        return 'j'

    def notification_has_to_be_sent(self, arg):
        if 'commands' in arg:
            if arg['commands'] != self.last_commands:
                self.last_commands = arg['commands']
                return True
        return False

    def process_incoming_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rv = None
        if 'commands' in data:
            rv = data
            if isinstance(data['commands'], list):
                self.commands = data['commands']
        return rv

    async def perform(self, args: tuple = None, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.sendGenericCommand(cmd=CMD_REMOTEDESKTOP_JS, sub=args[0])

    async def update(self, context: CallbackContext | None = None) -> str:
        rv = await RemoteInfoMessage.update(self, context)
        if self.status == NameDurationStatus.IDLE:
            for c in self.commands:
                self.add_button(c, self.perform, args=(c, ))
        return rv + 'Select command:'


class DesktopListMessage(RemoteListMessage):
    @staticmethod
    def build_remote_info_message_inner(name: str, url: str, sel: bool, navigation: NavigationHandler, remoteid: int, user: User) -> RemoteInfoMessage:
        return DesktopInfoMessage(name, url, sel, navigation, remoteid)
