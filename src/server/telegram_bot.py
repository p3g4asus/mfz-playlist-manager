import asyncio
import logging
import re
import traceback
from abc import abstractmethod
from datetime import datetime, timedelta
from enum import Enum, auto
from html import escape
from os import stat
from os.path import exists, isfile, split
from typing import Any, Coroutine, List, Optional, Union
from urllib.parse import urlencode, urlparse

import validators
from aiohttp import ClientSession
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD
from telegram_menu import (BaseMessage, ButtonType, NavigationHandler,
                           TelegramMenuSession)
from telegram_menu.models import MenuButton, emoji_replace

from common.const import (CMD_DEL, CMD_DOWNLOAD, CMD_DUMP, CMD_IORDER,
                          CMD_REFRESH, CMD_REN, CMD_SEEN, CMD_SORT)
from common.playlist import (PlaylistMessage)

_LOGGER = logging.getLogger(__name__)


def duration2string(secs):
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


class MyNavigationHandler(NavigationHandler):
    """Example of navigation handler, extended with a custom "Back" command."""

    async def goto_back(self) -> int:
        """Do Go Back logic."""
        return await self.select_menu_button("Back")


class ProcessorMessage(object):
    def __init__(self, userid, username, params):
        self.userid = userid
        self.username = username
        self.params = params
        self.processors = params.processors2
        self.executor = params.telegram_executor

    async def process(self, pl):
        for k, p in self.processors.items():
            _LOGGER.debug(f'Checking {k}')
            if p.interested(pl):
                out = await p.process(None, pl, self.userid, self.executor)
                if out:
                    return out
        return None


class NameDurationStatus(Enum):
    IDLE = auto()
    RETURNING_IDLE = auto()
    DELETING = auto()
    RENAMING = auto()
    UPDATING_INIT = auto()
    UPDATING_START = auto()
    UPDATING_STOP = auto()
    UPDATING_RUNNING = auto()
    UPDATING_WAITING = auto()
    SORTING = auto()
    DOWNLOADING = auto()
    DOWNLOADING_WAITING = auto()


class NameDurationTMessage(BaseMessage):
    def reset(self, index, myid, name, secs, thumb, deleted, obj):
        self.index = index
        self.id = myid
        self.name = name
        self.secs = secs
        self.thumb = f'{self.proc.params.link}/{self.proc.params.args["sid"]}/img{thumb}' if thumb and thumb[0] == '?' else thumb
        self.obj = obj
        self.deleted = deleted

    def __init__(self, navigation, index, myid, name, secs, thumb, deleted, obj, userid, username, params) -> None:
        self.proc = ProcessorMessage(userid, username, params)
        self.reset(index, myid, name, secs, thumb, deleted, obj)
        BaseMessage.__init__(
            self,
            navigation,
            f'{self.__class__.__name__}_{myid}_{int(datetime.now().timestamp() * 1000)}',
            picture=self.thumb,
            inlined=True,
            home_after=False,
            expiry_period=timedelta(hours=10)
        )
        self.status = NameDurationStatus.IDLE
        self.sub_status = 0
        self.return_msg = ''
        self.scheduler_job = None

    async def switch_to_status(self, args, context):
        self.status = args[0]
        try:
            await self.edit_message()
        except Exception:
            _LOGGER.warning(f'edit error {traceback.format_exc()}')

    async def switch_to_idle(self):
        if self.return_msg and self.sub_status != -1000:
            self.status = NameDurationStatus.RETURNING_IDLE
            self.sub_status = -1000
        else:
            self.status = NameDurationStatus.IDLE
            self.sub_status = 0
            self.return_msg = ''
        if self.scheduler_job:
            try:
                self.scheduler_job.remove()
            except Exception:
                pass
            self.scheduler_job = None
        if self.return_msg:
            self.scheduler_job = self.navigation.scheduler.add_job(
                self.switch_to_idle,
                "interval",
                id=f"switch_to_idle{id(self)}",
                seconds=8,
                replace_existing=True,
            )
        try:
            await self.edit_message()
        except Exception:
            _LOGGER.warning(f'edit error {traceback.format_exc()}')

    async def long_operation_do(self):
        sign = self.sub_status & 512
        self.sub_status &= 0xFF
        if self.sub_status == 10:
            sign = 512
        elif self.sub_status == 0:
            sign = 0
        self.sub_status = (self.sub_status + 1 * (-1 if sign else 1)) | sign
        try:
            await self.edit_message()
        except Exception:
            _LOGGER.warning(f'edit error {traceback.format_exc()}')

    async def wait_undo_job(self):
        if self.sub_status <= 0:
            if self.status == NameDurationStatus.DELETING:
                await self.delete_item_do()
                await self.switch_to_idle()
        else:
            self.sub_status -= 1
            try:
                await self.edit_message()
            except Exception:
                _LOGGER.warning(f'edit error {traceback.format_exc()}')

    @abstractmethod
    async def delete_item_do(self):
        return

    def delete_item_pre(self):
        self.status = NameDurationStatus.DELETING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.wait_undo_job,
            "interval",
            id=f"wait_undo_job{id(self)}",
            seconds=1,
            replace_existing=True,
        )


