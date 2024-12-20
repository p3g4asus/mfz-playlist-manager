from datetime import datetime
import logging
import re
from typing import Any, Coroutine, Dict, List, Optional
from urllib.parse import ParseResult, urlencode, urlunparse

from telegram_menu import MenuButton, NavigationHandler
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD

from common.const import CMD_REMOTEPLAY_JS, CMD_REMOTEPLAY_JS_DEL, CMD_REMOTEPLAY_JS_FFW, CMD_REMOTEPLAY_JS_GOTO, CMD_REMOTEPLAY_JS_NEXT, CMD_REMOTEPLAY_JS_PAUSE, CMD_REMOTEPLAY_JS_PREV, CMD_REMOTEPLAY_JS_RATE, CMD_REMOTEPLAY_JS_REW, CMD_REMOTEPLAY_JS_SEC
from common.user import User
from server.telegram.message import NameDurationStatus, duration2string
from server.telegram.remote import RemoteInfo, RemoteInfoMessage, RemoteListMessage

_LOGGER = logging.getLogger(__name__)


class PlayerInfo(RemoteInfo):
    DEFAULT_VINFO = dict(title='N/A', durs='0s', tot_n=0, tot_durs='0s', duri=0, chapters=[])
    DEFAULT_PINFO = dict(sec=0)

    def __init__(self, name: str, url: str, sel: bool) -> None:
        super().__init__(name, url, sel)
        pr = self.parsed_url
        self.plnames: List[str] = list(pr[1]['name'])
        self.default_plnames: bool = True
        self.pinfo: Dict[str, str] = PlayerInfo.DEFAULT_PINFO
        self.vinfo: Dict[str, str] = PlayerInfo.DEFAULT_VINFO
        self.play_url = urlunparse(pr[0]._replace(path=pr[0].path[1:-len(PlayerInfo.END_URL_PATH)] + '-s/play/workout.htm')._replace(query=''))
        self.base_cmd: ParseResult = pr[0]._replace(path=pr[0].path[1:-len(PlayerInfo.END_URL_PATH)] + f'/rcmd/{pr[1]["hex"][0]}')

    def process_incoming_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rv = None
        if 'pinfo' in data:
            rv = data
            if isinstance(data['pinfo'], dict):
                self.pinfo = data['pinfo']
            else:
                self.pinfo = PlayerInfo.DEFAULT_PINFO
        if 'vinfo' in data:
            rv = data
            if isinstance(data['vinfo'], dict):
                self.vinfo = data['vinfo']
            else:
                self.vinfo = PlayerInfo.DEFAULT_VINFO
        if 'plst' in data:
            rv = data
            if isinstance(data['plst'], list):
                self.plnames = data['plst']
                self.default_plnames = False
        return rv


