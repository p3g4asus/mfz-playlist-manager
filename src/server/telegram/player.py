from datetime import datetime
from html import escape
import logging
import re
from typing import Any, Coroutine, Dict, List, Optional
from urllib.parse import urlencode, urlunparse

from telegram import LinkPreviewOptions
from telegram_menu import MenuButton, NavigationHandler
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD

from common.const import CMD_REMOTEPLAY_JS, CMD_REMOTEPLAY_JS_DEL, CMD_REMOTEPLAY_JS_F5PL, CMD_REMOTEPLAY_JS_FFW, CMD_REMOTEPLAY_JS_GOTO, CMD_REMOTEPLAY_JS_INFO, CMD_REMOTEPLAY_JS_ITEM, CMD_REMOTEPLAY_JS_NEXT, CMD_REMOTEPLAY_JS_PAUSE, CMD_REMOTEPLAY_JS_PREV, CMD_REMOTEPLAY_JS_RATE, CMD_REMOTEPLAY_JS_REW, CMD_REMOTEPLAY_JS_SCHED, CMD_REMOTEPLAY_JS_SEC
from common.playlist import PlaylistItem
from common.user import User
from server.telegram.message import NameDurationStatus, duration2string
from server.telegram.remote import RemoteInfoMessage, RemoteListMessage

_LOGGER = logging.getLogger(__name__)


