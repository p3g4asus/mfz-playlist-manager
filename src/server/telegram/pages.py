from abc import abstractmethod
from datetime import timedelta
import logging
import traceback
from typing import Any, Coroutine, Dict, List, Optional, Union

from telegram_menu import BaseMessage, MenuButton
from telegram.ext._callbackcontext import CallbackContext
from telegram.ext._utils.types import BD, BT, CD, UD
from common.playlist import Playlist, PlaylistItem
from common.user import User
from server.telegram.browser import BrowserInfoMessage, BrowserListMessage
from server.telegram.message import MyNavigationHandler, NameDurationTMessage, ProcessorMessage, duration2string
from server.telegram.player import PlayerInfoMessage, PlayerListMessage


_LOGGER = logging.getLogger(__name__)


class PageGenerator(object):
    def __init__(self, user: User, params) -> None:
        self.proc = ProcessorMessage(user, params)

    @abstractmethod
    def item_convert(self, myid, navigation, **kwargs) -> NameDurationTMessage:
        return

    @abstractmethod
    async def get_items_list(self, deleted=False, **kwargs) -> List[Union[Playlist, PlaylistItem]]:
        return


class GroupOfNameDurationItems(object):

    def __init__(self):
        self.items: List[NameDurationTMessage] = []
        self.start_item = -1
        self.stop_item = -1

    def is_valid(self):
        return self.start_item >= 0 and self.stop_item >= 0

    def add_item(self, item):
        if not self.items:
            self.start_item = item.index
        self.items.append(item)
        self.stop_item = item.index

    def get_label(self):
        if self.start_item == self.stop_item:
            beginning = f'{self.start_item + 1}) {self.items[0].name}'
            if len(beginning) > 70:
                beginning = beginning[0:70] + '...'
            return f'{beginning} ({duration2string(self.items[0].secs)})'
        else:
            return f'{self.start_item + 1} - {self.stop_item + 1}'


class MultipleGroupsOfItems(object):

    def __init__(self):
        self.start_item: int = -1
        self.stop_item: int = -1
        self.next_page: MultipleGroupsOfItems = None
        self.back_page: MultipleGroupsOfItems = None
        self.groups: List[GroupOfNameDurationItems] = []
        self.first_item_index: int = -1
        self.last_item_index: int = -1

    def is_valid(self):
        return self.start_item >= 0 and self.stop_item >= 0

    def set_start_stop(self, sta: int, sto: int):
        self.start_item = sta
        self.stop_item = sto

    def set_first_last(self, sta: int, sto: int):
        self.first_item_index = sta
        self.last_item_index = sto

    def get_next_page(self):
        return self.next_page

    def add_group(self, grp):
        if not self.groups:
            self.start_item = grp.start_item
        self.stop_item = grp.stop_item
        self.groups.append(grp)

    def set_back_page(self, val):
        self.back_page = val

    def get_label(self):
        if self.start_item == self.stop_item:
            return f'{self.start_item + 1}'
        else:
            return f'{self.start_item + 1} - {self.stop_item + 1}'


