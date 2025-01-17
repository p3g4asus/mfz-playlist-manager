import asyncio
import logging
import re
from abc import abstractmethod
from datetime import datetime, timedelta
from html import escape
from os import stat
from os.path import exists, isfile, split
from typing import Any, Coroutine, List, Optional, Union
from urllib.parse import (urlencode)

from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD
from telegram_menu import (BaseMessage, ButtonType, NavigationHandler)
from telegram_menu.models import MenuButton

from common.const import (CMD_CLEAR, CMD_DEL, CMD_DOWNLOAD, CMD_DUMP,
                          CMD_FOLDER_LIST, CMD_FREESPACE, CMD_IORDER,
                          CMD_MEDIASET_BRANDS, CMD_MEDIASET_KEYS,
                          CMD_MEDIASET_LISTINGS, CMD_MOVE, CMD_PLAYID, CMD_RAI_CONTENTSET,
                          CMD_RAI_LISTINGS, CMD_REN, CMD_SEEN, CMD_SORT, CMD_YT_PLAYLISTCHECK, IMG_NO_VIDEO)
from common.playlist import Playlist, PlaylistItem, PlaylistMessage
from common.user import User
from server.telegram.cache import PlaylistTg, cache_del, cache_del_user, cache_get, cache_get_item, cache_get_items, cache_on_item_deleted, cache_store
from server.telegram.pages import ListPagesTMessage, PageGenerator
from server.telegram.message import DeletingTMessage, MyNavigationHandler, NameDurationStatus, NameDurationTMessage, StatusTMessage, duration2string
from server.telegram.refresh import RefreshingTMessage

_LOGGER = logging.getLogger(__name__)