class PlayerInfoMessage(RemoteInfoMessage):
    def __init__(self, navigation: NavigationHandler, player_info: PlayerInfo, user: User = None, params: object = None, **argw) -> None:
        self.time_btn: datetime = None
        self.btn_type: int = 0
        self.time_status: int = 0
        self.info_changed: int = -1
        super().__init__(navigation, player_info, user, params, **argw)

    def calc_dyn_sec(self):
        if not self.time_btn:
            return 0
        else:
            return (round((datetime.now() - self.time_btn).seconds * 5) + 10) * self.btn_type

    async def refresh_msg(self):
        if self.time_btn:
            passed = (datetime.now() - self.time_btn).seconds
            if passed > 120:
                await self.switch_to_idle()
            else:
                await self.edit_or_select()

    async def play(self, args: tuple):
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_PAUSE)

    async def rate(self, args: tuple):
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_RATE, n=args[0])

    async def move(self, args: tuple):
        val = args[0]
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_FFW if val > 0 else CMD_REMOTEPLAY_JS_REW, n=abs(val))

    async def move_pl(self, args: tuple):
        val = args[0]
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_NEXT if val > 0 else (CMD_REMOTEPLAY_JS_PREV if val < 0 else CMD_REMOTEPLAY_JS_DEL))

    async def switch_pl(self, args: tuple):
        val = args[0]
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_GOTO, link=self.pi.play_url + f'?{urlencode(dict(name=val))}')
        await self.switch_to_idle()

    async def move_abs(self, args: tuple):
        val = args[0]
        await self.pi.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_SEC, n=val)

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.IDLE:
            text = text.strip()
            try:
                sect = None
                rel = 0
                if text.startswith('/TT'):
                    text = text[3:]
                elif (mo := re.search(r'^\s*([\-\+])', text)):
                    rel = 1 if mo.group(1) == '+' else -1
                    text = text[mo.end():]
                while True:
                    if (mo := re.search(r'^\s*([0-9]+)\s*([msh]?)', text)):
                        sec = int(mo.group(1))
                        um = mo.group(2)
                        if um == 'm':
                            sec *= 60
                        elif um == 'h':
                            sec *= 3600
                        text = text[len(mo.group(0)):]
                        sect = sec if sect is None else sect + sec
                    else:
                        break
                if sect is not None:
                    if rel:
                        await self.move((sect * rel, ))
                    else:
                        await self.move_abs((sect, ))
            except Exception:
                pass

    async def info(self, args: tuple):
        await self.pi.sendGenericCommand(get=['vinfo', 'pinfo', 'plst'])
        self.info_changed = 1
        await self.edit_or_select()

    async def manage_state_change(self, args: tuple, context: Optional[CallbackContext] = None):
        btn_id: int = 0
        f = args[0]
        if isinstance(f, int):
            btn_id = f
            args = args[1:]
        _LOGGER.debug(f'btn_id={btn_id} type={self.btn_type}')
        if btn_id and not self.btn_type:
            self.btn_type = btn_id
            self.time_btn = datetime.now()
            name: str = f"manage_state_change{id(self)}"
            self.scheduler_job = self.navigation.scheduler.add_job(
                self.refresh_msg,
                "interval",
                name=name,
                id=name,
                seconds=1,
                replace_existing=True,
            )
            await self.switch_to_status((NameDurationStatus.RENAMING, ), context)
            return
        elif not btn_id and self.btn_type:
            self.btn_type = 0
            self.time_btn = None
            await self.switch_to_idle()
            if args[0] == self.move:
                return
        elif btn_id and self.btn_type and self.btn_type != btn_id:
            self.btn_type = btn_id
            self.time_btn = datetime.now()
            return
        elif btn_id and self.btn_type:
            await self.move((self.calc_dyn_sec(),))
            self.btn_type = 0
            self.time_btn = None
            await self.switch_to_idle()
            return
        await args[0](args[1:])

    async def update(self, context: CallbackContext | None = None) -> str:
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = u'\U000023F2 Timestamp'
        addtxt = ''
        if self.status == NameDurationStatus.IDLE or self.status == NameDurationStatus.RENAMING:
            if self.info_changed < 0 or (not self.info_changed and self.pi.default_plnames):
                self.info_changed = 0
                await self.pi.sendGenericCommand(get='plst')
            self.add_button(u'\U000023EF', self.manage_state_change, args=(self.play,))
            self.add_button(u'\U00002139', self.manage_state_change, args=(self.info, ))
            self.add_button(u'\U000023EE', self.manage_state_change, args=(self.move_pl, -1), new_row=True)
            self.add_button(u'\U000023ED', self.manage_state_change, args=(self.move_pl, +1))
            self.add_button(u'\U000023ED \U0001F5D1', self.manage_state_change, args=(self.move_pl, 0), new_row=True)
            self.add_button(u'\U0001F51C', self.manage_state_change, args=(self.switch_to_status, NameDurationStatus.DOWNLOADING_WAITING, context))
            self.add_button(u'\U000025B61x', self.manage_state_change, args=(self.rate, 1.0))
            self.add_button(u'\U000025B61.5x', self.manage_state_change, args=(self.rate, 1.5))
            self.add_button(u'\U000025B61.8x', self.manage_state_change, args=(self.rate, 1.8))
            self.add_button(u'\U000025B62x', self.manage_state_change, args=(self.rate, 2))
            if self.status == NameDurationStatus.RENAMING:
                if self.btn_type == 1:
                    addtxt = f'{self.calc_dyn_sec()}'
                elif self.btn_type == -1:
                    addtxt = f'{-self.calc_dyn_sec()}'
            self.add_button(u'...\U000023EA', self.manage_state_change, args=(-1, self.move, -1), new_row=True)
            self.add_button(u'\U000023E9...', self.manage_state_change, args=(+1, self.move, +1))
            self.add_button(u'10s\U000023EA', self.manage_state_change, args=(self.move, -10), new_row=True)
            self.add_button(u'\U000023E910s', self.manage_state_change, args=(self.move, +10))
            self.add_button(u'30s\U000023EA', self.manage_state_change, args=(self.move, -30), new_row=True)
            self.add_button(u'\U000023E930s', self.manage_state_change, args=(self.move, +30))
            self.add_button(u'60s\U000023EA', self.manage_state_change, args=(self.move, -60), new_row=True)
            self.add_button(u'\U000023E960s', self.manage_state_change, args=(self.move, +60))
            self.add_button(label=u"\U0001F519", callback=self.navigation.goto_back, new_row=True)
        elif self.status == NameDurationStatus.DOWNLOADING_WAITING:
            self.input_field = u'\U0001F449'
            for plname in self.pi.plnames:
                self.add_button(plname, self.switch_pl, args=(plname, ))
            self.add_button(u'\U00002934', self.switch_to_idle)
        if addtxt:
            rv = ''
            for x in addtxt:
                rv += x + u'\U0000FE0F\U000020E3'
            return rv
        elif self.info_changed <= 0:
            idx = self.time_status
            self.time_status += 1
            if self.time_status >= len(self.TIMES):
                self.time_status = 0
            return self.TIMES[idx]
        else:
            self.info_changed = 0
            rv = f'{self.pi.vinfo["title"]}\n'
            rv += u'\U000023F3 ' + f'{self.pi.vinfo["durs"]}\n'
            rv += u'\U0001F4B0 ' + f'{self.pi.vinfo["tot_n"]} ({self.pi.vinfo["tot_durs"]})\n'
            no = int(round(30.0 * (perc := self.pi.pinfo["sec"] / self.pi.vinfo["duri"]))) if self.pi.vinfo["duri"] else (perc := 0)
            rv += f'<code>{duration2string(round(self.pi.pinfo["sec"]))} ({self.pi.vinfo["durs"]})\n[' + (no * 'o') + ((30 - no) * ' ') + f'] {round(perc * 100)}%</code>'
            for ch in self.pi.vinfo["chapters"]:
                rv += f'\n/TT{int(ch["start_time"])}s {ch["title"]}'
            return rv


class PlayerListMessage(RemoteListMessage):
    @staticmethod
    def build_remote_info(name: str, url: str, sel: bool) -> RemoteInfo:
        return PlayerInfo(name, url, sel)

    @staticmethod
    def build_remote_info_message(navigation: NavigationHandler, remote_info: RemoteInfo, user: User = None, params: object = None, **argw) -> RemoteInfoMessage:
        return PlayerInfoMessage(navigation, remote_info, user, params=params, **argw)
