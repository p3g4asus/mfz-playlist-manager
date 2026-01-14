import asyncio
import logging
import re
import traceback
from abc import abstractmethod
from asyncio import Event, Task
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Coroutine, List, Optional, Union

import tzlocal
import validators
from aiohttp import ClientSession
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD
from telegram_menu import BaseMessage, MenuButton, NavigationHandler

from common.const import IMG_NO_THUMB
from common.playlist import PlaylistItem
from common.user import User

_LOGGER = logging.getLogger(__name__)


def duration2string(secs) -> str:
    gg = int(secs / 86400)
    rem = secs % 86400
    hh = int(rem / 3600)
    rem = secs % 3600
    mm = int(rem / 60)
    ss = rem % 60
    if gg > 0:
        return '%dg %02dh %02dm %02ds' % (gg, hh, mm, ss)
    elif hh > 0:
        return '%dh %02dm %02ds' % (hh, mm, ss)
    elif mm > 0:
        return '%dm %02ds' % (mm, ss)
    else:
        return f'{ss}s'


def duration2dict(secs) -> dict:
    gg = int(secs / 86400)
    rem = secs % 86400
    hh = int(rem / 3600)
    rem = secs % 3600
    mm = int(rem / 60)
    ss = int(rem) % 60
    return dict(d=gg, h=hh, m=mm, s=ss)


class NavigationSyncSchedule(object):
    def __init__(self, co: Coroutine):
        self.ev: Event = Event()
        self.rv = None
        self.co: Coroutine = co

    async def wait(self):
        await self.ev.wait()
        return self.rv

    async def perform(self):
        self.rv = await self.co
        self.ev.set()


class MyNavigationHandler(NavigationHandler):
    """Example of navigation handler, extended with a custom "Back" command."""

    def __init__(self, bot, chat, scheduler) -> None:
        super().__init__(bot, chat, scheduler)
        self.sending_queue: list[Coroutine] = []
        self.sending_task: Task = None

    def send_operation_wrapper(self, p: Coroutine):
        self.sending_queue.append(p)
        if not self.sending_task:
            self.sending_task = asyncio.get_event_loop().create_task(self.sending_queue_process())

    async def sending_queue_process(self):
        queue = self.sending_queue
        if queue:
            i = 0
            while True:
                p = queue[i]
                try:
                    if isinstance(p, NavigationSyncSchedule):
                        await p.perform()
                    else:
                        await p
                except Exception:
                    _LOGGER.warning(f'send command failed {traceback.format_exc()}')
                await asyncio.sleep(0.1)
                if i == len(queue) - 1:
                    self.sending_queue.clear()
                    self.sending_task = None
                    break
                else:
                    i += 1

    async def navigation_schedule_wrapper(self, sched, sync):
        if sync:
            sched = NavigationSyncSchedule(sched)
        self.send_operation_wrapper(sched)
        if sync:
            return await sched.wait()

    async def goto_back_wrap(self, level: int = 1) -> int:
        if not self._menu_queue:
            return -1
        elif len(self._menu_queue) == 1:
            # already at 'home' level
            return self._menu_queue[0].message_id
        menu_previous = self._menu_queue.pop()  # delete actual menu
        lev = 0
        while self._menu_queue:
            menu_previous = self._menu_queue.pop()
            lev += 1
            if lev == level:
                break
        return await self.goto_menu(menu_previous, going_home=True)

    async def goto_back(self, sync: bool = False) -> int:
        """Do Go Back logic."""
        return await self.navigation_schedule_wrapper(self.goto_back_wrap(), sync)

    async def goto_home(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None, sync: bool = False):
        return await self.navigation_schedule_wrapper(self.goto_back_wrap(-1), sync)

    async def goto_menu(self, menu_message: BaseMessage, context: Optional[CallbackContext[BT, UD, CD, BD]] = None, add_if_present: bool = True, sync: bool = False, going_home: bool = False):
        coro = super().goto_menu(menu_message, context, add_if_present=add_if_present)
        if going_home:
            return await coro
        else:
            return await self.navigation_schedule_wrapper(coro, sync)


class ProcessorMessage(object):
    def __init__(self, user: User, params):
        self.user = user
        self.params = params
        self.processors = params.processors2
        self.executor = params.telegram_executor

    async def process(self, pl):
        for k, p in self.processors.items():
            _LOGGER.debug(f'Checking {k}')
            if p.interested(pl):
                out = await p.process(None, pl, self.user.rowid, self.executor)
                if out:
                    return out
        return None


