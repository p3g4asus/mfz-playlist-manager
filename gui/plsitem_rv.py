from functools import partial

from jnius import autoclass, cast
from kivy.gesture import Gesture, GestureDatabase
from kivy.graphics import Color, Ellipse, Line
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.utils import platform
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.card import MDCardPost
from kivymd.uix.dialog import MDDialog
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.tab import MDTabsBase

from common.const import CMD_DEL, CMD_REFRESH, CMD_REN, CMD_SEEN
from common.playlist import PlaylistMessage
from common.timer import Timer

from .gestures import lineleft, lineright
from .renamewidget import RenameWidget
from .updatewidget import UpdateWidget

Builder.load_string(
    '''
#:import MDIconButton kivymd.uix.button.MDIconButton
#:import MDCardPost kivymd.uix.card.MDCardPost
<PlsRvItem>:
    source: root.img
    tile_text: root.format_duration(root.dur)
    tile_font_style: "H5"
    text_post: root.title + ' (' + root.uid + ')'
    with_image: root.img is not None and len(root.img)
    swipe: True
    buttons: ["play", "delete"]

<PlsRv>:
    viewclass: 'PlsRvItem'
    '''
)


#             md_bg_color: app.theme_cls.primary_color
#             background_palette: "Primary"
#             elevation: 10

Builder.load_string(
    '''
<PlsItem>:
    id: id_mainbox
    orientation: 'vertical'
    PlsRv:
        id: id_rv
        title: 'Playlist'
    '''
)


async def launch_link(lnk, launchconf):
    if platform == "win":
        if not launchconf:
            toast("Please configure video player path")
        else:
            import asyncio
            await asyncio.create_subprocess_shell(
                launchconf, lnk)
    else:
        Intent = autoclass('android.content.Intent')
        Uri = autoclass('android.net.Uri')
        u = Uri.parse(lnk)
        intent = Intent(Intent.ACTION_VIEW, u)
        intent.setDataAndType(u, "video/*")
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        currentActivity = cast('android.app.Activity', PythonActivity.mActivity)
        currentActivity.startActivity(intent)
        # PythonActivity.mActivity.startActivity(intent)


class PlsRvItem(RecycleDataViewBehavior, MDCardPost):
    ''' Add selection support to the Label '''
    index = None
    img = StringProperty('')
    dur = NumericProperty(0)
    title = StringProperty('')
    link = StringProperty('')
    launch = StringProperty()
    uid = StringProperty()
    rowid = NumericProperty(0)
    tab = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super(PlsRvItem, self).__init__()
        self.callback = self.process_button_click

    def process_button_click(self, value):
        if value and isinstance(value, str):
            if value == "play":
                self.on_lineright()
                return
        self.on_lineleft()

    def format_duration(self, dur):
        h = dur // 3600
        s = ''
        if h > 0:
            s = '%d:' % (h, )
        dur -= h * 3600
        m = dur // 60
        if len(s):
            s += '%02d' % (m, )
        else:
            s += '%d' % (m, )
        dur -= m * 60
        return s + (':%02d' % (dur, ))

    def on_lineleft(self, *args, **kwargs):
        self.tab.on_new_del_item(self.rowid, self.title, self.index)

    def on_lineright(self, *args, **kwargs):
        Timer(1, partial(launch_link, self.link, self.launch))

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        self.index = index
        dbitem = data[index]
        Logger.debug("PlsItem: r_v_a = %s" % str(dbitem))
        self.rowid = dbitem['rowid']
        self.uid = dbitem['uid']
        self.link = dbitem['link']
        self.title = dbitem['title']
        self.img = dbitem['img']
        self.dur = dbitem['dur']
        self.launch = dbitem['launch']
        self.tab = dbitem['tab']
        return super(PlsRvItem, self).refresh_view_attrs(
            rv, index, data)


class PlsRv(RecycleView):
    pass