class PlaylistItemTMessage(NameDurationTMessage):
    def refresh_from_cache(self):
        obj = cache_get_item(self.proc.user.rowid, self.pid, self.id)
        if obj:
            self.obj = obj.item
            obj.message = self
            p = cache_get(self.proc.user.rowid, self.pid)
            self.type = p.playlist.type
            self.playlist_name = p.playlist.name
            self.index = obj.index
            self.name = self.obj.title
            self.secs = self.obj.dur
            self.thumb = self.obj.img
            self.deleted = self.obj.seen
            self.is_playing = p.playlist.conf.get('play', dict()).get('id') == self.obj.uid
            return True
        else:
            return False

    def __init__(self, navigation: NavigationHandler, myid: int = None, user: User = None, params: object = None, pid: int = None, **argw) -> None:
        self.pid = pid
        self.current_sort: str = ''
        self.download_message: PlaylistMessage = None
        super().__init__(navigation, myid, user, params)

    def slash_message_processed(self, text: str) -> bool:
        return super().slash_message_processed(text) or (self.status == NameDurationStatus.UPDATING_WAITING and text == '/autodetect')

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.SORTING:
            text = text.strip()
            if re.match(r'^[0-9]+$', text):
                await self.set_iorder_do(int(text))
                await self.switch_to_idle()
        elif self.status == NameDurationStatus.UPDATING_WAITING:
            text = text.strip()
            if text == '/autodetect':
                text = '0'
            if len(text) == 1 or re.match(r'^https://link\.theplatform\.eu', text) and text.find('format=SMIL'):
                await self.get_keys(text)

    async def get_keys(self, smil):
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
        pl = PlaylistMessage(CMD_MEDIASET_KEYS,
                             playlistitem=self.id,
                             smil=smil)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.obj.conf = pl.playlistitem.conf
            self.return_msg = 'Key get OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} getting keys :thumbs_down:'
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
            id=f"long_operation_do{self.label}",
            seconds=3,
            replace_existing=True,
            next_run_time=StatusTMessage.datenow()
        )
        pl = PlaylistMessage(CMD_DOWNLOAD,
                             playlistitem=self.id,
                             fmt=args[0],
                             host=f'{self.proc.params.link}/{self.proc.params.args["sid"]}',
                             conv=args[1])
        self.download_message = pl
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.obj.dl = pl.playlistitem.dl
            self.return_msg = f'Download OK {split(self.obj.dl)[1]} :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} downloading {self.name} :thumbs_down:'
        await self.switch_to_idle()
        self.download_message = None

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

    async def move_to_do(self, args):
        pdst: PlaylistTg
        psrc: PlaylistTg
        pdst, psrc = args
        pl = PlaylistMessage(CMD_MOVE, playlistitem=self.id, playlist=pdst.playlist.rowid)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            cache_store(pl.playlist)
            plTg: PlaylistTg = cache_get(self.proc.user.rowid, pl.playlist.rowid)
            cache_on_item_deleted(self.proc.user.rowid, self.id)
            self.deleted = True
            self.obj.seen = True
            if psrc.message:
                await psrc.message.edit_or_select_items()
                await psrc.message.edit_or_select_if_exists()
            if plTg.message:
                await plTg.message.edit_or_select_items()
                await plTg.message.edit_or_select_if_exists()
            self.return_msg = 'Move OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} Moving {self.name} in {plTg.playlist.name} :thumbs_down:'
        await self.switch_to_idle()

    async def prepare_for_sort(self) -> None:
        self.current_sort = ''
        await self.switch_to_status((NameDurationStatus.SORTING, ))

    async def set_iorder(self) -> None:
        if self.current_sort[0] != u'\U0001F502' or len(self.current_sort) > 1:
            await self.set_iorder_do(int(self.current_sort) if self.current_sort[0] != u'\U0001F502' else self.get_iorder_from_index(int(self.current_sort[1:])))
            await self.switch_to_idle()

    async def add_to_sort(self, args) -> None:
        self.current_sort += f'{args[0]}'
        await self.edit_or_select()

    def get_iorder_from_index(self, index: int) -> int:
        p = cache_get(self.proc.user.rowid, self.pid)
        pis = p.get_items(deleted=False)
        if not index:
            return pis[0].item.iorder - 1
        elif index - 1 < len(pis):
            return pis[index - 1].item.iorder + 1
        else:
            return pis[-1].item.iorder + 1

    async def remove_from_sort(self) -> None:
        if self.current_sort:
            self.current_sort = self.current_sort[0:-1]
            await self.edit_or_select()

    async def set_play_id(self):
        pl = PlaylistMessage(CMD_PLAYID, playlist=self.pid, playid=self.obj.uid if not self.is_playing else None)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            plTg = cache_get(self.proc.user.rowid, self.pid)
            plTg.playlist.conf.update(pl.playlist.conf)
            if plTg.message:
                await plTg.message.edit_or_select_items()

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.refresh_from_cache()
        if not self.deleted:
            if self.status == NameDurationStatus.IDLE:
                self.add_button(u'\U0001F5D1', self.delete_item_pre_pre, args=(CMD_SEEN, ))
                self.add_button(u'\U00002211', self.switch_to_status, args=(NameDurationStatus.SORTING, ))
                self.add_button(u'\U0001F517', self.switch_to_status, args=(NameDurationStatus.DOWNLOADING_WAITING, ))
                self.add_button(u'\U0001F4EE', self.switch_to_status, args=(NameDurationStatus.MOVING, ))
                self.add_button(u'\U000025B6', self.set_play_id)
                if self.type == "mediaset":
                    self.add_button(u'\U0001F511', self.switch_to_status, args=(NameDurationStatus.UPDATING_WAITING, ))
                if self.obj.takes_space():
                    self.add_button(u'\U0001F4A3', self.delete_item_pre_pre, args=(CMD_FREESPACE, ))
            elif self.status == NameDurationStatus.UPDATING_WAITING:
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
                return 'Enter network filter ' + ("<a href=\"" + self.obj.conf["pageurl"] + "\">here</a> " if "pageurl" in self.obj.conf else "") + '<u>SMIL</u> or /autodetect'
            elif self.status == NameDurationStatus.UPDATING_RUNNING:
                return f'Getting keys {"." * (self.sub_status & 0xFF)}'
            elif self.status == NameDurationStatus.MOVING:
                self.input_field = u'\U0001F449'
                pps: List[PlaylistTg] = cache_get(self.proc.user.rowid)
                myself: PlaylistTg = cache_get(self.proc.user.rowid, self.obj.playlist)
                for pp in pps:
                    if pp.playlist.rowid != self.obj.playlist:
                        self.add_button(pp.playlist.name, self.move_to_do, args=(pp, myself))
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
            elif self.status == NameDurationStatus.DOWNLOADING_WAITING:
                self.input_field = u'\U0001F449'
                self.add_button('bestaudio', self.download_format, args=('bestaudio/best', 0))
                self.add_button('best', self.download_format, args=('bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 0))
                self.add_button('worstaudio', self.download_format, args=('worstaudio/worst', 0))
                self.add_button('worst', self.download_format, args=('worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst', 0))
                if 'twitch.tv' in self.obj.link:
                    self.add_button('bestaudio os', self.download_format, args=('bestaudio/best', 4))
                    self.add_button('best os', self.download_format, args=('bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 4))
                    self.add_button('worstaudio os', self.download_format, args=('worstaudio/worst', 4))
                    self.add_button('worst os', self.download_format, args=('worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst', 4))
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
            elif self.status == NameDurationStatus.DOWNLOADING:
                self.add_button(f':cross_mark: Abort {self.id}', self.stop_download, args=(self.id, ))
                status = None if not self.download_message else self.download_message.f(PlaylistMessage.PING_STATUS)
                if status and 'que' in status:
                    if not status['que']:
                        self.add_button(':cross_mark::cross_mark: Abort All', self.stop_download, args=(None, ))
                        upd = f'{escape(self.name)} downloading {"." * (self.sub_status & 0xFF)}'
                        if 'raw' in status:
                            dl = status['raw']
                            upd2 = ''
                            if 'status' in dl:
                                upd2 += dl['status'] + '\n'
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
                else:
                    upd = f'{escape(self.name)} getting download status {"." * (self.sub_status & 0xFF)}'
                return upd
            elif self.status == NameDurationStatus.SORTING:
                for i in range(10):
                    self.add_button(f'{(i + 1) % 10}' + u'\U0000FE0F\U000020E3', self.add_to_sort, args=((i + 1) % 10, ))
                self.add_button(u'\U000002C2', self.remove_from_sort)
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
                if not self.current_sort:
                    self.add_button(u'\U0001F502', self.add_to_sort, args=(u'\U0001F502', ), new_row=True)
                else:
                    self.add_button(self.current_sort, self.set_iorder, new_row=True)
                self.input_field = f'Enter \U00002211 for {self.name}'
                return f'Enter \U00002211 for <b>{self.name}</b>'
        elif self.status == NameDurationStatus.IDLE:
            self.add_button(u'\U0000267B', self.delete_item_pre_pre, args=(CMD_SEEN, ))
            if self.obj.takes_space():
                self.add_button(u'\U0001F4A3', self.delete_item_pre_pre, args=(CMD_FREESPACE, ))
        upd = await super().update(context)
        if upd:
            return upd
        upd += f'<a href="{self.obj.link}">{self.index + 1})<b> {escape(self.name)}</b> - <i>Id {self.id}</i></a> :memo: {self.playlist_name}\n\U000023F1 {duration2string(self.secs)}\n\U000023F3: {self.obj.datepub[0:19]}\n'
        if self.obj.conf and 'author' in self.obj.conf and self.obj.conf['author']:
            upd += f'\U0001F64B: {self.obj.conf["author"]}\n'
        upd += f'\U00002211: {self.obj.iorder}'
        mainlnk = f'{self.proc.params.link}/{self.proc.params.args["sid"]}'
        if 'twitch.tv' in self.obj.link:
            lnk = f'{mainlnk}/twi?'
            par = urlencode(dict(link=self.obj.link))
            upd += f'\n<a href="{lnk}{par}">\U0001F7E3 TWI</a>'
        if 'pageurl' in self.obj.conf:
            upd += f'\n<a href="{self.obj.conf["pageurl"]}">\U0001F4C3 Main</a>'
        if '_drm_m' in self.obj.conf and self.obj.conf['_drm_m']:
            upd += u'\n\U0001F511'
            if '_drm_k' in self.obj.conf and self.obj.conf['_drm_k']:
                upd += u'\U0001F511'
        if not self.obj.dl and self.obj.conf and isinstance(self.obj.conf, dict) and 'todel' in self.obj.conf and self.obj.conf['todel']:
            self.obj.dl = self.obj.conf['todel'][0]
        if (isinstance(self.obj.conf, dict) and (sec := 'sec' in self.obj.conf)) or self.is_playing:
            upd += '\n'
            if sec:
                upd += f'\U000023F2 {duration2string(int(self.obj.conf["sec"]))}'
            if self.is_playing:
                if not sec:
                    upd += '0s'
                upd += ' \U000025B6'
        if self.obj.dl and exists(self.obj.dl) and isfile(self.obj.dl):
            sta = stat(self.obj.dl)
            upd += f'\n<a href="{mainlnk}/dl/{self.proc.user.token}/{self.id}">DL {self.sizeof_fmt(sta.st_size) if sta else ""}</a>'
        # upd += f'<tg-spoiler><pre>{json.dumps(self.obj.conf, indent=4)}</pre></tg-spoiler>'
        chapters = self.dictget(self.obj.conf, 'chapters', [])
        if chapters:
            upd += '\n<b>Chapters:</b>\n<tg-spoiler>'
            i = 0
            while len(upd) <= 970 and i < len(chapters):
                ch = chapters[i]
                upd += f'<b>{duration2string(int(ch["start_time"]))}</b>\t<u>{escape(ch["title"])}</u>\n'
                i += 1
            if i:
                upd = upd[:-1]
            upd += '</tg-spoiler>'
        if self.return_msg:
            upd += f'\n<b>{self.return_msg}</b>'
        elif self.deleted:
            upd = f'<s>{upd}</s>'
        return upd

    async def delete_item_do(self):
        if self.del_action == CMD_SEEN:
            pl = PlaylistMessage(CMD_SEEN, playlistitem=self.id, seen=not self.deleted)
            pl = await self.proc.process(pl)
            if pl.rv == 0:
                self.deleted = not self.deleted
                self.obj.seen = not self.obj.seen
                cache_on_item_deleted(self.proc.user.rowid, self.pid)
                plTg = cache_get(self.proc.user.rowid, self.pid)
                if plTg.message:
                    await plTg.message.edit_or_select_items(5)
                    await plTg.message.edit_or_select_if_exists(5)
                self.return_msg = ('Delete' if self.deleted else 'Restore') + ' OK :thumbs_up:'
            else:
                self.return_msg = f'Error {pl.rv} {"deleting" if not self.deleted else "restoring"} {self.name} :thumbs_down:'
        elif self.del_action == CMD_FREESPACE:
            pl = PlaylistMessage(CMD_FREESPACE, playlistitem=self.id)
            pl = await self.proc.process(pl)
            if pl.rv == 0:
                self.obj.dl = None
                self.obj.conf = pl.playlistitem.conf
                self.return_msg = f'Free Space OK (deleted files: {pl.deleted}):thumbs_up:'
            else:
                self.return_msg = f'Error {pl.rv} freeing space of {self.name} :thumbs_down:'

    async def set_iorder_do(self, iorder):
        pl = PlaylistMessage(CMD_IORDER, playlistitem=self.id, iorder=iorder)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            cache_store(pl.playlist)
            plTg = cache_get(self.proc.user.rowid, self.pid)
            if plTg.message:
                await plTg.message.edit_or_select_items()
                await plTg.message.edit_or_select_if_exists()
            self.return_msg = 'IOrder OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} IOrdering {self.name} :thumbs_down:'


class PlaylistTMessage(NameDurationTMessage, RefreshingTMessage):
    def refresh_from_cache(self):
        obj = cache_get(self.proc.user.rowid, self.id)
        if obj:
            self.obj = obj.playlist
            obj.message = self
            self.index = obj.index
            self.name = self.obj.name
            img = None
            self.unseen = 0
            for pli in self.obj.items:
                if not pli.seen:
                    self.unseen += 1
                    if not img:
                        img = pli.img
            self.secs = self.obj.get_duration()
            self.thumb = img if img else IMG_NO_VIDEO
            self.deleted = False
            return True
        else:
            return False

    def __init__(self, navigation: NavigationHandler, myid: int = None, user: User = None, params: object = None, **argw) -> None:
        super().__init__(
            navigation,
            myid=myid,
            user=user,
            params=params)
        self.del_and_recreate = False
        self.set_playlist(self.obj)

    async def edit_or_select_items(self, delay: float = 0):
        itemsTg = cache_get_items(self.proc.user.rowid, self.id, True)
        for itemTg in itemsTg:
            if itemTg.message:
                await itemTg.message.edit_or_select_if_exists(delay)

    async def delete_item_do(self):
        if self.del_action == CMD_DEL:
            pl = PlaylistMessage(CMD_DEL, playlist=self.id)
            pl = await self.proc.process(pl)
            if pl.rv == 0:
                self.deleted = True
                await self.navigation.delete_message(self.message_id)
                itemsTg = cache_get_items(self.proc.user.rowid, self.id, True)
                for itTg in itemsTg:
                    if itTg.message:
                        await self.navigation.delete_message(itTg.message.message_id)
                cache_del(self.obj)
                plsTg: List[PlaylistTg] = cache_get(self.proc.user.rowid)
                for plTg in plsTg:
                    if plTg.message:
                        await plTg.message.edit_or_select_if_exists()
                lmm = self.navigation._menu_queue[-1]
                if isinstance(lmm, PlaylistItemsPagesTMessage) and\
                        lmm.playlist_obj.id == self.id:
                    await self.navigation.goto_back()
                lmm = self.navigation._menu_queue[-1]
                if isinstance(lmm, PlaylistsPagesTMessage):
                    await self.navigation.goto_menu(lmm, None, add_if_present=False)
                self.return_msg = 'Delete OK :thumbs_up:'
            else:
                self.return_msg = f'Error {pl.rv} deleting {self.name} :thumbs_down:'
        else:
            pl = PlaylistMessage(CMD_CLEAR, playlist=self.id)
            pl = await self.proc.process(pl)
            if pl.rv == 0:
                for pli in self.obj.items:
                    if not pli.seen:
                        pli.seen = True
                itemsTg = cache_get_items(self.proc.user.rowid, self.id, True)
                for itemTg in itemsTg:
                    if itemTg.message:
                        itemTg.message.deleted = True
                        itemTg.message.obj.seen = True
                plTg: PlaylistTg = cache_get(self.proc.user.rowid, self.id)
                plTg.refresh(plTg.playlist, plTg.index)
                self.return_msg = 'Clear OK :thumbs_up:'
                self.status = NameDurationStatus.RETURNING_IDLE
                await self.edit_or_select_items()
                await self.edit_or_select_if_exists()
            else:
                self.return_msg = f'Error {pl.rv} clearing {self.name} :thumbs_down:'

    async def rename_playlist_2(self, newname):
        pl = PlaylistMessage(CMD_REN, playlist=self.id, to=newname)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            self.obj.name = self.name = newname
            lmm = self.navigation._menu_queue[-1]
            if isinstance(lmm, PlaylistsPagesTMessage):
                await self.navigation.goto_menu(lmm, None, add_if_present=False)
            self.return_msg = 'Rename OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} renaming {self.name} :thumbs_down:'

    def sort_playlist(self):
        asyncio.get_event_loop().create_task(self.sort_playlist_1())

    async def switch_to_idle_end(self):
        if self.del_and_recreate:
            self.del_and_recreate = False
            await self.send()
        else:
            await super().switch_to_idle_end()

    async def sort_playlist_1(self):
        self.status = NameDurationStatus.SORTING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id=f"long_operation_do{self.label}",
            seconds=3,
            replace_existing=True,
            next_run_time=StatusTMessage.datenow()
        )
        pl = PlaylistMessage(CMD_SORT, playlist=self.id)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            cache_store(pl.playlist)
            await self.edit_or_select_items()
            self.del_and_recreate = True
            self.return_msg = 'Sort OK :thumbs_up:'
        else:
            self.return_msg = f'Error {pl.rv} sorting {self.name} :thumbs_down:'
        await self.switch_to_idle()

    async def on_refresh_finish(self, pl: PlaylistMessage):
        self.del_and_recreate = True
        lmm = self.navigation._menu_queue[-1]
        if isinstance(lmm, PlaylistsPagesTMessage) or\
           (isinstance(lmm, PlaylistItemsPagesTMessage) and lmm.playlist_obj.id == self.id):
            await self.navigation.goto_menu(lmm, None, add_if_present=False)
        await self.edit_or_select_items()
        await self.switch_to_idle()

    async def on_refresh_abort(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.switch_to_idle()

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.RENAMING:
            text = text.strip()
            if re.match(r'^[0-9a-zA-Z_\-]+$', text):
                await self.rename_playlist_2(text)
                await self.switch_to_idle()
        else:
            await super().text_input(text, context)

    async def list_items(self, args, context):
        p = PlaylistItemsPagesTMessage(self.navigation, deleted=args[0], user=self.proc.user, params=self.proc.params, playlist_obj=self)
        if self.navigation._menu_queue and isinstance(self.navigation._menu_queue[-1], PlaylistItemsPagesTMessage):
            await self.navigation.goto_back()
        await self.navigation.goto_menu(p, context, sync=True)
        if p.first_page.groups:
            grp = p.first_page.groups[0]
            await p.goto_group((grp,), context)

    async def edit_me(self, context=None):
        cls = None
        if self.obj.type == 'youtube':
            cls = YoutubeDLPlaylistTMessage
        elif self.obj.type == 'mediaset':
            cls = MediasetPlaylistTMessage
        elif self.obj.type == 'rai':
            cls = RaiPlaylistTMessage
        elif self.obj.type == 'localfolder':
            cls = LocalFolderPlaylistTMessage

        if cls:
            but = cls(
                self.navigation,
                user=self.proc.user,
                params=self.proc.params,
                playlist=self.obj)
            await self.navigation.goto_menu(but)

    @staticmethod
    def list_items_taking_space(it: PlaylistItem) -> bool:
        return it.takes_space()

    async def update(self, context: Union[CallbackContext, None] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.refresh_from_cache()
        lnk = f'{self.proc.params.link}/{self.proc.params.args["sid"]}'
        if not self.deleted:
            if self.status == NameDurationStatus.IDLE:
                self.add_button(u'\U00002699', self.edit_me)
                self.add_button(u'\U000000AB\U000000BB', self.switch_to_status, args=(NameDurationStatus.RENAMING, ))
                self.add_button(u'\U0001F5D1', self.switch_to_status, args=(NameDurationStatus.DELETING_CONFIRM, ))
                self.add_button(u'\U0001F9F9', self.delete_item_pre_pre, args=(CMD_CLEAR, ))
                self.add_button(u'\U0001F501', self.switch_to_status, args=(NameDurationStatus.UPDATING_INIT, ))
                self.add_button(u'\U00002211', self.sort_playlist)
                self.add_button(':play_button:', btype=ButtonType.LINK, web_app_url=f'{lnk}-s/play/workout.htm?{urlencode(dict(name=self.name))}')
                self.add_button(u'\U0001F4D2', btype=ButtonType.LINK, web_app_url=f'{lnk}-s/index.htm?{urlencode(dict(pid=self.id))}')
                self.add_button(':memo:', self.list_items, args=(False, ))
                self.add_button(':eye:', self.list_items, args=(True, ))
                self.add_button(u'\U0001F4A3', self.list_items, args=(PlaylistTMessage.list_items_taking_space, ))
                # self.add_button(':play_button:', btype=ButtonType.LINK, web_app_url=f'{self.proc.params.link}/{self.proc.params.args["sid"]}-s/play/workout.htm?{urlencode(dict(name=self.name))}')
            elif self.status == NameDurationStatus.RENAMING:
                self.input_field = f'Enter new name for {self.name}'
                self.add_button(':cross_mark: Abort', self.switch_to_idle)
                return f'Enter new name for <b>{self.name}</b>'
            elif self.status == NameDurationStatus.DELETING_CONFIRM:
                self.input_field = u'\U0001F449'
                self.add_button('\U00002705 Yes', self.delete_item_pre_pre, args=(CMD_DEL, ))
                self.add_button(':cross_mark: No', self.switch_to_idle)
                return f'Are you sure to delete <b>{self.name}</b>?'
            elif self.status == NameDurationStatus.SORTING:
                self.input_field = u'\U0001F570'
                return f'{self.name} sorting {"." * (self.sub_status & 0xFF)}'
            else:
                updt = await DeletingTMessage.update(self, context)
                if updt:
                    return updt
                updt = await RefreshingTMessage.update(self, context)
                if updt:
                    return updt
        datepubo = datetime.fromtimestamp(int(self.obj.dateupdate / 1000))
        upd = f'{self.index + 1}) <b>{self.name}</b> - <i>Id {self.id}</i>'
        if self.obj.type == 'youtube':
            upd += '\U0001F534'
        elif self.obj.type == 'rai':
            upd += '\U0001F535'
        elif self.obj.type == 'mediaset':
            upd += '\U00002B24'
        upd += f'\nLength: {self.unseen} \U000023F1 {duration2string(self.obj.get_duration())}\n'
        upd += f':eye: {len(self.obj.items)} \U000023F1 {duration2string(self.obj.get_duration(True))}\n'
        upd += f'Update \U000023F3: {datepubo.strftime("%Y-%m-%d %H:%M:%S")} ' + ("\U00002705" if self.obj.autoupdate else "") + '\n'
        par = urlencode(dict(name=self.name, host=lnk))
        uprefix: str = f'{lnk}/m3u/{self.proc.user.token}?{par}&'
        upd += f'<a href="{uprefix}fmt=m3u">M3U8</a>, <a href="{uprefix}fmt=ely">ELY</a>, <a href="{uprefix}fmt=json">JSON</a>\n'
        upd += f'<a href="{uprefix}fmt=m3u&conv=4">M3U8c4</a>, <a href="{uprefix}fmt=ely&conv=4">ELYc4</a>, <a href="{uprefix}fmt=json&conv=4">JSONc4</a>\n'
        upd += f'<a href="{uprefix}fmt=m3u&conv=2">M3U8c2</a>, <a href="{uprefix}fmt=ely&conv=2">ELYc2</a>, <a href="{uprefix}fmt=json&conv=2">JSONc2</a>\n'
        upd += f'Playback Rate {self.obj.conf["play"]["rate"] if "play" in self.obj.conf and "rate" in self.obj.conf["play"] else 1.0:.2f}\U0000274E'
        # upd += f'<tg-spoiler><pre>{json.dumps(self.obj.conf, indent=4)}</pre></tg-spoiler>'
        if self.return_msg:
            upd += f'\n<b>{self.return_msg}</b>'
        elif self.deleted:
            upd = f'<s>{upd}</s>'
        return upd


class PlaylistsPagesGenerator(PageGenerator):

    def item_convert(self, myid, navigation, **_):
        plTg = cache_get(self.proc.user.rowid, myid)
        return plTg.message if plTg and plTg.message and plTg.message.refresh_from_cache() else\
            PlaylistTMessage(navigation, myid, self.proc.user, self.proc.params)

    def get_playlist_message(self, pid=None, deleted=False):
        return PlaylistMessage(CMD_DUMP, useri=self.proc.user.rowid, load_all=1 if deleted else 0, playlist=pid)

    async def get_items_list(self, deleted=False, pid=None):
        plout = await self.proc.process(self.get_playlist_message(pid, deleted))
        cache_del_user(self.proc.user.rowid, plout.playlists)
        return plout.playlists


class PlaylistItemsPagesGenerator(PageGenerator):
    def __init__(self, user: User, params, pid):
        super().__init__(
            user,
            params
        )
        self.pid = pid

    def item_convert(self, myid, navigation):
        itTg = cache_get_item(self.proc.user.rowid, self.pid, myid)
        return itTg.message if itTg and itTg.message and itTg.message.refresh_from_cache() else\
            PlaylistItemTMessage(
                navigation,
                myid=myid,
                user=self.proc.user,
                params=self.proc.params,
                pid=self.pid)

    async def get_items_list(self, deleted=False):
        itemsTg = cache_get_items(self.proc.user.rowid, self.pid, deleted)
        rv = []
        for itTg in itemsTg:
            rv.append(itTg.item)
        return rv


class PlaylistsPagesTMessage(ListPagesTMessage):

    def __init__(self, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, firstpage=None, deleted=False, user=None, params=None) -> None:
        super().__init__(
            update_str=f'List of <b>{user.username}</b> playlists',
            navigation=navigation,
            max_items_per_group=max_items_per_group,
            max_group_per_page=max_group_per_page,
            firstpage=firstpage,
            deleted=deleted,
            pagegen=PlaylistsPagesGenerator(
                user,
                params
            ),
            input_field='Select Playlist'
        )

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        updstr = await super().update(context)
        self.add_button(label=u"\U0001F3E0 Home", callback=self.navigation.goto_home, new_row=True)
        return updstr


class PlaylistItemsPagesTMessage(ListPagesTMessage):

    def __init__(self, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, firstpage=None, deleted=False, user=None, params=None, playlist_obj: Optional[PlaylistTMessage] = None) -> None:
        self.playlist_obj = playlist_obj
        super().__init__(
            update_str=f'List of <b>{playlist_obj.name}</b> items ({playlist_obj.unseen} - \U000023F1 {duration2string(playlist_obj.obj.get_duration())})',
            navigation=navigation,
            max_items_per_group=max_items_per_group,
            max_group_per_page=max_group_per_page,
            firstpage=firstpage,
            deleted=deleted,
            pagegen=PlaylistItemsPagesGenerator(
                user,
                params,
                playlist_obj.id
            )
        )

    def get_label_addition(self):
        return f'{self.playlist_obj.id}'

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        updstr = await super().update(context)
        self.add_button(label=u"\U0001F519", callback=self.navigation.goto_back, new_row=True)
        self.add_button(label=u"\U0001F3E0 Home", callback=self.navigation.goto_home)
        return updstr


class ChangeOrderedOrDeleteOrCancelTMessage(BaseMessage):
    def __init__(self, navigation: NavigationHandler, playlist: Playlist, plinfo: object) -> None:
        super().__init__(
            navigation,
            self.__class__.__name__,
            input_field=plinfo["title"])
        self.playlist = playlist
        self.plinfo = plinfo

    async def toggle_ordered(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        self.plinfo["ordered"] = not self.plinfo["ordered"]
        await self.navigation.goto_menu(self, context, add_if_present=False)

    async def remove(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        for i in range(len(self.playlist.conf['playlists'])):
            p = self.playlist.conf['playlists'][i]
            if p["id"] == self.plinfo["id"]:
                del self.playlist.conf['playlists'][i]
                break
        await self.navigation.goto_back()

    async def update(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = self.plinfo["title"]
        self.add_button('Ordered: ' + ("\U00002611" if self.plinfo["ordered"] else "\U00002610"), self.toggle_ordered, new_row=True)
        self.add_button('Remove: \U0001F5D1', self.remove, new_row=True)
        self.add_button('OK: \U0001F197', self.navigation.goto_back, new_row=True)
        return f'{self.plinfo["title"]} modify'


class PlaylistNamingTMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        self.playlist = playlist
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field='\U0001F50D Playlist link or id' if self.playlist.name else 'Enter Playlist Name',
            user=user,
            params=params)
        if not self.playlist.name:
            self.status = NameDurationStatus.NAMING

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.NAMING:
            text = text.strip()
            if re.match(r'^[0-9a-zA-Z_\-]+$', text):
                self.playlist.name = text
                self.return_msg = f':thumbs_up: New name {text}'
                await self.switch_to_idle()
            else:
                self.return_msg = f':thumbs_down: Invalid name {text}. Please try again'

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        if self.status == NameDurationStatus.NAMING:
            self.input_field = 'Enter Playlist Name'
            if self.playlist.name:
                self.add_button(':cross_mark: Abort Naming', self.switch_to_status, args=(NameDurationStatus.IDLE, ))
            else:
                self.add_button(':cross_mark: Abort', self.navigation.goto_back)
        else:
            self.input_field = '\U0001F50D Playlist link or id'


class YoutubeDLPlaylistTMessage(PlaylistNamingTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        if not playlist:
            playlist = Playlist(
                type='youtube',
                useri=user.rowid,
                autoupdate=False,
                dateupdate=0,
                conf=dict(playlists=[], play=dict()))
        super().__init__(
            navigation,
            user=user,
            params=params,
            playlist=playlist)
        self.checking_playlist = ''
        for p in playlist.conf['playlists']:
            p['ordered'] = p.get('ordered', True)

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        if self.status == NameDurationStatus.IDLE:
            text = text.strip()
            if text:
                self.checking_playlist = text
                asyncio.create_task(self.check_playlist(text))
        else:
            await super().text_input(text, context)

    async def check_playlist(self, text):
        self.status = NameDurationStatus.DOWNLOADING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="check_playlist",
            seconds=3,
            replace_existing=True,
            next_run_time=StatusTMessage.datenow()
        )
        pl = PlaylistMessage(CMD_YT_PLAYLISTCHECK, text=text)
        pl = await self.proc.process(pl)
        if pl.rv == 0:
            plinfo = pl.playlistinfo
            add = True
            for p in self.playlist.conf['playlists']:
                if p["id"] == plinfo["id"]:
                    self.return_msg = f'\U0001F7E1 {plinfo["title"]} already present!'
                    add = False
                    break
            if add:
                plinfo["ordered"] = True
                self.return_msg = f':thumbs_up: ({plinfo["title"]} - {plinfo["id"]})'
                self.playlist.conf['playlists'].append(plinfo)
        else:
            self.return_msg = f'Error {pl.rv} with playlist {text} :thumbs_down:'
        await self.switch_to_idle()

    async def toggle_autoupdate(self, context: Optional[CallbackContext] = None):
        self.playlist.autoupdate = not self.playlist.autoupdate
        await self.edit_or_select(context)

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        upd = ''
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        await PlaylistNamingTMessage.update(self, context)
        if self.status == NameDurationStatus.IDLE:
            self.input_field = '\U0001F50D Playlist link or id'
            self.add_button(f'Name: {self.playlist.name}', self.switch_to_status, args=(NameDurationStatus.NAMING, ), new_row=True)
            self.add_button('AutoUpdate: ' + ("\U00002611" if self.playlist.autoupdate else "\U00002610"), self.toggle_autoupdate)
            new_row = True
            if self.playlist.conf['playlists']:
                for p in self.playlist.conf['playlists']:
                    self.add_button(('\U00002B83 ' if p["ordered"] else '') + p["title"], ChangeOrderedOrDeleteOrCancelTMessage(self.navigation, playlist=self.playlist, plinfo=p), new_row=True)
                self.add_button(u'\U0001F501', RefreshNewPlaylistTMessage(
                    self.navigation,
                    user=self.proc.user,
                    params=self.proc.params,
                    playlist=self.playlist
                ), new_row=True)
                new_row = False
            self.add_button(':cross_mark: Abort', self.navigation.goto_back, new_row=new_row)
        elif self.status == NameDurationStatus.DOWNLOADING:
            self.input_field = u'\U0001F570'
            upd = f'{escape(self.checking_playlist)} finding playlist info {"." * (self.sub_status & 0xFF)}'
        if self.return_msg:
            upd = f'<b>{self.return_msg}</b>'
        return upd if upd else self.input_field


class LocalFolderPlaylistTMessage(PlaylistNamingTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        if not playlist:
            playlist = Playlist(
                type='localfolder',
                useri=user.rowid,
                autoupdate=False,
                dateupdate=0,
                conf=dict(playlists=dict(), folders=dict(), play=dict()))
        super().__init__(
            navigation,
            user=user,
            params=params,
            playlist=playlist)
        self.listings_changed = False
        self.listings_done = False

    def get_listings_command(self):
        return PlaylistMessage(CMD_FOLDER_LIST)

    async def listing_refresh_1(self, cmd, context):
        self.status = NameDurationStatus.LISTING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="listing_refresh",
            seconds=3,
            replace_existing=True,
            next_run_time=StatusTMessage.datenow()
        )
        pl = await self.proc.process(cmd)
        if pl.rv == 0:
            self.playlist.conf['folders'] = pl.folders
            self.listings_changed = True
            self.return_msg = ''
        else:
            self.return_msg = f'Error {pl.rv} listing folders :thumbs_down:'
        await self.switch_to_idle()

    async def listings_refresh(self, context: Optional[CallbackContext] = None):
        if self.status == NameDurationStatus.IDLE:
            self.playlist.conf['folders'] = dict()
            cmd = self.get_listings_command()
            asyncio.create_task(self.listing_refresh_1(cmd, context))

    async def toggle_autoupdate(self, context: Optional[CallbackContext] = None):
        self.playlist.autoupdate = not self.playlist.autoupdate
        await self.edit_or_select(context)

    async def toggle_playlist(self, args, context: Optional[CallbackContext] = None):
        pid = args[0]
        if pid in self.playlist.conf['playlists']:
            del self.playlist.conf['playlists'][pid]
        else:
            self.playlist.conf['playlists'][pid] = self.playlist.conf['folders'][pid]
        await self.edit_or_select(context)

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        upd = ''
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        await PlaylistNamingTMessage.update(self, context)
        if self.status == NameDurationStatus.IDLE:
            self.input_field = '\U0001F50D Select folder'
            self.add_button(f'Name: {self.playlist.name}', self.switch_to_status, args=(NameDurationStatus.NAMING, ), new_row=True)
            self.add_button('AutoUpdate: ' + ("\U00002611" if self.playlist.autoupdate else "\U00002610"), self.toggle_autoupdate)
            self.add_button('Refresh Listings', self.listings_refresh)
            new_row = True
            foldd = self.playlist.conf['folders']
            playd = self.playlist.conf['playlists']
            if foldd:
                n_ok: int = 0
                for pid, p in playd.copy().items():
                    sel = pid in foldd
                    if not sel:
                        del playd[pid]
                for pid, p in foldd.items():
                    sel = pid in playd
                    self.add_button(("\U00002611 " if sel else "\U00002610 ") + p["title"], self.toggle_playlist, args=(pid, ), new_row=True)
                    if sel:
                        n_ok += 1
                if n_ok:
                    self.add_button(u'\U0001F501', RefreshNewPlaylistTMessage(
                        self.navigation,
                        user=self.proc.user,
                        params=self.proc.params,
                        playlist=self.playlist
                    ), new_row=True)
                    new_row = False
            elif not self.listings_done:
                self.listings_done = True
                await self.listings_refresh()
            self.add_button(':cross_mark: Abort', self.navigation.goto_back, new_row=new_row)
            if self.listings_changed:
                upd = 'Available folders:\n'
                self.listings_changed = False
                for f in self.playlist.conf['folders']:
                    upd += f['title'] + '\r\n'
        elif self.status == NameDurationStatus.LISTING:
            self.input_field = u'\U0001F570'
            return f'Downloading listings {"." * (self.sub_status & 0xFF)}'
        if self.return_msg:
            upd = f'<b>{self.return_msg}</b>'
        return upd if upd else self.input_field


class SubBrandSelectTMessage(BaseMessage):
    def __init__(self, navigation: NavigationHandler, playlist: Playlist = None) -> None:
        self.playlist = playlist
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field=f'Select content for {playlist.conf["brand"]["title"]}')
        self.compute_id_map()

    def compute_id_map(self):
        self.id_map = dict()
        for i, b in enumerate(self.playlist.conf['subbrands_all']):
            self.id_map[str(b['id'])] = i + 1

    def get_brand_index(self, brand):
        return self.id_map.get(str(brand['id']), 0)

    async def toggle_selected(self, args, context):
        subid, = args
        found = False
        for i in range(len(self.playlist.conf['subbrands'])):
            b = self.playlist.conf['subbrands'][i]
            if b['id'] == subid:
                del self.playlist.conf['subbrands'][i]
                found = True
                break
        if not found:
            for b in self.playlist.conf['subbrands_all']:
                if b['id'] == subid:
                    self.playlist.conf['subbrands'].append(b)
                    break
        await self.navigation.goto_menu(self, context, add_if_present=False)

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = f'Select content for {self.playlist.conf["brand"]["title"]}'
        for b in self.playlist.conf['subbrands_all']:
            subid = b["id"]
            subchk = False
            for b2 in self.playlist.conf['subbrands']:
                if b2['id'] == subid:
                    subchk = True
                    break
            self.add_button(f"[{self.get_brand_index(b)}] {b['title']} - {b['desc']}" + (" \U00002611" if subchk else " \U00002610"), self.toggle_selected, args=(b['id'], ), new_row=True)
        self.add_button('OK: \U0001F197', self.navigation.goto_back, new_row=True)
        return self.input_field


class SelectDayTMessage(BaseMessage):
    def __init__(self, navigation: NavigationHandler, playlist: Playlist = None) -> None:
        self.playlist = playlist
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field='Select day of listing')

    def nearest_weekday(self, weekday):
        d2 = datetime.now()
        v = -1
        sum = 0
        while True:
            if weekday == d2.weekday():
                return d2
            v *= -1
            if v > 0:
                sum += 1
            d2 = datetime.now() + timedelta(days=sum * v)
        return 0

    async def select_day(self, args, context):
        day, = args
        self.playlist.conf['listings_command'] = dict(datestart=int(self.nearest_weekday(day).replace(hour=0, minute=0, second=1).timestamp() * 1000))
        await self.navigation.goto_back()

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.input_field = 'Select day of listing'
        d = self.nearest_weekday(0)
        for _ in range(7):
            self.add_button(f'{d:%a}', self.select_day, args=(d.weekday(), ))
            d += timedelta(days=1)
        return self.input_field


class MedRaiPlaylistTMessage(PlaylistNamingTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None, playlist_type: str = None) -> None:
        if not playlist:
            playlist = Playlist(
                type=playlist_type,
                useri=user.rowid,
                autoupdate=False,
                dateupdate=0,
                conf=dict(brand=dict(id=None, desc=None, title=None), subbrands=[], subbrands_all=[], listings_command=None, play=dict()))
        else:
            if 'subbrands_all' not in playlist.conf:
                playlist.conf['subbrands_all'] = []
            playlist.conf['listings_command'] = None
        if not playlist.conf['subbrands_all'] and playlist.conf['subbrands']:
            playlist.conf['subbrands_all'] = playlist.conf['subbrands'].copy()
        if 'title' not in playlist.conf['brand'] and playlist.conf['subbrands']:
            playlist.conf['brand']['title'] = playlist.conf['subbrands'][0]['title']
        super().__init__(
            navigation,
            user=user,
            params=params,
            playlist=playlist)
        self.listings_cache = []
        self.listings_filter = ''
        self.listings_changed = False

    @abstractmethod
    def get_listings_command(self):
        return

    @abstractmethod
    def get_subbrand_command(self):
        return

    async def toggle_autoupdate(self, context: Optional[CallbackContext] = None):
        self.playlist.autoupdate = not self.playlist.autoupdate
        await self.edit_or_select(context)

    async def listing_refresh_1(self, cmd, context):
        self.status = NameDurationStatus.LISTING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="listing_refresh",
            seconds=3,
            replace_existing=True,
            next_run_time=StatusTMessage.datenow()
        )
        pl = await self.proc.process(cmd)
        if pl.rv == 0:
            self.listings_cache = pl.brands
            self.listings_changed = True
            self.return_msg = ''
        else:
            self.return_msg = f'Error {pl.rv} finding listings :thumbs_down:'
        await self.switch_to_idle()

    async def get_listings_command_params(self):
        return

    async def listings_refresh(self, context: Optional[CallbackContext] = None):
        if self.status == NameDurationStatus.IDLE:
            self.listings_cache = []
            self.playlist.conf['brand']['id'] = None
            self.playlist.conf['subbrands'] = []
            cmd = self.get_listings_command()
            self.playlist.conf['listings_command'] = None
            if not cmd:
                await self.get_listings_command_params()
                return
            asyncio.create_task(self.listing_refresh_1(cmd, context))

    def filter(self, title):
        if not self.listings_filter:
            return True
        else:
            title = title.lower()
            if title in self.listings_filter:
                return True
            else:
                ss = self.listings_filter.split(' ')
                for s in ss:
                    if s.lower() not in title:
                        return False
                return True

    def get_listings_text(self):
        txt = ''
        for i, b in enumerate(self.listings_cache):
            if len(txt) < 3900:
                if self.filter(b['title']):
                    txt += f'\n/brand_{i} {b["title"]} ({b["id"]})'
            else:
                return txt[1:] + '\n...'
        return txt[1:] if txt else f'No Listing{" for " + self.listings_filter if self.listings_filter else ""}'

    def download_subbrand(self):
        asyncio.create_task(self.download_subbrand_1())

    async def download_subbrand_1(self):
        self.status = NameDurationStatus.DOWNLOADING
        self.sub_status = 10
        self.scheduler_job = self.navigation.scheduler.add_job(
            self.long_operation_do,
            "interval",
            id="listing_refresh",
            seconds=3,
            replace_existing=True,
            next_run_time=StatusTMessage.datenow()
        )
        pl = await self.proc.process(self.get_subbrand_command())
        if pl.rv == 0:
            self.playlist.conf['subbrands_all'] = pl.brands
            self.playlist.conf['subbrands'] = []
            self.return_msg = ''
            if pl.brands:
                await self.navigation.goto_menu(SubBrandSelectTMessage(self.navigation, playlist=self.playlist))
            else:
                self.return_msg = 'No subbrand found'
        else:
            self.return_msg = f'Error {pl.rv} downloading subbrands :tumbs_down:'
        await self.switch_to_idle()

    def slash_message_processed(self, text: str) -> bool:
        return super().slash_message_processed(text) or (
            self.status == NameDurationStatus.IDLE and self.listings_cache and (re.search(r'^/brand_([0-9]+)$', text) or re.search(r'^/brandid ([0-9a-zA-Z_\-]+)$', text)))

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, Coroutine[Any, Any, None]]:
        if self.status == NameDurationStatus.IDLE:
            if self.listings_cache:
                if (mo := re.search(r'^/brand_([0-9]+)$', text)):
                    self.playlist.conf['brand'] = self.listings_cache[int(mo.group(1))]
                    self.download_subbrand()
                elif (mo := re.search(r'^/brandid ([0-9a-zA-Z_\-]+)$', text)):
                    self.playlist.conf['brand'] = dict(
                        id=int(mo.group(1)),
                        title=mo.group(1),
                        starttime=int(datetime.now().timestamp() * 1000)
                    )
                    self.download_subbrand()
                else:
                    self.listings_filter = text.strip()
                    self.listings_changed = True
                await self.edit_or_select()
        else:
            await super().text_input(text, context)

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        upd = ''
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        await PlaylistNamingTMessage.update(self, context)
        enteridle = False
        if enteridle or self.status == NameDurationStatus.IDLE:
            if self.listings_cache:
                self.input_field = f'\U0001F53B {self.listings_filter}' if self.listings_filter else '\U0001F53B Filter Listings'
            else:
                self.input_field = 'Please Click a Button'
                if not self.playlist.conf['brand']['id'] and self.get_listings_command():
                    await self.listings_refresh()
            self.add_button(f'Name: {self.playlist.name}', self.switch_to_status, args=(NameDurationStatus.NAMING, ), new_row=True)
            self.add_button('Refresh Listings', self.listings_refresh)
            new_row = True
            if self.playlist.conf['brand']['id']:
                self.add_button('AutoUpdate: ' + ("\U00002611" if self.playlist.autoupdate else "\U00002610"), self.toggle_autoupdate)
                if self.playlist.conf['subbrands_all']:
                    self.add_button(f'{self.playlist.conf["brand"]["title"]} ({self.playlist.conf["brand"]["id"]})' + ('\U00002757' if not self.playlist.conf["subbrands"] else '\U00002714'),
                                    SubBrandSelectTMessage(self.navigation, playlist=self.playlist))
                    if self.playlist.conf["subbrands"]:
                        self.add_button(u'\U0001F501', RefreshNewPlaylistTMessage(
                                        self.navigation,
                                        user=self.proc.user,
                                        params=self.proc.params,
                                        playlist=self.playlist
                                        ), new_row=True)
                        new_row = False
            self.add_button(':cross_mark: Abort', self.navigation.goto_back, new_row=new_row)
            if self.listings_changed:
                upd = self.get_listings_text()
                self.listings_changed = False
        elif self.status == NameDurationStatus.LISTING:
            self.input_field = u'\U0001F570'
            return f'Downloading listings {"." * (self.sub_status & 0xFF)}'
        elif self.status == NameDurationStatus.DOWNLOADING:
            self.input_field = u'\U0001F570'
            return f'Downloading brand content for {self.playlist.conf["brand"]["title"]} {"." * (self.sub_status & 0xFF)}'
        if self.return_msg:
            upd = f'\n<b>{self.return_msg}</b>'
        return upd if upd else self.input_field


class MediasetPlaylistTMessage(MedRaiPlaylistTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        super().__init__(navigation, user, params, playlist, playlist_type='mediaset')

    def get_listings_command(self):
        if self.playlist.conf['listings_command']:
            return PlaylistMessage(CMD_MEDIASET_LISTINGS, **self.playlist.conf['listings_command'])
        else:
            return None

    async def get_listings_command_params(self):
        await self.navigation.goto_menu(SelectDayTMessage(self.navigation, playlist=self.playlist))

    def get_subbrand_command(self):
        return PlaylistMessage(CMD_MEDIASET_BRANDS, brand=int(self.playlist.conf['brand']['id']))


class RaiPlaylistTMessage(MedRaiPlaylistTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        super().__init__(navigation, user, params, playlist, playlist_type='rai')

    def get_listings_command(self):
        return PlaylistMessage(CMD_RAI_LISTINGS)

    def get_subbrand_command(self):
        return PlaylistMessage(CMD_RAI_CONTENTSET, brand=self.playlist.conf['brand']['id'])


class RefreshNewPlaylistTMessage(RefreshingTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None, playlist: Playlist = None) -> None:
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field=f'Refresh {playlist.name}',
            user=user,
            params=params,
            playlist=playlist)
        self.status = NameDurationStatus.UPDATING_INIT

    async def on_refresh_finish(self, pl: PlaylistMessage):
        await self.switch_to_idle()
        if pl.rv == 0:
            await self.navigation.goto_home()
            await self.navigation._menu_queue[0].list_page_of_playlists(None)

    async def on_refresh_abort(self, context: Optional[CallbackContext[BT, UD, CD, BD]] = None):
        await self.navigation.goto_back()

    async def update(self, context: Optional[CallbackContext] = None) -> Coroutine[Any, Any, str]:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        upd = await super().update(context)
        self.input_field = f'Refresh {self.playlist.name}'
        if not upd:
            upd = ''
        if self.return_msg:
            upd += f'\n{self.return_msg}'
        return upd if upd else self.input_field


class PlaylistAddTMessage(StatusTMessage):
    def __init__(self, navigation: NavigationHandler, user: User = None, params: object = None) -> None:
        super().__init__(
            navigation,
            label=self.__class__.__name__,
            input_field='Select Playlist Type',
            user=user,
            params=params)

    def update(self, _: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> str:
        self.keyboard_previous: List[List["MenuButton"]] = [[]]
        self.keyboard: List[List["MenuButton"]] = [[]]
        self.add_button('\U0001F534 YoutubeDL', YoutubeDLPlaylistTMessage(self.navigation, user=self.proc.user, params=self.proc.params))
        self.add_button('\U0001F535 Rai', RaiPlaylistTMessage(self.navigation, user=self.proc.user, params=self.proc.params))
        self.add_button('\U00002B24 Mediaset', MediasetPlaylistTMessage(self.navigation, user=self.proc.user, params=self.proc.params))
        self.add_button('\U0001F4C2 Folder', LocalFolderPlaylistTMessage(self.navigation, user=self.proc.user, params=self.proc.params))
        self.add_button(':cross_mark: Abort', self.navigation.goto_back, new_row=True)
        self.input_field = 'Select Playlist Type'
        return self.input_field
