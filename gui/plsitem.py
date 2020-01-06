import traceback

from datetime import datetime
from functools import partial

from jnius import autoclass, cast
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.properties import NumericProperty, ObjectProperty, StringProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
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
<CardPostImage2>
    spacing: dp(10)
    padding: dp(5)
    orientation: 'horizontal'
    size_hint: None, None
    size: root.card_size

    SmartTileWithLabel:
        pos_hint: {'top': 1}
        source: root.source
        text: ' %s' % root.tile_text
        color: root.tile_text_color
        size_hint_y: None
        font_style: root.tile_font_style
        height: root.card_size[1]
        id: id_c1
        on_release: root.callback(root, [self, self.source])
    BoxLayout:
        orientation: 'vertical'
        id: id_c2
        size_hint_y: None
        pos_hint: {'top': 1}
        height: root.card_size[1]
        MDLabel:
            pos_hint: {'top': 1}
            text: root.text_post
            size_hint_y: None
            halign: 'justify'
            valign: 'top'
            height: int(root.card_size[1] / 150 * 110)
            id: id_c21
            text_size: self.width - 20, dp(60)
        AnchorLayout:
            pos_hint: {'top': 1}
            anchor_x: 'right'
            size_hint_y: None
            height: int(root.card_size[1] / 150 * 40)
            id: id_c22
            BoxLayout:
                pos_hint: {'top': 1}
                id: box_buttons
    '''
)

Builder.load_string(
    '''
<PlsRvItem>:
    path_to_avatar: root.img
    source: root.img
    tile_text: root.format_duration(root.dur)
    tile_font_style: "H6"
    text_post: root.format_post(root.datepub, root.title, root.uid)
    swipe: True
    buttons: ["play", "delete"]
    with_image: True
    card_image_class: root.mycls
    ysize: 150

<PlsItem>:
    id: id_mainbox
    orientation: 'vertical'
    PlsRv:
        id: id_rv
        title: 'Playlist'
        ysize: root.cardsize
        viewclass: 'PlsRvItem'
        RecycleBoxLayout:
            default_size: None, dp(root.cardsize)
            default_size_hint: 1, None
            size_hint_y: None
            height: self.minimum_height
            orientation: 'vertical'
    '''
)


class CardPostImage2(BoxLayout):
    source = StringProperty()
    text_post = StringProperty()
    tile_text = StringProperty("Title")
    tile_font_style = StringProperty("H5")
    tile_text_color = ListProperty([1, 1, 1, 1])
    callback = ObjectProperty(lambda *x: None)
    card_size = ListProperty((Window.width - 10, dp(150)))


#             md_bg_color: app.theme_cls.primary_color
#             background_palette: "Primary"
#             elevation: 10


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
        try:
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            u = Uri.parse(lnk)
            intent = Intent(Intent.ACTION_VIEW, u)
            intent.setDataAndType(u, "video/*")
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            currentActivity = cast('android.app.Activity', PythonActivity.mActivity)
            currentActivity.startActivity(intent)
            # PythonActivity.mActivity.startActivity(intent)
        except Exception:
            Logger.error(traceback.format_exc())


class PlsRvItem(RecycleDataViewBehavior, MDCardPost):
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
    index = NumericProperty(-1)
    ysize = NumericProperty(150)
    mycls = ObjectProperty(CardPostImage2)

    def __init__(self, *args, **kwargs):
        super(PlsRvItem, self).__init__(
            callback=self.process_button_click,
            **kwargs)
        self.on_ysize(self, self.ysize)
        for i in self.ids.root_box.children[0].children:
            if isinstance(i, SmartTileWithLabel):
                i.allow_stretch = True
                i.keep_ratio = True

    def process_button_click(self, inst, value):
        ids = self.ids.root_box.children[0].ids
        if value and isinstance(value, list):
            self.on_lineright()
            return
        if value and isinstance(value, str):
            if value == "play":
                self.on_lineright()
                return
        self.on_lineleft()

    def format_post(self, datepub, title, uid):
        return 'Date: ' + str(datepub) + '\n' + str(title) + ' (' + str(uid) + ')'

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

    def on_ysize(self, inst, sz):
        lo = dp(sz)
        self.card_size[1] = lo
        self.ids.root_box.children[0].card_size[1] = lo

    def on_lineright(self, *args, **kwargs):
        Timer(1, partial(launch_link, self.link, self.launch))

    def refresh_view_attrs(self, rv, index, dbitem):
        ''' Catch and handle the view changes '''
        Logger.debug("PlsItem: r_v_a data = %s" % str(dbitem))
        self.index = index
        Logger.debug("PlsItem: r_v_a = %s" % str(dbitem))
        self.rowid = dbitem['rowid']
        self.uid = dbitem['uid']
        self.link = dbitem['link']
        self.title = dbitem['title']
        self.conf = dbitem['conf']
        self.datepub = dbitem['datepub']
        self.playlist = dbitem['playlist']
        self.img = dbitem['img']
        self.dur = dbitem['dur']
        self.launch = dbitem['launch']
        self.seen = dbitem['seen']
        self.tab = dbitem['tab']
        self.ysize = rv.ysize
        cpm = self.ids.root_box.children[0]
        cpm.text_post = self.format_post(self.datepub, self.title, self.uid)
        cpm.tile_text = self.format_duration(self.dur)
        cpm.source = self.img
        return super(PlsRvItem, self).refresh_view_attrs(
            rv, index, dbitem)


class PlsRv(RecycleView):
    ysize = NumericProperty(150)
    pass


class PlsItem(BoxLayout, MDTabsBase):
    client = ObjectProperty()
    confclass = ObjectProperty()
    manager = ObjectProperty()
    launchconf = StringProperty('')
    cardsize = NumericProperty(150)

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
            del self.ids.id_rv.data[:]
            data = []
            if not self.playlist.items:
                data.append({
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
                       'tab': self})
            for d in self.playlist.items:
                if not d.seen:
                    dct = dict(vars(d))
                    dct['launch'] = self.launchconf
                    dct['tab'] = self
                    Logger.debug("Adding %s" % str(dct))
                    data.append(dct)
            self.ids.id_rv.data = data

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
            it = dict(data=self.ids.id_rv.data[received], index=received)
            del self.ids.id_rv.data[received]
            Snackbar(
                text="%s removed" % it["data"]["title"],
                button_text="Undo",
                button_callback=partial(self.on_new_del_item_undo,
                                        removed_item=it),
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
            self.ids.id_rv.data.insert(received["index"], received["data"])
            toast('%s restored' % received["data"]["title"])

    def on_new_del_item_undo(self, *args, **kwargs):
        removed_item = kwargs['removed_item']
        rowid = removed_item['data']["rowid"]
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
        if inst.rowid:
            self.client.enqueue(PlaylistMessage(cmd=CMD_SEEN, playlistitem=inst.rowid, seen=1, index=inst.index), self.on_new_del_item_result)
        else:
            Timer(1, partial(self.on_new_del_item_result, self.client, None, inst.index))

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