class NameDurationStatus(Enum):
    IDLE = auto()
    RETURNING_IDLE = auto()
    DELETING = auto()
    DELETING_CONFIRM = auto()
    RENAMING = auto()
    UPDATING_INIT = auto()
    UPDATING_START = auto()
    UPDATING_STOP = auto()
    UPDATING_RUNNING = auto()
    UPDATING_WAITING = auto()
    SORTING = auto()
    DOWNLOADING = auto()
    DOWNLOADING_WAITING = auto()
    NAMING = auto()
    LISTING = auto()
    MOVING = auto()
    DUMPING = auto()


class StatusTMessage(BaseMessage):
    def set_pict_arr(self, picture: str):
        self.pict_arr = picture.split('|') if picture else []
        self.pict_idx = 2 if len(self.pict_arr) > 2 else (1 if len(self.pict_arr) > 1 else 0)

    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: Optional[timedelta] = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, **argw) -> None:
        self.set_pict_arr(picture)
        super().__init__(navigation, label, '' if not self.pict_arr else self.pict_arr[self.pict_idx], expiry_period, inlined, home_after, notification, input_field, **argw)
        self.status = NameDurationStatus.IDLE
        self.navigation: MyNavigationHandler
        self.sub_status = 0
        self.return_msg = ''
        self.scheduler_job = None
        self.proc = ProcessorMessage(user, params) if user and params else None

    @staticmethod
    def datenow(**argv) -> datetime:
        dt = datetime.now(tz=tzlocal.get_localzone())
        return dt if not argv else dt + timedelta(**argv)

    async def send_wrap(self, context: Optional[CallbackContext] = None):
        try:
            if self.inlined:
                await self.navigation._send_app_message(self, self.label)
            else:
                await self.navigation.goto_menu(self, context, add_if_present=False, sync=False, going_home=True)
        except Exception:
            if self.picture and self.picture != IMG_NO_THUMB:
                while True:
                    if self.pict_idx + 1 < len(self.pict_arr):
                        self.pict_idx += 1
                        new_idx = self.pict_idx
                        new_pict = await self.check_picture_url(self.pict_arr[self.pict_idx])
                        if not new_pict:
                            continue
                    else:
                        new_pict = IMG_NO_THUMB
                        new_idx = -1
                    break
                _LOGGER.warning(f'send error: trying fallback thumb[{new_idx}] {new_pict} (old was {self.picture})')
                self.picture = new_pict
                await self.send_wrap(context)
            else:
                _LOGGER.warning(f'send error {traceback.format_exc()}')

    async def send(self, context: Optional[CallbackContext] = None, sync: bool = False):
        await self.navigation.navigation_schedule_wrapper(self.send_wrap(context), sync)

    async def edit_or_select_wrap(self, context: Optional[CallbackContext] = None):
        try:
            if self.inlined:
                await self.edit_message()
            else:
                await self.navigation.goto_menu(self, context, add_if_present=False, sync=False, going_home=True)
        except Exception:
            _LOGGER.warning(f'edit error {traceback.format_exc()}')

    async def edit_or_select(self, context: Optional[CallbackContext] = None, sync: bool = False):
        await self.navigation.navigation_schedule_wrapper(self.edit_or_select_wrap(context), sync)

    async def switch_to_status(self, args, context=None):
        self.status = args[0]
        await self.edit_or_select(context)

    async def switch_to_idle_end(self):
        await self.edit_or_select()

    def slash_message_processed(self, text: str) -> bool:
        return False

    def scheduler_job_remove(self, name: str = None):
        if self.scheduler_job and not name:
            try:
                _LOGGER.debug(f'Deleting {self.scheduler_job.name} for {id(self)}')
                self.scheduler_job.remove()
            except Exception:
                pass
            self.scheduler_job = None
        elif name:
            try:
                _LOGGER.debug(f'Deleting {name} for {id(self)}')
                self.navigation.scheduler.remove_job(name, 'default')
            except Exception:
                pass

    async def switch_to_idle(self, args=None):
        if self.return_msg and self.sub_status != -1000:
            self.status = NameDurationStatus.RETURNING_IDLE
            self.sub_status = -1000
        else:
            self.status = NameDurationStatus.IDLE if not isinstance(args, (tuple, list)) or not args else args[0]
            self.sub_status = 0
            self.return_msg = ''
        self.scheduler_job_remove()
        if self.return_msg:
            self.navigation.scheduler.add_job(
                self.switch_to_idle,
                "date",
                (args, ),
                id=f"switch_to_idle{id(self)}",
                replace_existing=True,
                run_date=self.datenow(seconds=8 if self.inlined else 0.5)
            )
        await self.switch_to_idle_end()

    async def long_operation_do(self, edit_only: bool = False):
        if not edit_only:
            sign = self.sub_status & 512
            self.sub_status &= 0xFF
            if self.sub_status == 10:
                sign = 512
            elif self.sub_status == 0:
                sign = 0
            self.sub_status = (self.sub_status + 1 * (-1 if sign else 1)) | sign
        await self.edit_or_select()

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        return None


