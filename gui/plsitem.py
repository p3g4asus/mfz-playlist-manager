from datetime import datetime
from functools import partial

from jnius import autoclass, cast
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.utils import platform
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.card import MDCardPost
from kivymd.uix.dialog import MDDialog, MDInputDialog
from kivymd.uix.imagelist import SmartTileWithLabel
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.tab import MDTabsBase

from common.const import CMD_DEL, CMD_REFRESH, CMD_REN, CMD_SEEN
from common.playlist import PlaylistMessage
from common.timer import Timer

from .updatewidget import UpdateWidget


# <PlsRvItem>:
#     source: root.img
#     tile_text: root.format_duration(root.dur)
#     tile_font_style: "H5"
#     text_post: root.title + ' (' + root.uid + ')'
#     with_image: root.img is not None and len(root.img)
#     swipe: True
#     buttons: ["play", "delete"]

Builder.load_string(
    '''
#:import MDIconButton kivymd.uix.button.MDIconButton
#:import MDCardPost kivymd.uix.card.MDCardPost
<PlsRvItem>:
    path_to_avatar: root.img
    source: root.img
    name_data: 'Uid: ' + root.uid + '\\nDate: '+root.datepub
    tile_text: root.format_duration(root.dur)
    tile_font_style: "H6"
    text_post: 'Date: '+ root.datepub + '\\n' + root.title + ' (' + root.uid + ')'
    swipe: True
    buttons: ["play", "delete"]
    with_image: root.img is not None and len(root.img)
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
    ScrollView:
        id: scroll
        size_hint: 1, 1
        do_scroll_x: False

        GridLayout:
            id: id_grid_card
            cols: 1
            spacing: dp(10)
            padding: dp(5)
            size_hint_y: None
            height: self.minimum_height
    '''
)