class ListPagesTMessage(BaseMessage):

    def __init__(self, update_str: str, navigation: MyNavigationHandler, max_items_per_group=6, max_group_per_page=6, pagegen: PageGenerator = None, firstpage: Optional[MultipleGroupsOfItems] = None, deleted=False, input_field=None) -> None:
        super().__init__(
            navigation,
            self.__class__.__name__ + f'_{self.get_label_addition()}_' + ('00' if not firstpage else firstpage.get_label()),
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
        self.sel_players: Dict[str, PlayerInfoMessage] = None
        self.sel_browsers: Dict[str, BrowserInfoMessage] = None

    def get_label_addition(self):
        return ''

    async def put_items_in_pages(self):
        try:
            items = await self.pagegen.get_items_list(self.deleted)
            nitems = len(items)
            self.first_page = thispage = MultipleGroupsOfItems()
            if nitems:
                last_group_items = nitems % self.max_items_per_group
                ngroups = int(nitems / self.max_items_per_group) + (1 if last_group_items else 0)
                if not last_group_items:
                    last_group_items = self.max_items_per_group
                last_page_groups = ngroups % self.max_group_per_page
                npages = int(ngroups / self.max_group_per_page) + (1 if last_page_groups else 0)
                if not last_page_groups:
                    last_page_groups = self.max_group_per_page
                first_item_index = None
                last_item_index = None
                pages: List[MultipleGroupsOfItems] = []
                oldpage = None
                current_item = 0
                for i in range(npages):
                    groups_of_this_page = last_page_groups if i == npages - 1 else self.max_group_per_page
                    for j in range(groups_of_this_page):
                        items_of_this_group = last_group_items if i == npages - 1 and j == groups_of_this_page - 1 else self.max_items_per_group
                        group = GroupOfNameDurationItems()
                        for _ in range(items_of_this_group):
                            item = self.pagegen.item_convert(items[current_item].rowid, self.navigation)
                            group.add_item(item)
                            current_item += 1
                            if current_item == 1:
                                first_item_index = item.index
                            last_item_index = item.index
                        thispage.add_group(group)
                    thispage.set_back_page(oldpage)
                    oldpage = thispage
                    pages.append(thispage)
                    thispage = oldpage.next_page = MultipleGroupsOfItems()
                for p in pages:
                    p.set_first_last(first_item_index, last_item_index)
        except Exception:
            _LOGGER.error(traceback.format_exc())

    async def goto_index(self, index, context=None):
        basepage = self.first_page
        while basepage.back_page:
            basepage = basepage.back_page
        current = 0
        while basepage:
            for g in basepage.groups:
                for _ in g.items:
                    if current == index:
                        await self.goto_group((g,), context)
                        return
                    current += 1
            basepage = basepage.next_page

    async def text_input(self, text: str, context: Optional[CallbackContext[BT, UD, CD, BD]] = None) -> Coroutine[Any, Any, None]:
        try:
            val = int(text.strip())
        except Exception:
            val = -1
        if val > 0:
            await self.goto_index(val - 1, context)

    def slash_message_processed(self, text: str) -> bool:
        return False

    async def goto_page(self, args, context=None, sync: bool = False):
        page, = args
        self.first_page = page
        await self.navigation.goto_menu(self, context, add_if_present=False, sync=sync)

    async def goto_group(self, args, context=None):
        group: GroupOfNameDurationItems = args[0]
        for item in group.items:
            try:
                await item.send(context)
            except Exception:
                _LOGGER.error(f'goto_group error {traceback.format_exc()}')
        self.is_alive()

    def soft_refresh(self):
        basepage = self.first_page
        while basepage.back_page:
            basepage = basepage.back_page
        while basepage:
            for g in basepage.groups:
                for it in g.items:
                    if not it.refresh_from_cache():
                        self.first_page = None
                        return False
            basepage = basepage.next_page
        return True

    async def update(self, context: Optional[CallbackContext] = None) -> str:
        if not self.first_page or not self.soft_refresh():
            await self.put_items_in_pages()
        self.keyboard: List[List["MenuButton"]] = [[]]
        if self.first_page:
            self.input_field = f'{self.first_page.first_item_index + 1} - {self.first_page.last_item_index + 1}'\
                if self.first_page.last_item_index != self.first_page.first_item_index else\
                (f'{self.first_page.first_item_index + 1}' if self.first_page.groups else u'\U00002205')
            for grp in self.first_page.groups:
                label = grp.get_label()
                self.add_button(label, self.goto_group, args=(grp,))
            new_row = True
            if self.first_page.back_page:
                self.add_button(f':arrow_left: {self.first_page.back_page.get_label()}', self.goto_page, args=(self.first_page.back_page, ), new_row=new_row)
                new_row = False
            if self.first_page.next_page and self.first_page.next_page.is_valid():
                self.add_button(f'{self.first_page.next_page.get_label()} :arrow_right:', self.goto_page, args=(self.first_page.next_page, ), new_row=new_row)
        else:
            self.input_field = u'\U00002205'
        if self.sel_players is None:
            self.sel_players = PlayerListMessage.user_conf_field_to_remotes_dict(
                self.navigation,
                self.pagegen.proc,
                True)
        if self.sel_browsers is None:
            self.sel_browsers = BrowserListMessage.user_conf_field_to_remotes_dict(
                self.navigation,
                self.pagegen.proc,
                True)
        new_row = True
        for pi, pim in self.sel_players.items():
            self.add_button(label=u"\U0001F3A6 " + pi, callback=pim, new_row=new_row)
            new_row = False
        new_row = True
        for pi, pim in self.sel_browsers.items():
            self.add_button(label=u"\U0001F4D9 " + pi, callback=pim, new_row=new_row)
            new_row = False
        return self.update_str
