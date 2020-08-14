import re
import traceback

from datetime import datetime
from functools import partial

from jnius import autoclass, cast
from kivy.app import App
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.utils import platform
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.tab import MDTabsBase

from common.const import CMD_DEL, CMD_IORDER, CMD_REFRESH, CMD_REN, CMD_SEEN, CMD_SORT
from common.playlist import PlaylistMessage
from common.timer import Timer

from gui.mdcardpost import SwipeToDeleteItem, ICON_IMAGE, ICON_TRASH

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
<RenameContent>
    orientation: "vertical"
    padding: dp(5)
    MDTextField:
        id: id_newname
        hint_text: "New name"
        error: True
        helper_text_mode: "on_error"
        helper_text: "At least a letter is required"
    '''
)

Builder.load_string(
    '''
#:import images_path kivymd.images_path
<PlsRvItem>:
    source: root.img if root.img else f'{images_path}kivymd_logo.png'
    tile_text: root.format_duration(root.dur) + f'    ({root.iorder})'
    tile_font_style: "H6"
    text_post: root.format_post(root.datepub, root.title, root.uuid)
    buttons: ["folder-move", "order-numeric-ascending", "delete"]
    ysize: 150

<PlsItem>:
    id: id_mainbox
    orientation: 'vertical'
    PlsRv:
        id: id_rv
        title: 'Playlist'
        ysize: root.cardsize
        cardtype: root.cardtype
        viewclass: 'PlsRvItem'
        RecycleBoxLayout:
            default_size: None, dp(root.cardsize)
            default_size_hint: 1, None
            size_hint_y: None
            height: self.minimum_height
            orientation: 'vertical'
    '''
)


class RenameContent(BoxLayout):
    button_ok = ObjectProperty()
    oldname = StringProperty()

    def __init__(self, **kwargs):
        super(RenameContent, self).__init__(**kwargs)
        self.ids.id_newname.bind(text=self.name_check)
        self.ids.id_newname.text = self.oldname

    def is_name_ok(self, name):
        return re.search(r"[A-Za-z]", name)

    def name_check(self, inst, name):
        if self.is_name_ok(name):
            if self.ids.id_newname.error:
                self.ids.id_newname.error = False
                inst.on_text(inst, name)
            if self.button_ok:
                self.button_ok.disabled = name == self.oldname
        else:
            self.button_ok.disabled = True
            if not self.ids.id_newname.error:
                self.ids.id_newname.error = True
                inst.on_text(inst, name)


class OrderContent(RenameContent):
    def __init__(self, **kwargs):
        super(OrderContent, self).__init__(**kwargs)
        self.ids.id_newname.hint_text = 'New Order'
        self.ids.id_newname.helper_text = 'Only digits are allowed here'

    def is_name_ok(self, name):
        return re.search(r"^[0-9]+$", name)

#             md_bg_color: app.theme_cls.primary_color
#             background_palette: "Primary"
#             elevation: 10


async def launch_link(lnk, launchconf):
    Logger.debug(f'lnk to launch: {lnk}')
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


def iorder_show_dialog(plsitem, uuid, plstab, *args, **kwargs):
    renc = OrderContent(oldname=str(plsitem.iorder))
    renc.button_ok = MDFlatButton(
        text="OK", disabled=True, on_release=partial(iorder_on_new, renc=renc, tab=plstab, item=plsitem)
    )
    dialog = MDDialog(
        title=f"Item Order {uuid}",
        type="custom",
        content_cls=renc,
        buttons=[
            MDRaisedButton(
                text="Cancel", on_release=partial(iorder_on_new, renc=renc, tab=plstab, item=plsitem)
            ),
            renc.button_ok,
        ]
    )
    dialog.open()


def iorder_on_new(but, renc=None, tab=None, item=None):
    if but.text == "OK":
        tab.on_new_iorder_item(item, int(renc.ids.id_newname.text))
    while but:
        but = but.parent
        if isinstance(but, MDDialog):
            but.dismiss()
            break


class PlsRvItem(RecycleDataViewBehavior, SwipeToDeleteItem):
    ''' Add selection support to the Label '''
    img = StringProperty('', allownone=True)
    dur = NumericProperty(0)
    iorder = NumericProperty(0)
    title = StringProperty('')
    link = StringProperty('')
    launch = StringProperty()
    uuid = StringProperty()
    rowid = ObjectProperty()
    playlist = ObjectProperty()
    datepub = ObjectProperty()
    tab = ObjectProperty()
    conf = ObjectProperty(None)
    seen = ObjectProperty(None, allownone=True)
    index = NumericProperty(-1)
    ysize = NumericProperty(150)

    def __init__(self, *args, **kwargs):
        super(PlsRvItem, self).__init__(**kwargs)
        self.on_ysize(self, self.ysize)

    def on_button_click(self, value):
        if value == ICON_IMAGE:
            self.on_lineright()
        elif value == "play":
            self.on_lineright()
        elif value == "order-numeric-ascending":
            iorder_show_dialog(self, self.uuid, self.tab)
        elif value == "folder-move":
            self.tab.on_new_move_item(self)
        elif value == ICON_TRASH or value == 'delete':
            self.on_lineleft()

    def format_post(self, datepub, title, uid):
        if datepub:
            itsdate = datetime.strptime(datepub, '%Y-%m-%d %H:%M:%S.%f')
            format = '%d/%m/%Y %H:%M' if itsdate.year != datetime.now().year else '%d/%m %H:%M'
            strdate = itsdate.strftime(format)
        else:
            strdate = 'N/A'
        return 'Date: ' + strdate + '\n' + str(title) + ' (' + str(uid) + ')'

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
        self.height = lo

    def on_lineright(self, *args, **kwargs):
        Timer(0, partial(launch_link, self.link, self.launch))

    def refresh_view_attrs(self, rv, index, dbitem):
        ''' Catch and handle the view changes '''
        try:
            Logger.debug("PlsItem: r_v_a data = %s" % str(dbitem))
        except Exception:
            pass
        self.index = index
        self.rowid = dbitem['rowid']
        self.uuid = dbitem['uuid']
        self.link = dbitem['link']
        self.title = dbitem['title']
        self.conf = dbitem['conf']
        self.datepub = dbitem['datepub']
        self.playlist = dbitem['playlist']
        self.img = dbitem['img']
        self.dur = dbitem['dur']
        self.iorder = dbitem['iorder']
        self.launch = dbitem['launch']
        self.seen = dbitem['seen']
        self.tab = dbitem['tab']
        self.height = rv.ysize
        if rv.cardtype == 'RESIZE':
            self.allow_stretch = True
            self.keep_ratio = True
        else:
            self.allow_stretch = None
            self.keep_ratio = None
        self.text_post = self.format_post(self.datepub, self.title, self.uuid)
        self.tile_text = self.format_duration(self.dur) + f'    ({self.iorder})'
        return super(PlsRvItem, self).refresh_view_attrs(
            rv, index, dbitem)


class PlsRv(RecycleView):
    ysize = NumericProperty(150)
    cardtype = StringProperty('RESIZE')


class PlsItem(BoxLayout, MDTabsBase):
    client = ObjectProperty()
    tabcont = ObjectProperty(None)
    confclass = ObjectProperty()
    manager = ObjectProperty()
    launchconf = StringProperty('')
    cardtype = StringProperty('RESIZE')
    cardsize = NumericProperty(150)

    def __init__(self, playlist=None, **kwargs):
        self.playlist = playlist
        super(PlsItem, self).__init__(**kwargs)
        self.popup = None
        self.load_list()

    def play_pls(self):
        lnk = self.client.m3u_lnk(self.playlist.name)
        Timer(0, partial(launch_link, lnk, self.launchconf))

    def load_list(self):
        try:
            Logger.debug("Loading list in tab: %s" % str(self.playlist))
        except Exception:
            pass
        if self.playlist:
            self.text = self.playlist.name
            del self.ids.id_rv.data[:]
            data = []
            for d in self.playlist.items:
                if not d.seen:
                    dct = dict(vars(d))
                    dct['launch'] = self.launchconf
                    dct['tab'] = self
                    dct['uuid'] = dct['uid']
                    del dct['uid']
                    try:
                        Logger.debug("Adding %s" % str(dct))
                    except Exception:
                        pass
                    data.append(dct)
            self.ids.id_rv.data = data

    def on_new_name(self, but, renc=None):
        if but.text == "OK":
            if self.playlist.rowid:
                self.client.enqueue(PlaylistMessage(
                    cmd=CMD_REN,
                    playlist=self.playlist.rowid,
                    to=renc.ids.id_newname.text), self.on_new_name_result)
            else:
                Timer(0, partial(self.on_new_name_result, self.client, None, renc.ids.id_newname.text))
        while but:
            but = but.parent
            if isinstance(but, MDDialog):
                but.dismiss()
                break

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
            try:
                Logger.debug("PlsItem: Sent PL: %s Received PL: %s" % (str(sent.playlist), str(received.playlist)))
            except Exception:
                pass
            self.set_playlist(received.playlist)
        else:
            toast("[E %d] %s" % (received.rv, received.err))
            self.tabcont.ws_dump(playlist_to_ask=self.playlist.rowid)

    async def on_new_del_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
                self.tabcont.ws_dump()
            else:
                received = self.playlist.name
        if isinstance(received, str):
            toast("Playlist %s removed" % received)
            self.tabcont.remove_widget(self)

    async def on_new_sort_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
                self.tabcont.ws_dump(playlist_to_ask=self.playlist.rowid)
            else:
                toast("Playlist %s sorted" % self.playlist.name)
                self.set_playlist(received.playlist)

    def del_item(self, index):
        del self.ids.id_rv.data[index]

    async def on_new_iorder_item_result(self, client, sent, received):
        if received is None:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
            else:
                toast("New iorder (%d) OK" % received.playlistitem['iorder'])
            self.tabcont.ws_dump(playlist_to_ask=self.playlist.rowid)

    async def on_new_del_item_result(self, client, sent, received):
        if received is None:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
                self.tabcont.ws_dump(playlist_to_ask=self.playlist.rowid)
            else:
                received = received.index
        if isinstance(received, int):
            it = dict(data=self.ids.id_rv.data[received], index=received)
            del self.ids.id_rv.data[received]
            col = App.get_running_app().theme_cls.primary_color
            sn = Snackbar(
                text="%s removed" % it["data"]["title"],
                button_text="Undo",
                button_callback=partial(self.on_new_del_item_undo,
                                        removed_item=it),
            )
            for x in sn.ids.box.children:
                if isinstance(x, MDFlatButton):
                    x.theme_text_color = "Custom"
                    x.text_color = col
                    break
            sn.show()

    async def on_new_del_item_undo_result(self, client, sent, received, removed_item=None):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
                self.tabcont.ws_dump(playlist_to_ask=self.playlist.rowid)
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
            Timer(0, partial(
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
            Timer(0, partial(self.on_new_del_item_result, self.client, None, inst.index))

    def on_new_iorder_item(self, inst, neworder):
        if inst.rowid:
            self.client.enqueue(PlaylistMessage(cmd=CMD_IORDER, playlistitem=inst.rowid, iorder=neworder), self.on_new_iorder_item_result)

    def on_new_move_item(self, inst):
        if inst.rowid and self.tabcont:
            self.tabcont.on_new_move_item(inst)

    def on_new_del(self, but):
        if but.text == 'Yes':
            if self.playlist.rowid:
                self.client.enqueue(
                    PlaylistMessage(cmd=CMD_DEL, playlist=self.playlist.rowid),
                    self.on_new_del_result)
            else:
                Timer(0, partial(self.on_new_del_result, self.client, None, self.playlist.name))
        while but:
            but = but.parent
            if isinstance(but, MDDialog):
                but.dismiss()
                break

    def on_new_sort(self, but):
        if but.text == 'Yes':
            if self.playlist.rowid:
                self.client.enqueue(
                    PlaylistMessage(cmd=CMD_SORT, playlist=self.playlist.rowid),
                    self.on_new_sort_result)
        while but:
            but = but.parent
            if isinstance(but, MDDialog):
                but.dismiss()
                break

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

    def del_pls(self):
        dialog = MDDialog(
            title="Delete confirmation",
            size_hint=(0.8, 0.3),
            text="Are you sure?",
            type="alert",
            buttons=[
                MDFlatButton(
                    text="Yes", on_release=self.on_new_del
                ),
                MDRaisedButton(
                    text="No", on_release=self.on_new_del
                ),
            ])
        dialog.open()

    def sort_pls(self):
        dialog = MDDialog(
            title="Sort confirmation",
            size_hint=(0.8, 0.3),
            text="Are you sure?",
            type="alert",
            buttons=[
                MDFlatButton(
                    text="Yes", on_release=self.on_new_sort
                ),
                MDRaisedButton(
                    text="No", on_release=self.on_new_sort
                ),
            ])
        dialog.open()

    def rename_pls(self):
        if self.playlist:
            renc = RenameContent(oldname=self.playlist.name)
            renc.button_ok = MDFlatButton(
                text="OK", disabled=True, on_release=partial(self.on_new_name, renc=renc)
            )
            dialog = MDDialog(
                title="Playlist rename",
                type="custom",
                content_cls=renc,
                buttons=[
                    MDRaisedButton(
                        text="Cancel", on_release=partial(self.on_new_name, renc=renc)
                    ),
                    renc.button_ok,
                ]
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