class PlayerInfoMessage(RemoteInfoMessage):
    DEFAULT_VINFO = dict(tot_n=0, tot_durs='0s', rate=1)
    DEFAULT_PINFO = dict(sec=0)

    def __init__(self, name: str, url: str, sel: bool, navigation: Optional[NavigationHandler]) -> None:
        super().__init__(name, url, sel, navigation, link_preview=LinkPreviewOptions(is_disabled=True))
        pr = self.parsed_url
        self.plitems: List[PlaylistItem] = []
        self.plnames: List[str] = list(pr[1]['name'])
        self.pinfo: Dict[str, str] = PlayerInfoMessage.DEFAULT_PINFO
        self.vinfo: Dict[str, str] = PlayerInfoMessage.DEFAULT_VINFO
        self.play_url = urlunparse(pr[0]._replace(path=pr[0].path[1:-len(PlayerInfoMessage.END_URL_PATH)] + '-s/play/workout.htm')._replace(query=''))
        self.time_btn: datetime = None
        self.btn_type: int = 0
        self.time_status: int = 0
        self.last_pinfo: float = 0.0
        self.default_vinfo: int = 1

    @staticmethod
    def get_my_hex_prefix() -> str:
        return 'h'

    @staticmethod
    def get_dest_hex_prefix():
        return ''

    def notification_has_to_be_sent(self, arg):
        if 'pinfo' in arg:
            if abs(arg['pinfo']['sec'] - self.last_pinfo) > 120:
                self.last_pinfo = self.pinfo['sec']
                return True
        return 'vinfo' in arg

    def process_incoming_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rv = None
        if 'vinfo' in data:
            rv = data
            if isinstance(data['vinfo'], dict):
                self.default_vinfo = 0
                self.vinfo = data['vinfo']
            else:
                self.vinfo = PlayerInfoMessage.DEFAULT_VINFO
        if 'pinfo' in data:
            rv = data
            if isinstance(data['pinfo'], dict):
                self.pinfo = data['pinfo']
                if self.default_vinfo:
                    self.default_vinfo += 1
            else:
                self.pinfo = PlayerInfoMessage.DEFAULT_PINFO
        if 'plst' in data:
            rv = data
            if isinstance(data['plst'], list):
                self.plnames = data['plst']
        if 'ilst' in data:
            rv = data
            if isinstance(data['ilst'], list):
                self.plitems.clear()
                for kk in data['ilst']:
                    self.plitems.append(PlaylistItem(kk))
        return rv

    @staticmethod
    def is_url(ss: str) -> re.Match | None:
        rex = r'(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))'
        return re.search(rex, ss)

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
                await self.remote_send()

    async def play(self, args: tuple):
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_PAUSE)

    async def sync_changes(self, args: tuple):
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_F5PL, n=args[0] if args else '', sched=args[1] if len(args) > 1 else False)
        if args:
            await self.switch_to_idle()

    async def rate(self, args: tuple):
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_RATE, n=args[0])

    async def move(self, args: tuple):
        val = args[0]
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_FFW if val > 0 else CMD_REMOTEPLAY_JS_REW, n=abs(val))

    async def move_pl(self, args: tuple):
        val = args[0]
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_NEXT if val > 0 else (CMD_REMOTEPLAY_JS_PREV if val < 0 else CMD_REMOTEPLAY_JS_DEL))

    async def switch_pl(self, args: tuple):
        val = args[0]
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_GOTO, link=self.play_url + f'?{urlencode(dict(name=val))}')
        await self.switch_to_idle()

    async def move_abs(self, args: tuple):
        val = args[0]
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_SEC, n=val)

    async def schedule(self, url: str):
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_SCHED, n=url)

    async def goto_item(self, idx: int):
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_ITEM, n=idx)

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.IDLE:
            text = text.strip()
            try:
                sect = None
                rel = 0
                if ((mo := re.search(r'^/s\s*(.+)', text)) and (mo := PlayerInfoMessage.is_url(mo.group(1)))):
                    await self.schedule(mo.group(1))
                    return
                elif ((mo := re.search(r'^/I(\d+)', text))):
                    await self.goto_item(int(mo.group(1)))
                    return
                elif text.startswith('/TT'):
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

    async def info(self, args: tuple = ()) -> None:
        await self.sendGenericCommand(cmd=CMD_REMOTEPLAY_JS, sub=CMD_REMOTEPLAY_JS_INFO)

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
        rv = f'<b>Player {self.name}</b>\n'
        if self.status == NameDurationStatus.IDLE or self.status == NameDurationStatus.RENAMING:
            if self.default_vinfo > 1:
                await self.info()
            self.add_button(u'\U000023EF', self.manage_state_change, args=(self.play,))
            self.add_button(u'\U00002139', self.manage_state_change, args=(self.info, ))
            self.add_button(u'\U000023EE', self.manage_state_change, args=(self.move_pl, -1), new_row=True)
            self.add_button(u'\U000023ED', self.manage_state_change, args=(self.move_pl, +1))
            self.add_button(u'\U000023ED \U0001F5D1', self.manage_state_change, args=(self.move_pl, 0))
            self.add_button(u'\U000021C5', self.manage_state_change, args=(self.sync_changes,), new_row=True)
            self.add_button(u'\U0001F4C5', self.manage_state_change, args=(self.switch_to_status, NameDurationStatus.UPDATING_WAITING, context))
            self.add_button(u'\U0001F51C', self.manage_state_change, args=(self.switch_to_status, NameDurationStatus.DOWNLOADING_WAITING, context))
            self.add_button(u'\U000025B61x', self.manage_state_change, args=(self.rate, 1.0), new_row=True)
            self.add_button(u'\U000025B61.5x', self.manage_state_change, args=(self.rate, 1.5))
            self.add_button(u'\U000025B61.8x', self.manage_state_change, args=(self.rate, 1.8), new_row=True)
            self.add_button(u'\U000025B62x', self.manage_state_change, args=(self.rate, 2))
            if self.status == NameDurationStatus.RENAMING:
                if self.btn_type == 1:
                    addtxt = f'{self.calc_dyn_sec()}'
                elif self.btn_type == -1:
                    addtxt = f'{-self.calc_dyn_sec()}'
            self.add_button(u'30s\U000023EA', self.manage_state_change, args=(self.move, -30), new_row=True)
            self.add_button(u'\U000023E930s', self.manage_state_change, args=(self.move, +30))
            self.add_button(u'60s\U000023EA', self.manage_state_change, args=(self.move, -60), new_row=True)
            self.add_button(u'\U000023E960s', self.manage_state_change, args=(self.move, +60))
        elif self.status == NameDurationStatus.DOWNLOADING_WAITING or self.status == NameDurationStatus.UPDATING_WAITING:
            self.input_field = u'\U0001F449'
            for plname in self.plnames:
                self.add_button(plname, self.sync_changes, args=(plname, self.status == NameDurationStatus.UPDATING_WAITING))
            self.add_button(u'\U00002934', self.switch_to_idle)
        if addtxt:
            for x in addtxt:
                rv += x + u'\U0000FE0F\U000020E3'
            return rv
        else:
            plitems = self.plitems
            vinfo = self.vinfo
            rate = vinfo["rate"]
            if 'title' not in vinfo:
                rv += '<b>No more video in playlist</b>'
                idx = -1
                add = ''
            else:
                sec = self.pinfo["sec"] / rate
                rv += f'{escape(vinfo["title"])}\n'
                rv += u'\U000023F3 ' + f'{vinfo["durs"]} ' + u'\U0000231B ' + duration2string(0 if (idx := round(vinfo["duri"] - sec)) < 0 else idx) + '\n'
                rv += u'\U0001F4B0 ' + f'{vinfo["tot_n"]} (\U000023F3 {vinfo["tot_durs"]} \U0000231B {duration2string(round(vinfo["tot_dur"] - vinfo["tot_played"] - sec))})\n'
                no = int(round(30.0 * (perc := sec / vinfo["duri"]))) if vinfo["duri"] else (perc := 0)
                rv += f'<code>{duration2string(round(sec))} ({vinfo["durs"]})\n[' + (no * 'o') + ((30 - no) * ' ') + f'] {round(perc * 100)}% ({rate:.2f}\U0000274E)</code>'
                for ch in vinfo["chapters"]:
                    rv += f'\n/TT{int(ch["start_time"])}s {escape(ch["title"])}'
                idx = vinfo['idx']
                if idx >= len(plitems):
                    return rv
                it = plitems[idx]
                add = u'\n<b>\U0001F6A6' + f'{idx:06d}) <a href="{it.link}">{escape(vinfo["title"])}</a> ({duration2string(round(vinfo["duri"]))})</b>'
            updown_s = 1
            updown_i = 1
            dirs = 2
            while len(rv) + len(add) < 3700:
                ci = idx + updown_i * updown_s
                if ci < 0 or ci >= len(plitems):
                    dirs -= 1
                    updown_s = -updown_s
                    if not dirs:
                        break
                    elif updown_s == 1:
                        updown_i += 1
                else:
                    it = self.plitems[ci]
                    if 'rate' in it.conf:
                        rate = it.conf['rate']
                    a2 = f'\n<b>/I{ci:06d}</b> <a href="{it.link}">{escape(it.title)}</a> ({duration2string(round(it.dur / rate))})'
                    if updown_s == 1:
                        add += a2
                    else:
                        add = a2 + add
                    if dirs > 1:
                        updown_s = -updown_s
                    if updown_s == 1 or dirs == 1:
                        updown_i += 1
            return rv + add


class PlayerListMessage(RemoteListMessage):
    @staticmethod
    def build_remote_info_message(name: str, url: str, sel: bool, navigation: NavigationHandler, user: User) -> RemoteInfoMessage:
        return PlayerInfoMessage(name, url, sel, navigation)
