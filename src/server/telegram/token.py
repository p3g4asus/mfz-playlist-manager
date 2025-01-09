import asyncio
from datetime import datetime, timedelta
from time import time
from typing import List, Optional

from telegram_menu import MenuButton, NavigationHandler
from telegram.ext._callbackcontext import CallbackContext
from common.const import CMD_TOKEN
from common.playlist import PlaylistMessage
from common.user import User
from server.telegram.message import NameDurationStatus, StatusTMessage


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
            next_run_time=StatusTMessage.datenow()
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