class PlsItem(BoxLayout, MDTabsBase):
    client = ObjectProperty()
    confclass = ObjectProperty()
    manager = ObjectProperty()
    launchconf = StringProperty('')

    def __init__(self, playlist=None, **kwargs):
        self.playlist = playlist
        super(PlsItem, self).__init__(**kwargs)
        self.popup = None
        self.load_list()

    def play_pls(self):
        lnk = self.client.m3u_lnk(self.pls_playlist.name)
        Timer(1, partial(launch_link, lnk, self.launchconf))

    def load_list(self):
        Logger.debug("Loading list in tab: %s" % str(self.playlist))
        if self.playlist:
            self.text = self.playlist.name
            data_rv = []
            for d in self.playlist.items:
                if not d.seen:
                    dct = vars(d)
                    dct['launch'] = self.launchconf
                    dct['tab'] = self
                    Logger.debug("Adding %s" % str(dct))
                    data_rv.append(dct)
            del self.ids.id_rv.data[:]
            self.ids.id_rv.data.extend(data_rv)
            self.ids.id_rv.refresh_from_data()

    def on_new_name(self, inst, name):
        self.on_new_exit(None)
        if self.playlist.rowid:
            self.client.enqueue(PlaylistMessage(cmd=CMD_REN, playlist=self.playlist.rowid, to=name), self.on_new_name_result)
        else:
            self.on_new_name_result(self.client, None, name)

    async def on_new_name_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
            else:
                received = received.name
        if isinstance(received, str):
            self.playlist.name = received
            toast("New playlist name " + received)
            self.text = received

    def set_playlist(self, p):
        self.playlist = p
        self.load_list()

    async def on_new_update_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv == 0:
            Logger.debug("PlsItem: Sent PL: %s Received PL: %s" % (str(sent.playlist), str(received.playlist)))
            self.set_playlist(received.playlist)
        else:
            toast("[E %d] %s" % (received.rv, received.err))

    async def on_new_del_result(self, client, sent, received, tabs=None):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
            else:
                received = self.playlist.name
        if isinstance(received, str):
            toast("Playlist %s removed" % received)
            if tabs:
                tabs.remove_widget(self)

    async def on_new_del_item_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
            else:
                received = received.index
        if isinstance(received, int):
            it = self.ids.id_rv.data.pop(received)
            Snackbar(
                text="%s removed" % it["title"],
                button_text="Undo",
                button_callback=partial(self.on_new_del_item_undo,
                                        removed_item=dict(item=it, index=received)),
            ).show()

    async def on_new_del_item_undo_result(self, client, sent, received, removed_item=None):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
            else:
                received = removed_item
        if isinstance(received, dict):
            self.ids.id_rv.data.insert(received['index'], received['item'])
            toast('%s restored' % received['item']['title'])

    def on_new_del_item_undo(self, *args, **kwargs):
        removed_item = kwargs['removed_item']
        rowid = removed_item['item']['rowid']
        if rowid:
            self.client.enqueue(
                PlaylistMessage(cmd=CMD_SEEN, playlistitem=rowid, seen=0),
                partial(self.on_new_del_item_undo_result, removed_item=removed_item))
        else:
            self.on_new_del_item_undo_result(self.client, None, removed_item, removed_item=removed_item)

    def on_new_exit(self, inst):
        if self.popup:
            self.popup.dismiss()
            self.popup = None

    def on_new_update(self, inst, df, dt):
        self.on_new_exit(None)
        self.client.enqueue(PlaylistMessage(
            cmd=CMD_REFRESH,
            playlist=self.playlist,
            datefrom=int(df.timestamp() * 1000),
            dateto=int(dt.timestamp() * 1000)), self.on_new_update_result)

    def on_new_conf(self, inst, conf):
        self.on_new_exit(None)
        self.playlist.conf = conf
        toast("Please update to save new config")

    def on_new_del_item(self, rowid, title, index):
        if rowid:
            self.client.enqueue(PlaylistMessage(cmd=CMD_SEEN, playlistitem=rowid, seen=1, index=index), self.on_new_del_item_result)
        else:
            self.on_new_del_item_result(self.client, None, index)

    def on_new_del(self, but, inst, tabs=None):
        if but == "Yes":
            if self.playlist.rowid:
                self.client.enqueue(
                    PlaylistMessage(cmd=CMD_DEL, playlist=self.playlist.rowid),
                    partial(self.on_new_del_result, tabs=tabs))
            else:
                self.on_new_del_result(self.client, None, self.playlist.name, tabs=tabs)

    def update_pls(self):
        update_w = UpdateWidget(
            on_update=self.on_new_update,
            on_exit=self.on_new_exit)
        self.popup = Popup(content=update_w, auto_dismiss=True, title='Update')
        self.popup.open()

    def conf_pls(self):
        if self.playlist and self.confclass:
            conf_w = self.confclass(
                startconf=self.playlist.conf,
                manager=self.manager,
                on_exit=self.on_new_exit,
                client=self.client)
            conf_w.bind(conf=self.on_new_conf)
            self.manager.add_widget(conf_w)
            self.manager.current = conf_w.name
        else:
            toast("Playlist does not need configuration")

    def del_pls(self, tabs):
        dialog = MDDialog(
            title="Delete confirmation",
            size_hint=(0.8, 0.3),
            text_button_ok="Yes",
            text="Are you sure?",
            text_button_cancel="No",
            events_callback=partial(self.on_new_del, tabs=tabs),
        )
        dialog.open()

    def rename_pls(self):
        if self.playlist:
            rename_w = RenameWidget(
                    on_exit=self.on_new_exit,
                    name=self.playlist.name,
                    on_rename=self.on_new_name)
            self.popup = Popup(content=rename_w, auto_dismiss=True, title='Update')
            self.popup.open()

# class PlsItem(TabbedPanelItem, ABC):
#     pls_name = StringProperty('')
#     pls_list = ListProperty([])
#     pls_host = StringProperty()
#     pls_port = NumericProperty(0)
#     pls_user = StringProperty()
#     pls_password = StringProperty()
#     pls_launchconf = StringProperty()
#
#     def __init__(self, **kwargs):
#         super(PlsItem, self).__init__(**kwargs)
#         if 'pls_name' in kwargs:
#             self.pls_name = kwargs['pls_name']
#             self.load_list(self.pls_name)
#         self.add_widgets(self.ids.id_mainbox)
#
#     @abstractmethod
#     def build_settings(self):
#         pass
#
#     def load_list(self, name):
#         pass
#
#     @abstractmethod
#     def add_widgets(self, mainbox):
#         pass