async def launch_link(lnk, launchconf):
    if platform == "win":
        if not launchconf:
            toast("Please configure video player path")
        else:
            Logger.info("Launching %s %s" % (launchconf, lnk))
            import asyncio
            await asyncio.create_subprocess_exec(
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


class PlsRvItem(MDCardPost):
    ''' Add selection support to the Label '''
    img = StringProperty('')
    dur = NumericProperty(0)
    title = StringProperty('')
    link = StringProperty('')
    launch = StringProperty()
    uid = StringProperty()
    rowid = ObjectProperty()
    playlist = ObjectProperty()
    datepub = ObjectProperty()
    tab = ObjectProperty()
    conf = ObjectProperty(None)
    seen = ObjectProperty(None)

    def __init__(self, *args, **kwargs):
        super(PlsRvItem, self).__init__(
            callback=self.process_button_click,
            **kwargs)
        sz = dp(150)
        self.card_size[1] = sz
        self.ids.root_box.children[0].card_size[1] = sz
        for i in self.ids.root_box.children[0].children:
            if isinstance(i, SmartTileWithLabel):
                i.allow_stretch = True
                i.keep_ratio = True

    def process_button_click(self, inst, value):
        ids = self.ids.root_box.children[0].ids
        Logger.debug("S1 %s S2 %s S21 %s S22 %s S221 %s" % (
            str(ids.id_c1.size),
            str(ids.id_c2.size),
            str(ids.id_c21.size),
            str(ids.id_c22.size),
            str(ids.box_buttons.size)
        ))
        if value and isinstance(value, list):
            self.on_lineright()
            return
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
        self.tab.on_new_del_item(self)

    def on_lineright(self, *args, **kwargs):
        Timer(1, partial(launch_link, self.link, self.launch))


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
        lnk = self.client.m3u_lnk(self.playlist.name)
        Timer(1, partial(launch_link, lnk, self.launchconf))

    def load_list(self):
        Logger.debug("Loading list in tab: %s" % str(self.playlist))
        if self.playlist:
            self.text = self.playlist.name
            self.ids.id_grid_card.clear_widgets()
            if not self.playlist.items:
                self.ids.id_grid_card.add_widget(PlsRvItem(**{
                       'rowid': None,
                       'uid': 'F309989201002401',
                       'link': 'https://link.theplatform.eu/s/PR1GhC/media/0UrkkBgkTWSv',
                       'title': 'Puntata del 22 dicembre',
                       'playlist': None,
                       'img': 'https://static2.mediasetplay.mediaset.it/Mediaset_Italia_Production_-_Main/1021/416/F309989201002401-3-keyframe-poster-1280x720.jpg',
                       'datepub': '2019-12-22 21:10:00.000000',
                       'conf': {'subbrand': 100003082, 'brand': 100002223},
                       'dur': 11877, 'seen': 0,
                       'launch': r'C:\/Program Files (x86)/VideoLAN/VLC/vlc.exe',
                       'tab': self}))
            for d in self.playlist.items:
                if not d.seen:
                    dct = dict(vars(d))
                    dct['launch'] = self.launchconf
                    dct['tab'] = self
                    Logger.debug("Adding %s" % str(dct))
                    self.ids.id_grid_card.add_widget(PlsRvItem(**dct))

    def on_new_name(self, text, inst):
        if text == "OK":
            if self.playlist.rowid:
                self.client.enqueue(PlaylistMessage(cmd=CMD_REN, playlist=self.playlist.rowid, to=inst.text_field.text), self.on_new_name_result)
            else:
                Timer(1, partial(self.on_new_name_result, self.client, None, inst.text_field.text))

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
        if received is None:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
            else:
                received = received.index
        if isinstance(received, int):
            w = self.ids.id_grid_card.children[received]
            self.ids.id_grid_card.remove_widget(w)
            Snackbar(
                text="%s removed" % w.title,
                button_text="Undo",
                button_callback=partial(self.on_new_del_item_undo,
                                        removed_item=dict(widget=w, index=received)),
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
            self.ids.id_grid_card.add_widget(received['widget'], index=received['index'])
            toast('%s restored' % received['widget'].title)

    def on_new_del_item_undo(self, *args, **kwargs):
        removed_item = kwargs['removed_item']
        rowid = removed_item['widget'].rowid
        if rowid:
            self.client.enqueue(
                PlaylistMessage(cmd=CMD_SEEN, playlistitem=rowid, seen=0),
                partial(self.on_new_del_item_undo_result, removed_item=removed_item))
        else:
            Timer(1, partial(
                    self.on_new_del_item_undo_result,
                    self.client,
                    None,
                    removed_item,
                    removed_item=removed_item))

    def on_new_update(self, inst, df, dt):
        self.client.enqueue(PlaylistMessage(
            cmd=CMD_REFRESH,
            playlist=self.playlist,
            datefrom=df if isinstance(df, int) else int(df.timestamp() * 1000),
            dateto=dt if isinstance(dt, int) else int(dt.timestamp() * 1000)), self.on_new_update_result)

    def on_new_conf(self, inst, conf):
        self.playlist.conf = conf
        toast("Please update to save new config")
        self.update_pls(True)

    def on_new_del_item(self, inst):
        index = self.ids.id_grid_card.children.index(inst)
        if inst.rowid:
            self.client.enqueue(PlaylistMessage(cmd=CMD_SEEN, playlistitem=inst.rowid, seen=1, index=index), self.on_new_del_item_result)
        else:
            Timer(1, partial(self.on_new_del_item_result, self.client, None, index))

    def on_new_del(self, but, inst, tabs=None):
        if but == "Yes":
            if self.playlist.rowid:
                self.client.enqueue(
                    PlaylistMessage(cmd=CMD_DEL, playlist=self.playlist.rowid),
                    partial(self.on_new_del_result, tabs=tabs))
            else:
                self.on_new_del_result(self.client, None, self.playlist.name, tabs=tabs)

    def update_pls(self, show_date_selection):
        if show_date_selection:
            updatew = UpdateWidget(on_update=self.on_new_update)
            self.manager.add_widget(updatew)
            self.manager.current = updatew.name
        else:
            self.on_new_update(None, 0, int(datetime.now().timestamp() * 1000))

    def conf_pls(self):
        if self.playlist and self.confclass:
            Logger.debug("PlsItem: %s/%s Startconf %s %s" % (
                self.playlist.name,
                str(self.playlist.rowid),
                str(type(self.playlist.conf)),
                str(self.playlist.conf)))
            conf_w = self.confclass(
                startconf=self.playlist.conf,
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
            dialog = MDInputDialog(
                title="Playlist rename",
                size_hint=(0.8, 0.3),
                text_button_ok="OK",
                hint_text="New name",
                text_button_cancel="Cancel",
                events_callback=self.on_new_name
            )
            dialog.open()

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