class DeletingTMessage(StatusTMessage):
    MAX_DELETING_SIMULTANEOUS = 4
    UNDO_TASK_PATTERN = re.compile(r'wait_undo_job(\d+)')

    async def wait_undo_job(self):
        if self.sub_status <= 0:
            if self.status == NameDurationStatus.DELETING:
                self.scheduler_job_remove()
                await self.delete_item_do()
                await self.switch_to_idle()
        elif self.sub_status < 10 or self.is_task_active():
            self.sub_status -= 1
            await self.edit_or_select()

    @abstractmethod
    async def delete_item_do(self):
        return

    def is_task_active(self):
        jobs = self.navigation.scheduler.get_jobs()
        ll = [999999] * self.MAX_DELETING_SIMULTANEOUS
        for jb in jobs:
            if mo := self.UNDO_TASK_PATTERN.search(jb.name):
                jbi = int(mo.group(1))
                for k, jbioth in enumerate(ll):
                    if jbioth >= jbi:
                        ll = ll[0:k] + [jbi] + ll[k: -1]
                        break
        return self.jbi in ll

    def get_new_undo_task_name(self):
        jobs = self.navigation.scheduler.get_jobs()
        max_jb = 0
        for jb in jobs:
            if mo := self.UNDO_TASK_PATTERN.search(jb.name):
                jbi = int(mo.group(1))
                if jbi > max_jb:
                    max_jb = jbi
        self.jbi = max_jb + 1
        return f'wait_undo_job{self.jbi}'

    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: timedelta | None = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, **argw) -> None:
        self.del_action: str = ''
        self.jbi: int = -1
        super().__init__(navigation, label, picture, expiry_period, inlined, home_after, notification, input_field, user, params, **argw)

    def delete_item_pre_pre(self, args):
        self.del_action = args[0]
        self.delete_item_pre()

    def delete_item_pre(self):
        self.status = NameDurationStatus.DELETING
        self.sub_status = 10
        name: str = self.get_new_undo_task_name()
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.wait_undo_job,
            "interval",
            name=name,
            id=name,
            seconds=1,
            replace_existing=True,
        )

    async def update(self, _: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        if self.status == NameDurationStatus.DELETING:
            self.input_field = u'\U0001F570'
            self.add_button(f':cross_mark: Undo in {self.sub_status} sec', self.switch_to_idle)
        return ''


class NameDurationTMessage(DeletingTMessage):

    async def send_wrap(self, context: Optional[CallbackContext] = None):
        if self.inlined:
            await self.prepare_for_sending()
        await super().send_wrap(context)

    async def edit_or_select(self, context: Optional[CallbackContext] = None):
        if self.inlined and self._old_thumb != self.thumb:
            await self.send(context)
        else:
            return await super().edit_or_select(context)

    async def edit_or_select_if_exists(self, delay: float = 0, context: Optional[CallbackContext] = None):
        if self.time_alive and self.refresh_from_cache():
            if delay > 0.0:
                name = f"eos{self.label}"
                self.navigation.scheduler.add_job(
                    self.edit_or_select,
                    "date",
                    id=name,
                    name=name,
                    replace_existing=True,
                    run_date=self.datenow(seconds=delay)
                )
            else:
                await self.edit_or_select()

    async def check_picture_url(self, url: str) -> str:
        headers = {"range": "bytes=0-10", "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/81.0"}
        thumb = PlaylistItem.convert_img_url(url, f'{self.proc.params.link}/{self.proc.params.args["sid"]}')
        if thumb and validators.url(thumb):
            async with ClientSession() as session:
                async with session.get(thumb, headers=headers) as resp:
                    if not (resp.status >= 200 and resp.status < 300):
                        return ''
                    else:
                        return thumb
        else:
            return ''

    async def set_picture_path(self):
        if self._old_thumb != self.thumb:
            self._old_thumb = self.thumb
            self.set_pict_arr(self.thumb)
            self.picture = ''
            for i in range(len(self.pict_arr)):
                real_idx = (i + self.pict_idx) % len(self.pict_arr)
                tt = self.pict_arr[real_idx]
                thumb = await self.check_picture_url(tt)
                if thumb:
                    self.picture = thumb
                    self.pict_idx = real_idx
                    break

    @abstractmethod
    def refresh_from_cache(self):
        return

    async def prepare_for_sending(self):
        if self.refresh_from_cache():
            await self.set_picture_path()
            return True
        else:
            return False

    def __init__(self, navigation: NavigationHandler, myid: int = None, user: User = None, params: object = None, **argw) -> None:
        self.index = None
        self.id = myid
        self.name = None
        self.secs = None
        self.obj = None
        self.thumb = None
        self._old_thumb = None
        self.deleted = None
        super().__init__(
            navigation=navigation,
            label=f'{self.__class__.__name__}_{myid}_{int(datetime.now().timestamp() * 1000)}',
            picture=self.thumb,
            inlined=True,
            home_after=False,
            expiry_period=timedelta(hours=10),
            user=user,
            params=params,
            **argw
        )
        self.refresh_from_cache()


class YesNoTMessage(BaseMessage):
    def __init__(self, navigation: NavigationHandler, labelYes: str, labelNo: str, inputField: str = 'Are you sure?', argsYes=None, argsNo=None) -> None:
        super().__init__(
            navigation,
            self.__class__.__name__,
            expiry_period=timedelta(minutes=30),
            input_field=inputField)
        self.yes_btn = labelYes
        self.no_btn = labelNo
        self.yes_args = argsYes
        self.no_args = argsNo

    async def on_no(self, _: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.navigation.goto_back()

    @abstractmethod
    async def on_yes(self, _: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        pass

    def update(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> str:
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.add_button(self.yes_btn, self.on_yes, args=self.yes_args)
        self.add_button(self.no_btn, self.on_no, args=self.no_args)
        return self.input_field


class SetRateTMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: Optional[timedelta] = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, **argw) -> None:
        super().__init__(navigation, label, picture, expiry_period, inlined, home_after, notification, input_field, user, params, **argw)
        self.modding_rate: list[str] = [5] * 5
        self.init_rate: Optional[float] = None

    def modding_rate_del(self) -> str:
        if self.modding_rate:
            self.modding_rate.pop()
        return self.modding_rate_conv()

    def modding_rate_conv(self) -> str:
        ss = ''
        ln = len(self.modding_rate)
        for i, s in reversed(list(enumerate(self.modding_rate))):
            if i == 0 and ln > 2:
                ss = s + '.' + ss
            else:
                ss = s + ss
        if ln == 1:
            ss = '_._' + ss
        elif ln == 0:
            ss = '_.__'
        elif ln == 2:
            ss = '_.' + ss
        return ss

    async def modding_rate_mod(self, args):
        if not args[0]:
            self.modding_rate_del()
        elif args[0] == -1:
            self.modding_rate = [5] * 5
            await self.switch_to_idle()
            return
        else:
            self.modding_rate_char(args[0])
        await self.edit_or_select()

    def modding_rate_char(self, char) -> str:
        ln = len(self.modding_rate)
        if ln < 3:
            self.modding_rate.append(str(char))
        return self.modding_rate_conv()

    def set_init_rate(self, init_rate: Optional[float] = None):
        if init_rate is None or (init_rate < 10.0 and init_rate > 0.0):
            self.init_rate = init_rate

    def modding_rate_get(self) -> str:
        if len(self.modding_rate) > 3:
            if self.init_rate is not None:
                self.modding_rate = list(f'{int(self.init_rate * 100)}')
            else:
                self.modding_rate = []
        return self.modding_rate_conv()

    def modding_rate_float(self) -> Optional[float]:
        if len(self.modding_rate) < 3:
            return None
        else:
            return int(''.join(self.modding_rate)) / 100.0

    @abstractmethod
    async def modding_rate_send(self):
        pass

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        self.add_button(u'\U0001F3C3 ' + self.modding_rate_get(), self.modding_rate_send)
        for c in '1234567890':
            if len(self.modding_rate) < 3:
                self.add_button(c, self.modding_rate_mod, args=(c, ), new_row=c == '1')
            else:
                self.add_button(' ', new_row=c == '1')
        self.add_button('<', self.modding_rate_mod, args=(None, ))
        self.add_button(':cross_mark: Abort', self.modding_rate_mod, args=(-1, ))
        return await StatusTMessage.update(context)


class ChangeTimeTMessage(StatusTMessage):
    MT_SEPARATORS = ['d ', 'h ', 'm ', 's']
    MT_MUL = [86400, 3600, 60, 1]

    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: Optional[timedelta] = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, **argw) -> None:
        super().__init__(navigation, label, picture, expiry_period, inlined, home_after, notification, input_field, user, params, **argw)
        self.modding_time: list[str] = []
        self.init_secs: Optional[int] = None

    def modding_time_get(self) -> str:
        if not self.modding_time:
            if self.init_secs is not None:
                dct = duration2dict(self.init_secs)
            else:
                dct = dict(d=0, h=0, m=0, s=None)
            out = []
            if dct['d'] == 0:
                ss = '_'
                filled = False
            else:
                ss = str(dct['d'])
                filled = True
            out.append(ss)
            if dct['h'] == 0 and not filled:
                ss = '__'
            else:
                ss = str(dct['h']).rjust(2, '_' if not filled else '0')
                filled = True
            out.append(ss)
            if dct['m'] == 0 and not filled:
                ss = '__'
            else:
                ss = str(dct['m']).rjust(2, '_' if not filled else '0')
                filled = True
            out.append(ss)
            if dct['s'] is None:
                ss = '__'
            else:
                ss = str(dct['s']).rjust(2, '_' if not filled else '0')
            out.append(ss)
            self.modding_time = out
        return self.modding_time_conv()

    def modding_time_conv(self) -> str:
        ss = ''
        for i, s in reversed(list(enumerate(self.modding_time))):
            ss = s + self.MT_SEPARATORS[i] + ss
            if s.count('_') > 0:
                break
        return ss

    def modding_time_del(self) -> str:
        idxlast = -1
        for i, s in enumerate(self.modding_time):
            if mo := re.search(r'\d+', s):
                idxlast = mo.end()
                break
        if idxlast < 0:
            return self.modding_time_conv()
        else:
            mt = self.modding_time
            if i == 0:
                if len(mt[i]) > 1:
                    mt[i] = mt[i][0:-1]
                else:
                    mt[i] = '_'
            else:
                mt[i] = '_' + mt[i][0:idxlast - 1]
            return self.modding_time_conv()

    def modding_time_char(self, char) -> str:
        i = -1
        for i, s in reversed(list(enumerate(self.modding_time))):
            idxlast = s.rfind('_')
            if idxlast >= 0:
                break
        mt = self.modding_time
        if idxlast < 0:
            mt[i] = mt[i] + str(char)
        else:
            mt[i] = mt[i][0:idxlast] + mt[i][idxlast + 1:] + str(char)
        return self.modding_time_conv()

    def modding_time_chars(self) -> str:
        i = -1
        for i, s in reversed(list(enumerate(self.modding_time))):
            idxlast = s.rfind('_')
            if idxlast >= 0:
                break
        if idxlast != 0 or not i:
            return '0123456789'
        else:
            mm = int(self.modding_time[i][1])
            if i == 1:
                if mm >= 3:
                    return ''
                elif mm <= 1:
                    return '0123456789'
                else:  # if mm == 2:
                    return '0123'
            else:
                return '' if mm >= 6 else '0123456789'

    def modding_time_secs(self):
        if not self.modding_time or self.modding_time[3] == '__':
            return None
        else:
            secs = None
            for i, m in enumerate(self.modding_time):
                if mo := re.search(r'(\d+)', m):
                    if secs is None:
                        secs = 0
                    secs += int(mo.group(1)) * self.MT_MUL[i]
        return secs

    async def modding_time_mod(self, args):
        if not args[0]:
            self.modding_time_del()
        elif args[0] == -1:
            self.modding_time = []
            await self.switch_to_idle()
            return
        else:
            self.modding_time_char(args[0])
        await self.edit_or_select()

    @abstractmethod
    async def modding_time_send(self):
        pass

    def set_init_secs(self, init_secs: Optional[int] = None):
        self.init_secs = init_secs

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        self.add_button(u'\U000023F2 ' + self.modding_time_get(), self.modding_time_send)
        chars = self.modding_time_chars()
        for c in '1234567890':
            if c in chars:
                self.add_button(c, self.modding_time_mod, args=(c, ), new_row=c == '1')
            else:
                self.add_button(' ', new_row=c == '1')
        self.add_button('<', self.modding_time_mod, args=(None, ))
        self.add_button(':cross_mark: Abort', self.modding_time_mod, args=(-1, ))
        return await StatusTMessage.update(context)