class PlaylistItemTMessage(NameDurationTMessage):
    def __init__(self, navigation, index, playlist_name, item, userid, username, params) -> None:
        NameDurationTMessage.__init__(self, navigation, index, item.rowid, item.title, item.dur, item.img, item.seen, item, userid, username, params)
        self.playlist_name = playlist_name

    async def text_input(self, text: str, context: CallbackContext[BT, UD, CD, BD] | None = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.SORTING:
            text = text.strip()
            if re.match(r'^[0-9]+$', text):
                await self.set_iorder_do(int(text))
                await self.switch_to_idle()

    async def stop_download(self, args, _):
        myid = args[0]
        pl = PlaylistMessage(CMD_DOWNLOAD, playlistitem=myid)
        pl = await self.proc.process(pl)

    def download_format(self, args, context):
        asyncio.get_event_loop().create_task(self.download_format_1(args, context))

    async def download_format_1(self, args, context):
        self.status = NameDurationStatus.DOWNLOADING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id=f"long_operation_do{id(self)}",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = PlaylistMessage(CMD_DOWNLOAD,
                             playlistitem=self.id,
                             fmt=args[0],
                             host=f'{self.proc.params.link}/{self.proc.params.args["sid"]}',
                             conv=args[1])
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.obj.dl = pl.playlistitem.dl
            self.return_msg = f'Download OK {split(self.obj.dl)[1]} :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} downloading {self.name} :thumbs_down:'
        await self.switch_to_idle()

    @staticmethod
    def sizeof_fmt(num, suffix="B"):
        for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Yi{suffix}"

    @staticmethod
    def dictget(dcn, key, default=None):
        return dcn[key] if key in dcn and dcn[key] else default

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        if not self.deleted:
            if self.status == NameDurationStatus.IDLE:
                self.add_button(u'\U0001F5D1', self.delete_item_pre)
                self.add_button(u'\U00002211', self.switch_to_status, args=(NameDurationStatus.SORTING, ))
                self.add_button(u'\U0001F517', self.switch_to_status, args=(NameDurationStatus.DOWNLOADING_WAITING, ))
            elif self.status == NameDurationStatus.DOWNLOADING_WAITING:
                self.add_button('bestaudio', self.download_format, args=('bestaudio/best', 0))
                self.add_button('best', self.download_format, args=('best', 0))
                self.add_button('worstaudio', self.download_format, args=('worstaudio/worst', 0))
                self.add_button('worst', self.download_format, args=('worst', 0))
                if 'twitch.tv' in self.obj.link:
                    self.add_button('bestaudio os', self.download_format, args=('bestaudio/best', 4))
                    self.add_button('best os', self.download_format, args=('best', 4))
                    self.add_button('worstaudio os', self.download_format, args=('worstaudio/worst', 4))
                    self.add_button('worst os', self.download_format, args=('worst', 4))
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
            elif self.status == NameDurationStatus.DOWNLOADING:
                status = self.proc.processors['common'].status
                self.add_button(f':cross_mark: Abort {self.id}', self.stop_download, args=(self.id, ))
                if 'dlid' in status and status['dlid'] == self.id:
                    self.add_button(':cross_mark::cross_mark: Abort All', self.stop_download, args=(None, ))
                    upd = f'{escape(self.name)} downloading {"." * (self.sub_status & 0xFF)}'
                    if 'dl' in status and 'raw' in status['dl']:
                        dl = status['dl']['raw']
                        upd2 = ''
                        fi = self.dictget(dl, 'fragment_index', self.dictget(dl, 'downloaded_bytes'))
                        fc = self.dictget(dl, 'fragment_count', self.dictget(dl, 'total_bytes', self.dictget(dl, 'total_bytes_estimate')))
                        if isinstance(fi, (int, float)) and isinstance(fc, (int, float)):
                            no = int(round(30.0 * fi / fc))
                            upd2 += '[' + (no * 'o') + ((30 - no) * ' ') + '] '
                        fc = dl.get('speed')
                        if isinstance(fc, (int, float)):
                            upd2 += f'{self.sizeof_fmt(fc, "B/s")} '
                        fc = dl.get('downloaded_bytes')
                        if isinstance(fc, (int, float)):
                            upd2 += f'{self.sizeof_fmt(fc)}'
                        if upd2:
                            upd += '\n<code>' + upd2 + '</code>'
                else:
                    upd = f'{escape(self.name)} waiting in queue {"." * (self.sub_status & 0xFF)}'
                return upd
            elif self.status == NameDurationStatus.SORTING:
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
                return f'Enter \U00002211 for <b>{self.name}</b>'
        elif self.status == NameDurationStatus.IDLE:
            self.add_button(u'\U0000267B', self.delete_item_pre)
        if self.status == NameDurationStatus.DELETING:
            self.add_button(f':cross_mark: Undo in {self.sub_status} sec', self.switch_to_idle)
        upd = f'<a href="{self.obj.link}">{self.index})<b>{escape(self.name)}</b> - <i>Id {self.id}</i></a> :memo: {self.playlist_name}\n\U000023F1 {duration2string(self.secs)}\n\U000023F3: {self.obj.datepub}\n'
        if self.obj.conf and 'author' in self.obj.conf and self.obj.conf['author']:
            upd += f'\U0001F64B: {self.obj.conf["author"]}\n'
        upd += f'\U00002211: {self.obj.iorder}'
        mainlnk = f'{self.proc.params.link}/{self.proc.params.args["sid"]}'
        if 'twitch.tv' in self.obj.link:
            lnk = f'{mainlnk}/twi?'
            par = urlencode(dict(link=self.obj.link))
            upd += f'\n<a href="{lnk}{par}">\U0001F7E3 TWI</a>'
        if self.obj.dl and exists(self.obj.dl) and isfile(self.obj.dl):
            sta = stat(self.obj.dl)
            upd += f'\n<a href="{mainlnk}/dl/{self.id}">DL {self.sizeof_fmt(sta.st_size) if sta else ""}</a> <a href="{mainlnk}/dl/{self.id}?stream=1">\U0001F3BC</a>'
        # upd += f'<tg-spoiler><pre>{json.dumps(self.obj.conf, indent=4)}</pre></tg-spoiler>'
        if self.return_msg:
            upd += f'\n<b>{self.return_msg}</b>'
        elif self.deleted:
            upd = f'<s>{upd}</s>'
        return upd

    async def delete_item_do(self):
        pl = PlaylistMessage(CMD_SEEN, playlistitem=self.id, seen=not self.deleted)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.deleted = not self.deleted
            self.obj.seen = not self.obj.seen
            self.return_msg = ('Delete' if self.deleted else 'Restore') + ' OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} {"deleting" if not self.deleted else "restoring"} {self.name} :thumbs_down:'

    async def set_iorder_do(self, iorder):
        pl = PlaylistMessage(CMD_IORDER, playlistitem=self.id, iorder=iorder)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.obj = pl.playlistitem
            self.return_msg = 'IOrder OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} IOrdering {self.name} :thumbs_down:'


class PlaylistTMessage(NameDurationTMessage):

    def reset(self, index, myid, name, secs, thumb, deleted, obj):
        img = None
        self.unseen = 0
        for pli in obj.items:
            if not pli.seen:
                self.unseen += 1
                if not img:
                    img = pli.img
        duration = obj.get_duration()
        super().reset(index, myid, name, duration, img, deleted, obj)

    def __init__(self, navigation, index, item, userid, username, params) -> None:
        self.upd_sta = None
        self.upd_sto = None
        NameDurationTMessage.__init__(self, navigation, index, item.rowid, item.name, 0, '', False, item, userid, username, params)

    async def delete_item_do(self):
        pl = PlaylistMessage(CMD_DEL, playlist=self.id)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.deleted = True
            self.return_msg = 'Delete OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} deleting {self.name} :thumbs_down:'

    async def rename_playlist_2(self, newname):
        pl = PlaylistMessage(CMD_REN, playlist=self.id, to=newname)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.name = newname
            self.return_msg = 'Rename OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} renaming {self.name} :thumbs_down:'

    def update_playlist(self):
        asyncio.get_event_loop().create_task(self.update_playlist_1())

    async def update_playlist_1(self):
        self.status = NameDurationStatus.UPDATING_RUNNING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="long_operation_do",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = PlaylistMessage(CMD_REFRESH, playlist=self.obj, datefrom=int(self.upd_sta.timestamp() * 1000), dateto=int(self.upd_sto.timestamp() * 1000))
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            item = pl.playlist
            self.reset(self.index, item.rowid, item.name, 0, '', False, item)
            self.return_msg = 'Refresh OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} refreshing {self.name} :thumbs_down:'
        await self.switch_to_idle()

    def sort_playlist(self):
        asyncio.get_event_loop().create_task(self.sort_playlist_1())

    async def sort_playlist_1(self):
        self.status = NameDurationStatus.SORTING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="long_operation_do",
            seconds=3,
            replace_existing=True,
            next_run_time=datetime.utcnow()
        )
        pl = PlaylistMessage(CMD_SORT, playlist=self.id)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            item = pl.playlist
            self.reset(self.index, item.rowid, item.name, 0, '', False, item)
            self.return_msg = 'Sort OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} sorting {self.name} :thumbs_down:'
        await self.switch_to_idle()

    async def text_input(self, text: str, context: CallbackContext[BT, UD, CD, BD] | None = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.RENAMING:
            text = text.strip()
            if re.match(r'^[0-9a-zA-Z_\-]+$', text):
                await self.rename_playlist_2(text)
                await self.switch_to_idle()
        elif self.status in (NameDurationStatus.UPDATING_START, NameDurationStatus.UPDATING_STOP):
            text = text.strip()
            try:
                if self.status == NameDurationStatus.UPDATING_START:
                    self.upd_sta = datetime.strptime(f'{text} 00:00:00.1', '%y%m%d %H:%M:%S.%f')
                elif self.status == NameDurationStatus.UPDATING_STOP:
                    self.upd_sto = datetime.strptime(f'{text} 23:59:59.9', '%y%m%d %H:%M:%S.%f')
                self.status = NameDurationStatus.UPDATING_WAITING
                await self.edit_message()
            except Exception:
                pass

    async def list_items(self, args, context):
        p = PlaylistItemsPagesTMessage(self.navigation, deleted=args[0], userid=self.proc.userid, username=self.proc.username, params=self.proc.params, playlist_obj=self)
        await self.navigation.goto_menu(p, context)

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        if not self.deleted:
            if self.status == NameDurationStatus.IDLE:
                self.add_button(u'\U0001F5D1', self.delete_item_pre)
                self.add_button(u'\U000000AB\U000000BB', self.switch_to_status, args=(NameDurationStatus.RENAMING, ))
                self.add_button(u'\U0001F501', self.switch_to_status, args=(NameDurationStatus.UPDATING_INIT, ))
                self.add_button(u'\U00002211', self.sort_playlist)
                self.add_button(':memo:', self.list_items, args=(False, ))
                self.add_button(':eye:', self.list_items, args=(True, ))
                self.add_button(':play_button:', btype=ButtonType.LINK, web_app_url=f'{self.proc.params.link}/{self.proc.params.args["sid"]}-s/play/workout.htm?{urlencode(dict(name=self.name))}')
            elif self.status == NameDurationStatus.DELETING:
                self.add_button(f':cross_mark: Undo in {self.sub_status} sec', self.switch_to_idle)
            elif self.status == NameDurationStatus.RENAMING:
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
                return f'Enter new name for <b>{self.name}</b>'
            elif self.status == NameDurationStatus.SORTING:
                return f'{self.name} sorting {"." * (self.sub_status & 0xFF)}'
            elif self.status in (NameDurationStatus.UPDATING_INIT, NameDurationStatus.UPDATING_START, NameDurationStatus.UPDATING_STOP, NameDurationStatus.UPDATING_WAITING):
                if self.status == NameDurationStatus.UPDATING_INIT:
                    self.upd_sta = datetime.fromtimestamp(int(self.obj.dateupdate / 1000))
                    self.upd_sto = datetime.now()
                    self.status = NameDurationStatus.UPDATING_WAITING
                self.add_button(self.upd_sta.strftime('%Y-%m-%d'), self.switch_to_status, args=(NameDurationStatus.UPDATING_START, ))
                self.add_button(self.upd_sto.strftime('%Y-%m-%d'), self.switch_to_status, args=(NameDurationStatus.UPDATING_STOP, ))
                self.add_button(':cross_mark: Abort', self.switch_to_idle, new_row=True)
                self.add_button(u'\U0001F501', self.update_playlist)
                if self.status == NameDurationStatus.UPDATING_START:
                    return '<u>Start date</u> (YYMMDD)'
                elif self.status == NameDurationStatus.UPDATING_STOP:
                    return '<u>Stop date</u> (YYMMDD)'
                elif self.status == NameDurationStatus.UPDATING_WAITING:
                    return f'Review params for {self.name} and update or abort'
            elif self.status == NameDurationStatus.UPDATING_RUNNING:
                return f'{self.name} updating {"." * (self.sub_status & 0xFF)}'
        datepubo = datetime.fromtimestamp(int(self.obj.dateupdate / 1000))
        upd = f'<b>{self.name}</b> - <i>Id {self.id}</i>'
        if self.obj.type == 'youtube':
            upd += '\U0001F534'
        elif self.obj.type == 'rai':
            upd += '\U0001F535'
        elif self.obj.type == 'mediaset':
            upd += '\U00002B24'
        upd += f'\nLength: {self.unseen} \U000023F1 {duration2string(self.obj.get_duration())}\n'
        upd += f':eye: {len(self.obj.items)} \U000023F1 {duration2string(self.obj.get_duration(True))}\n'
        upd += f'Update \U000023F3: {datepubo.strftime("%Y-%m-%d %H:%M:%S")} ' + ("\U00002705" if self.obj.autoupdate else "") + '\n'
        lnk = f'{self.proc.params.link}/{self.proc.params.args["sid"]}'
        par = urlencode(dict(username=self.proc.username, name=self.name, host=lnk))
        upd += f'<a href="{lnk}/m3u?{par}&fmt=m3u">M3U8</a>, <a href="{lnk}/m3u?{par}&fmt=ely">ELY</a>, <a href="{lnk}/m3u?{par}&fmt=json">JSON</a>\n'
        upd += f'<a href="{lnk}/m3u?{par}&fmt=m3u&conv=4">M3U8c4</a>, <a href="{lnk}/m3u?{par}&fmt=ely&conv=4">ELYc4</a>, <a href="{lnk}/m3u?{par}&fmt=json&conv=4">JSONc4</a>\n'
        upd += f'<a href="{lnk}/m3u?{par}&fmt=m3u&conv=2">M3U8c2</a>, <a href="{lnk}/m3u?{par}&fmt=ely&conv=2">ELYc2</a>, <a href="{lnk}/m3u?{par}&fmt=json&conv=2">JSONc2</a>'
        # upd += f'<tg-spoiler><pre>{json.dumps(self.obj.conf, indent=4)}</pre></tg-spoiler>'
        if self.return_msg:
            upd += f'\n<b>{self.return_msg}</b>'
        elif self.deleted:
            upd = f'<s>{upd}</s>'
        return upd


class GroupOfNameDurationItems(object):

    def __init__(self):
        self.items = []
        self.start_item = -1
        self.stop_item = -1

    def is_valid(self):
        return self.start_item >= 0 and self.stop_item >= 0

    def add_item(self, item):
        if not self.items:
            self.start_item = item.index
        self.items.append(item)
        self.stop_item = item.index


class MultipleGroupsOfItems(object):

    def __init__(self):
        self.start_item = -1
        self.stop_item = -1
        self.next_page = None
        self.back_page = None
        self.groups = []

    def is_valid(self):
        return self.start_item >= 0 and self.stop_item >= 0

    def set_start_stop(self, sta, sto):
        self.start_item = sta
        self.stop_item = sto

    def get_next_page(self):
        return self.next_page

    def add_group(self, grp):
        self.groups.append(grp)

    def set_back_page(self, val):
        self.back_page = val


class PageGenerator(object):
    def __init__(self, userid, username, params) -> None:
        self.proc = ProcessorMessage(userid, username, params)

    @abstractmethod
    def item_convert(self, item, index, navigation):
        return

    @abstractmethod
    async def get_items_list(self, deleted=False, **kwargs):
        return


class PlaylistsPagesGenerator(PageGenerator):

    def item_convert(self, item, index, navigation):
        return PlaylistTMessage(navigation, index, item, self.proc.userid, self.proc.username, self.proc.params)

    def get_playlist_message(self, playlist=None):
        return PlaylistMessage(CMD_DUMP, useri=self.proc.userid, load_all=1, playlist=playlist)

    async def get_items_list(self, _=False, playlist=None):
        plout = await self.proc.process(self.get_playlist_message(playlist))
        return plout.playlists


class PlaylistItemsPagesGenerator(PageGenerator):
    def __init__(self, userid, username, params, playlist_obj):
        PageGenerator.__init__(
            self,
            userid,
            username,
            params
        )
        self.playlist_obj = playlist_obj

    def item_convert(self, item, index, navigation):
        return PlaylistItemTMessage(navigation, index, self.playlist_obj.name, item, self.proc.userid, self.proc.username, self.proc.params)

    async def get_items_list(self, deleted=False):
        if deleted:
            return self.playlist_obj.obj.items
        else:
            items = []
            for i in self.playlist_obj.obj.items:
                if not i.seen:
                    items.append(i)
            return items


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
        self.add_button(self.yes_btn, self.on_yes, args=self.yes_args)
        self.add_button(self.no_btn, self.on_no, args=self.no_args)
        return self.input_field


class SignOutTMessage(YesNoTMessage):
    def __init__(self, navigation: NavigationHandler) -> None:
        super().__init__(navigation, '\U00002705\U0001F6AA', ':cross_mark:\U0001F6AA')

    async def on_yes(self, _: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.navigation._menu_queue[0].sign_out(_)


class ListPagesTMessage(BaseMessage):

    def __init__(self, update_str: str, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, pagegen=None, firstpage=None, deleted=False, input_field=None) -> None:
        BaseMessage.__init__(
            self,
            navigation,
            self.__class__.__name__ + f'_{self.get_label_addition()}_' + ('00' if not firstpage else self.get_page_label(firstpage)),
            expiry_period=timedelta(hours=2),
            input_field=input_field,
            inlined=False,
            home_after=False,
        )
        self.max_items_per_group = max_items_per_group
        self.max_group_per_page = max_group_per_page
        self.update_str = update_str
        self.first_page = firstpage
        self.deleted = deleted
        self.pagegen = pagegen

    def get_label_addition(self):
        return ''

    def new_instance(self, page):
        cp = self.__class__(
            navigation=self.navigation,
            max_items_per_group=self.max_items_per_group,
            max_group_per_page=self.max_group_per_page,
            pagegen=self.pagegen,
            firstpage=page)
        return cp

    async def put_items_in_pages(self):
        try:
            items = await self.pagegen.get_items_list(self.deleted)
            nitems = len(items)
            last_group_items = nitems % self.max_items_per_group
            ngroups = int(nitems / self.max_items_per_group) + (1 if last_group_items else 0)
            if not last_group_items:
                last_group_items = self.max_items_per_group
            last_page_groups = ngroups % self.max_group_per_page
            npages = int(ngroups / self.max_group_per_page) + (1 if last_page_groups else 0)
            if not last_page_groups:
                last_page_groups = self.max_group_per_page
            if nitems:
                oldpage = None
                self.first_page = thispage = MultipleGroupsOfItems()
                current_item = 0
                for i in range(npages):
                    groups_of_this_page = last_page_groups if i == npages - 1 else self.max_group_per_page
                    start = current_item
                    for j in range(groups_of_this_page):
                        items_of_this_group = last_group_items if i == npages - 1 and j == groups_of_this_page - 1 else self.max_items_per_group
                        group = GroupOfNameDurationItems()
                        thispage.add_group(group)
                        for k in range(items_of_this_group):
                            item = self.pagegen.item_convert(items[current_item], current_item, self.navigation)
                            group.add_item(item)
                            if k == items_of_this_group - 1:
                                thispage.set_start_stop(start, current_item)
                            current_item += 1
                    thispage.set_back_page(oldpage)
                    oldpage = thispage
                    thispage = oldpage.next_page = MultipleGroupsOfItems()
        except Exception:
            _LOGGER.error(traceback.format_exc())

    async def goto_page(self, args, context):
        page, = args
        self.first_page = page
        await self.navigation.goto_menu(self, context)

    async def goto_group(self, args, context):
        group, label = args
        headers = {"range": "bytes=0-10", "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/81.0"}
        for item in group.items:
            if item.thumb and validators.url(item.thumb):
                async with ClientSession() as session:
                    async with session.get(item.thumb, headers=headers) as resp:
                        if not (resp.status >= 200 and resp.status < 300):
                            item.thumb = item.picture = ''
            try:
                await self.navigation._send_app_message(item, label, context)
            except Exception:
                _LOGGER.error(f'goto_group error {traceback.format_exc()}')

    def get_page_label(self, page):
        if page.start_item == page.stop_item:
            return f'{page.start_item + 1}'
        else:
            return f'{page.start_item + 1} - {page.stop_item + 1}'

    def get_group_label(self, group):
        if group.start_item == group.stop_item:
            beginning = f'{group.start_item + 1}) {group.items[0].name}'
            if len(beginning) > 70:
                beginning = beginning[0:70] + '...'
            return f'{beginning} ({duration2string(group.items[0].secs)})'
        else:
            return f'{group.start_item + 1} - {group.stop_item + 1}'

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        if not self.first_page:
            await self.put_items_in_pages()
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        if self.first_page:
            for grp in self.first_page.groups:
                label = self.get_group_label(grp)
                self.add_button(label, self.goto_group, args=(grp, label))
            new_row = True
            if self.first_page.back_page:
                self.add_button(f':arrow_left: {self.get_page_label(self.first_page.back_page)}', self.goto_page, args=(self.first_page.back_page, ), new_row=new_row)
                new_row = False
            if self.first_page.next_page and self.first_page.next_page.is_valid():
                self.add_button(f'{self.get_page_label(self.first_page.next_page)} :arrow_right:', self.goto_page, args=(self.first_page.next_page, ), new_row=new_row)
        return self.update_str


class PlaylistsPagesTMessage(ListPagesTMessage):

    def __init__(self, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, pagegen=None, firstpage=None, userid=None, username=None, params=None) -> None:
        ListPagesTMessage.__init__(
            self,
            update_str=f'List of <b>{username}</b> playlists',
            navigation=navigation,
            max_items_per_group=max_items_per_group,
            max_group_per_page=max_group_per_page,
            firstpage=firstpage,
            pagegen=pagegen if pagegen else PlaylistsPagesGenerator(
                userid,
                username,
                params
            ),
            input_field='Select Playlist'
        )

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        updstr = await super().update(context)
        self.add_button(label=u"\U0001F6AA Sign Out", callback=SignOutTMessage(self.navigation), new_row=True)
        return updstr


class PlaylistItemsPagesTMessage(ListPagesTMessage):

    def __init__(self, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, pagegen=None, firstpage=None, deleted=False, userid=None, username=None, params=None, playlist_obj=None) -> None:
        self.playlist_obj = playlist_obj
        ListPagesTMessage.__init__(
            self,
            update_str=f'List of <b>{playlist_obj.name}</b> items ({playlist_obj.unseen} - \U000023F1 {duration2string(playlist_obj.obj.get_duration())})',
            navigation=navigation,
            max_items_per_group=max_items_per_group,
            max_group_per_page=max_group_per_page,
            firstpage=firstpage,
            deleted=deleted,
            pagegen=pagegen if pagegen else PlaylistItemsPagesGenerator(
                userid,
                username,
                params,
                playlist_obj
            )
        )

    def new_instance(self, page):
        cp = super().new_instance(page)
        cp.playlist_obj = self.playlist_obj
        return cp

    def get_label_addition(self):
        return f'{self.playlist_obj.id}'

    async def list_playlists(self, context):
        await self.navigation.goto_home(context)
        await self.navigation._menu_queue[0].list_page_of_playlists(None, context)

    async def refresh_playlist_object(self, context):
        ppg = PlaylistsPagesGenerator(self.pagegen.proc.userid, self.pagegen.proc.username, self.pagegen.proc.params)
        lst = await ppg.get_items_list(False, playlist=self.playlist_obj.id)
        if lst:
            grp = GroupOfNameDurationItems()
            self.playlist_obj = ppg.item_convert(lst[0], self.playlist_obj.index, self.navigation)
            grp.add_item(self.playlist_obj)
            await self.goto_group((grp, self.get_group_label(grp)), context)

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        updstr = await super().update(context)
        grp = GroupOfNameDurationItems()
        grp.add_item(self.playlist_obj)
        self.add_button(self.get_group_label(grp), self.refresh_playlist_object, new_row=True)
        self.add_button(label=":memo: List", callback=self.list_playlists)
        return updstr


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
        content = "Please insert auth link"
        if context:
            self.user_data = context.user_data.setdefault('user_data', dict())
        return content

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
                        idmsg = await self.navigation.goto_home()
                        await self.navigation.delete_message(self.message_id)
                        await self.navigation.delete_message(idmsg)
            _LOGGER.info(f"Handle for {text}")


class StartTMessage(BaseMessage):
    """Start menu, create all app sub-menus."""

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

    async def sign_out(self, context):
        await self.params.db2.execute("UPDATE user set tg=null WHERE rowid=?", (self.userid, ))
        await self.params.db2.commit()
        self.userid = self.username = self.link = None
        await self.navigation.goto_home(context)

    async def list_page_of_playlists(self, page, context):
        if self.playlists_lister:
            await self.playlists_lister.goto_page((page, ), context)

    async def async_init(self, context: Optional[CallbackContext] = None):
        res = await self.check_if_username_registred(self.params.db2, self.navigation.user_name)
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        if context:
            self.user_data = context.user_data.setdefault('user_data', dict(link=''))
            if 'link' in self.user_data:
                self.link = self.user_data['link']
        if res and self.link:
            self.params.link = self.link
            self.playlists_lister = PlaylistsPagesTMessage(
                self.navigation,
                max_group_per_page=6,
                max_items_per_group=1,
                params=self.params,
                userid=res['userid'],
                username=res['username'])
            # second_menu = SecondMenuMessage(navigation, update_callback=message_args)
            self.add_button(label=":memo: List", callback=self.playlists_lister)
            self.add_button(label=u"\U0001F6AA Sign Out", callback=SignOutTMessage(self.navigation))
            self.userid = res['userid']
            self.username = res['username']
            self.input_field = 'What do you want to do?'
        else:
            self.username = None
            self.userid = None
            action_message = SignUpTMessage(self.navigation, params=self.params)
            # second_menu = SecondMenuMessage(navigation, update_callback=message_args)
            self.add_button(label=":writing_hand: Sign Up", callback=action_message)
            self.input_field = 'Click Sign Up to start procedure'
            # self.add_button(label="Second menu", callback=second_menu)

    def __init__(self, navigation: MyNavigationHandler, message_args) -> None:
        """Init StartTMessage class."""
        super().__init__(navigation, self.__class__.__name__)
        self.params = message_args[0]
        _LOGGER.debug(f'Start Message {message_args[0].args}')
        self.username = None
        self.userid = None
        self.link = None
        self.playlists_lister = None

        # define menu buttons

    async def update(self, context: Optional[CallbackContext] = None):
        await self.async_init(context)
        if self.username:
            return f'Hello <b>{self.username}</b> :musical_note:'
        else:
            return 'Hello: please click :writing_hand: Sign Up'

    @staticmethod
    def run_and_notify() -> str:
        """Update message content."""
        return "This is a notification"

    async def text_input(self, text: str, context: Optional[CallbackContext] = None) -> None:
        """Receive text from console. If used, this function must be instantiated in the child class."""
        _LOGGER.info(f"Handle for {text}")


async def stop_telegram_bot():
    raise SystemExit


def start_telegram_bot(params, loop):
    logging.getLogger('hpack.hpack').setLevel(logging.INFO)
    loop = asyncio.set_event_loop(loop)
    api_key = params.args['telegram']
    _LOGGER.info(f'Starting bot with {params} in loop {id(loop)}')
    TelegramMenuSession(api_key, persistence_path=params.args['pickle']).start(start_message_class=StartTMessage, start_message_args=[params], navigation_handler_class=MyNavigationHandler, stop_signals=())
