import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import re
from time import time
from typing import Any, List, Optional

from telegram_menu import MenuButton, NavigationHandler
from telegram.ext._callbackcontext import CallbackContext

from common.const import CMD_USER_SETTINGS
from common.playlist import PlaylistMessage
from common.user import User
from server.telegram.message import NameDurationStatus, StatusTMessage


class GenericSetting:
    def __init__(self, ptn: str, desc: str, field: str, default: str, sett: dict | None = None) -> None:
        self.re: re.Pattern = re.compile(ptn)
        self.field: str = field
        self.desc: str = desc
        self.default: Any = default
        if sett:
            self.from_user_conf(sett)
        else:
            self.obj_value: Any = default

    def to_user_conf(self, sett: dict) -> bool:
        if sett.get(self.field) != self.obj_value:
            sett[self.field] = self.obj_value
            return True
        else:
            return False

    def from_user_conf(self, sett: dict):
        self.obj_value = sett[self.field] if self.field in sett else self.default

    def match_to_value(self, match: re.Match) -> Any:
        self.obj_value = match.group(1 if self.re.groups else 0)
        return self.obj_value

    def _parse(self, text: str) -> re.Match:
        return self.re.search(text)

    def on_text_enter(self, text: str) -> bool:
        return bool((mo := self._parse(text)) and self.match_to_value(mo))

    def __str__(self) -> str:
        return f'<code>{self.desc}: <u>{self.obj_value}</u></code> /{self.field}\n'

    def req(self) -> str:
        return f'Enter {self.desc}:'


class PasswordSetting(GenericSetting):
    def __str__(self) -> str:
        s = f'{self.obj_value[0]}{(len(self.obj_value) - 2) * "*"}{self.obj_value[-1]}' if self.obj_value else "----------"
        return f'<code>{self.desc}: <u>{s}</u></code> /{self.field}\n'


class UserSettingsMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, **argw) -> None:
        super().__init__(navigation, label=f'{self.__class__.__name__}{id(self)}', inlined=True, expiry_period=timedelta(minutes=10), user=user, params=params, **argw)
        self.user = User(self.proc.user.toJSON())
        self.re: re.Pattern = None
        self.current_setting: str = ''
        self.changed = False
        cnf = self.user.conf
        if 'settings' not in cnf:
            cnf['settings'] = dict()
        cnf = deepcopy(cnf['settings'])
        self.cnf: dict = cnf
        self.setts: dict[str, GenericSetting] = dict(
            mediaset_user=GenericSetting(
                r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
                'Mediaset username',
                'mediaset_user',
                'anyuser@domain.com',
                cnf
            ),
            mediaset_password=PasswordSetting(
                r'^.{6,}$',
                'Mediaset password',
                'mediaset_password',
                'mypassisgood',
                cnf
            ),
            youtube_apikey=PasswordSetting(
                r'^.{30,}$',
                'Yputube API key',
                'youtube_apikey',
                '',
                cnf
            )
        )

    async def abort_edit(self, context: Optional[CallbackContext] = None):
        self.current_setting = ''
        await self.edit_or_select()

    async def settings_save(self, context: Optional[CallbackContext] = None):
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
        pl = PlaylistMessage(CMD_USER_SETTINGS, settings=self.cnf)
        opt = time()
        pl = await self.proc.process(pl)
        df = time() - opt
        if df < 1.5:
            await asyncio.sleep(1.5 - df)
        if pl.rv == 0:
            self.proc.user.conf['settings'] = deepcopy(self.cnf)
            self.return_msg = ':thumbs_up:'
            self.changed = False
        else:
            self.return_msg = f'Error {pl.rv} saving settings :thumbs_down:'
        await self.switch_to_idle()

    async def text_input(self, text: str, context: Optional[CallbackContext] = None) -> None:
        if self.current_setting:
            s = self.setts[self.current_setting]
            if s.on_text_enter(text):
                if s.to_user_conf(self.cnf):
                    self.changed = True
                self.current_setting = ''
                await self.edit_or_select(context)
        elif text and text[0] == '/':
            for k, s in self.setts.items():
                if text == '/' + k:
                    self.current_setting = k
                    await self.edit_or_select(context)
                    break

    async def update(self, context: CallbackContext | None = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        if self.has_expired():
            self.current_setting = ''
        if self.status == NameDurationStatus.IDLE:
            if not self.current_setting:
                msg = ''
                for _, s in self.setts.items():
                    msg += str(s)
                if self.changed:
                    self.add_button(u'\U0001F4BE', self.settings_save)
                # self.add_button(label=u"\U0001F519", callback=self.navigation.goto_back)
            else:
                self.add_button(':cross_mark: Abort', self.abort_edit)
                msg = self.setts[self.current_setting].req()
        else:
            msg = f'Saving {"." * (self.sub_status & 0xFF)}'
        return msg if not self.return_msg else f'{msg}\n<b>{self.return_msg}</b>'
