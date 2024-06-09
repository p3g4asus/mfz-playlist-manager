from abc import abstractmethod
import asyncio
from datetime import datetime, timedelta
from typing import Any, Coroutine, Optional, Union

from telegram_menu import NavigationHandler
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD
from common.const import CMD_REFRESH
from common.playlist import Playlist, PlaylistMessage
from common.user import User
from server.telegram.cache import cache_store
from server.telegram.message import NameDurationStatus, StatusTMessage


class RefreshingTMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: Optional[timedelta] = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, playlist: Playlist = None, **argw) -> None:
        super().__init__(navigation, label, picture, expiry_period, inlined, home_after, notification, input_field, user, params, **argw)
        self.playlist = playlist
        self.upd_sta = None
        self.upd_sto = None
        self.refresh_message: PlaylistMessage = None

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
            status = None if not self.refresh_message else self.refresh_message.f(PlaylistMessage.PING_STATUS)
            if status and 'ss' in status:
                stas = status['ss']
                status[PlaylistMessage.PING_STATUS_CONS] = True
                jj = "\n".join(stas)
                upd = f'<code>{jj}</code>\n'
            else:
                upd = ''
            return f'{upd}{self.playlist.name} updating {"." * (self.sub_status & 0xFF)}'

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
        self.refresh_message = pl
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.playlist = pl.playlist
            cache_store(self.playlist)
            self.return_msg = f'Refresh OK :thumbs_up: ({pl.n_new} new videos)'
        else:
            self.return_msg = f'Error {pl.rv} refreshing {self.playlist.name} :thumbs_down:'
        self.refresh_message = None
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
