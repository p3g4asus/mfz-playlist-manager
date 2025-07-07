from abc import abstractmethod
from asyncio import Event, Task
import asyncio
from datetime import datetime, timedelta
from enum import Enum, auto
import logging
import traceback
from typing import Any, Coroutine, List, Optional, Union
from urllib.parse import unquote

from aiohttp import ClientSession
from telegram_menu import BaseMessage, MenuButton, NavigationHandler
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD
import tzlocal
import validators

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
    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: Optional[timedelta] = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, **argw) -> None:
        super().__init__(navigation, label, picture, expiry_period, inlined, home_after, notification, input_field, **argw)
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

    async def long_operation_do(self):
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
    async def wait_undo_job(self):
        if self.sub_status <= 0:
            if self.status == NameDurationStatus.DELETING:
                self.scheduler_job_remove()
                await self.delete_item_do()
                await self.switch_to_idle()
        else:
            self.sub_status -= 1
            await self.edit_or_select()

    @abstractmethod
    async def delete_item_do(self):
        return

    def __init__(self, navigation: NavigationHandler, label: str = "", picture: str = "", expiry_period: timedelta | None = None, inlined: bool = False, home_after: bool = False, notification: bool = True, input_field: str = "", user: User = None, params: object = None, **argw) -> None:
        self.del_action: str = ''
        super().__init__(navigation, label, picture, expiry_period, inlined, home_after, notification, input_field, user, params, **argw)

    def delete_item_pre_pre(self, args):
        self.del_action = args[0]
        self.delete_item_pre()

    def delete_item_pre(self):
        self.status = NameDurationStatus.DELETING
        self.sub_status = 10
        name: str = f"wait_undo_job{id(self)}"
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

    async def set_picture_path(self):
        if self._old_thumb != self.thumb:
            self._old_thumb = self.thumb
            headers = {"range": "bytes=0-10", "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/81.0"}
            thumb = PlaylistItem.convert_img_url(self.thumb, f'{self.proc.params.link}/{self.proc.params.args["sid"]}')
            if thumb and validators.url(thumb):
                async with ClientSession() as session:
                    async with session.get(thumb, headers=headers) as resp:
                        if not (resp.status >= 200 and resp.status < 300):
                            self.picture = ''
                        else:
                            self.picture = thumb
            else:
                self.picture = ''

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
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.add_button(self.yes_btn, self.on_yes, args=self.yes_args)
        self.add_button(self.no_btn, self.on_no, args=self.no_args)
        return self.input_field
