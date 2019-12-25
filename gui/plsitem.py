from jnius import autoclass, cast
from kivy.gesture import Gesture, GestureDatabase
from kivy.graphics import Color, Ellipse, Line
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.tabbedpanel import TabbedPanelItem
from kivy.utils import platform
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu

from common.const import CMD_DEL, CMD_REFRESH, CMD_REN, CMD_SEEN
from common.playlist import Playlist, PlaylistMessage
from .gestures import lineleft, lineright
from .renamewidget import RenameWidget
from .typewidget import TypeWidget
from .updatewidget import UpdateWidget

Builder.load_string(
    '''
#:import MDIconButton kivymd.uix.button.MDIconButton
#:import MDLabel kivymd.uix.label.MDLabel
<PlsRvItem>:
    AsyncImage:
        id: id_img
        source: root.img
        size_hint: (1, .30)
    MDLabel:
        theme_text_color: "Primary"
        id: id_duration
        text: root.fotmat_duration(root.dur)
        size_hint: (1, .15)
    MDLabel:
        theme_text_color: "Primary"
        id: id_title
        text: root.title
        size_hint: (1, .55)
    MDIconButton:
        icon: "dots-vertical"
        on_release: root.open_menu()

<PlsRv>:
    viewclass: 'PlsRvItem'
    '''
)

Builder.load_string(
    '''
<PlsItem>:
    BoxLayout:
        id: id_mainbox
        MDToolbar:
            id: toolbar
            title: 'Title'
            md_bg_color: app.theme_cls.primary_color
            background_palette: "Primary"
            elevation: 10
        PlsRv:
            id: id_rv
            title: 'Playlist'
    '''
)


async def launch_link(lnk, launchconf):
    if platform == "windows":
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


class PlsRvItem(RecycleDataViewBehavior, GridLayout):
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
    cols = 4

    @staticmethod
    def simplegesture(name, point_list):
        """
            A simple helper function
        """
        g = Gesture()
        g.add_stroke(point_list)
        g.normalize()
        g.name = name
        return g

    def __init__(self, *args, **kwargs):
        super(PlsRvItem, self).__init__()
        self.gdb = GestureDatabase()

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

    def on_touch_up(self, touch):
        # touch is over, display informations, and check if it matches some
        # known gesture.
        g = PlsRvItem.simplegesture(
            '',
            list(zip(touch.ud['line'].points[::2],
                     touch.ud['line'].points[1::2]))
        )
        # gestures to my_gestures.py
        Logger.debug("gesture representation:", self.gdb.gesture_to_str(g))
        g2 = self.gdb.find(g, minscore=0.70)

        Logger.debug(g2)
        if g2:
            if g2[1] == lineright:
                Logger.debug("LR")
                self.on_lineright()
            if g2[1] == lineleft:
                self.on_lineleft()
                Logger.debug("LL")

        # erase the lines on the screen, this is a bit quick&dirty, since we
        # can have another touch event on the way...
        self.canvas.clear()

    def on_lineleft(self, *args, **kwargs):
        self.tab.on_new_del_item(self.rowid, self.title, self.index)

    def on_lineright(self, *args, **kwargs):
        await launch_link(self.item_lnk, self.launchconf)

    def on_touch_down(self, touch):
        # start collecting points in touch.ud
        # create a line to display the points
        userdata = touch.ud
        with self.canvas:
            Color(1, 1, 0)
            d = 30.
            Ellipse(pos=(touch.x - d / 2, touch.y - d / 2), size=(d, d))
            userdata['line'] = Line(points=(touch.x, touch.y))
        return True

    def on_touch_move(self, touch):
        # store points of the touch movement
        try:
            touch.ud['line'].points += [touch.x, touch.y]
            return True
        except KeyError:
            pass

    def open_menu(self):
        items = [
            dict(
                viewclass="MDMenuItem",
                text="Remove",
                callback=self.on_lineleft
            ),
            dict(
                viewclass="MDMenuItem",
                text="Play",
                callback=self.on_lineleft,
            ),
        ]
        MDDropdownMenu(items=items, width_mult=3).open(self)

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        self.index = index
        dbitem = data[index]
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


class PlsItem(TabbedPanelItem):
    playlist = ObjectProperty(None)
    client = ObjectProperty()
    confclass = ObjectProperty()
    launchconf = StringProperty('')

    def __init__(self, **kwargs):
        super(PlsItem, self).__init__(**kwargs)
        self.load_list()

    async def play_pls(self):
        lnk = self.client.m3u_lnk(self.pls_playlist.name)
        await launch_link(lnk, self.launchconf)

    def load_list(self):
        if self.playlist:
            self.ids.id_toolbar.right_action_items = [
                ["play", await self.play_pls()],
                ["plus", self.add_pls()],
                ["close", self.del_pls()]]
            if self.confclass:
                self.conf_w = self.confclass(
                    conf=self.playlist.conf,
                    on_conf=self.on_new_conf,
                    on_exit=self.on_new_exit,
                    client=self.client)
                self.ids.id_toolbar.left_action_items = [
                    ["update", self.update_pls()],
                    ["textbox", self.rename_pls()],
                    ["settings", self.conf_pls()]]
            else:
                self.conf_w = None
                self.ids.id_toolbar.left_action_items = [
                    ["update", self.update_pls()],
                    ["textbox", self.rename_pls()]]
            self.types_w = TypeWidget(
                    on_type=self.on_new_type)
            self.rename_w = RenameWidget(
                    name=self.playlist.name,
                    on_exit=self.on_new_exit,
                    on_rename=self.on_new_name)
            self.update_w = UpdateWidget(
                on_update=self.on_new_update,
                on_exit=self.on_new_exit)
            self.popup = None
            self.text = self.playlist.name
            data_rv = []
            for d in self.playlist.items:
                if not d.seen:
                    dct = vars(d)
                    dct['launch'] = self.launchconf
                    dct['tab'] = self
                    data_rv.append(dct)
            self.ids.id_rv.data = data_rv
        else:
            if getattr(self.ids, "id_rv"):
                self.remove_widget(self.ids.id_rv)
            self.ids.id_toolbar.right_action_items = [
                ["plus", self.add_pls()]]
            self.text = "Click the add button"
            self.add_widget(MDLabel(text="Please add a playlist"))

    def on_new_name(self, inst, name):
        if self.playlist.rowid:
            self.client.enqueue(PlaylistMessage(cmd=CMD_REN, playlist=self.playlist.rowid, to=name), self.on_new_name_result)
        else:
            self.on_new_name_result(self.client, None, name)

    async def on_new_name_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.msg))
            else:
                received = received.name
        if isinstance(received, str):
            self.playlist.name = received
            toast("New playlist name "+received)
            self.text = received

    def set_playlist(self, p):
        self.playlist = p
        self.load_list()

    async def on_new_update_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv == 0:
            self.set_playlist(received.playlist)
        else:
            toast("[E %d] %s" % (received.rv, received.msg))

    async def on_new_del_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.msg))
            else:
                received = self.playlist.name
        if isinstance(received, str):
            toast("Playlist %s removed" % received)
            self.parent.remove_widget(self)

    async def on_new_del_item_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.msg))
            else:
                received = received.index
        if isinstance(received, int):
            it = self.ids.id_rv.data.pop(received)
            toast("%s removed" % it["title"])

    def on_new_exit(self, inst):
        if self.popup:
            self.popup.dismiss()

    def on_new_update(self, inst, df, dt):
        self.client.enqueue(PlaylistMessage(cmd=CMD_REFRESH, playlist=self.playlist), self.on_new_update_result)

    def on_new_conf(self, inst, conf):
        self.playlist.conf = conf
        toast("Please update to save new config")

    def on_new_del_item(self, rowid, title, index):
        if rowid:
            self.client.enqueue(PlaylistMessage(cmd=CMD_SEEN, playlistitem=rowid, seen=1, index=index), self.on_new_del_item_result)
        else:
            self.on_new_del_item_result(self.client, None, index)

    def on_new_del(self, but, inst):
        if but == "Yes":
            if self.playlist.rowid:
                self.client.enqueue(PlaylistMessage(cmd=CMD_DEL, playlist=self.playlist.rowid), self.on_new_del_result)
            else:
                self.on_new_del_result(self.client, None, self.playlist.name)

    def on_new_type(self, inst, types, confclass):
        if type != TypeWidget.ABORT:
            tab = PlsItem(
                playlist=Playlist(type=types),
                client=self.client,
                confclass=confclass)
            self.parent.add_widget(tab)
            self.parent.switch_to(tab, True)

    def update_pls(self):
        self.popup = Popup(content=self.update_w, auto_dismiss=True, title='Update')
        self.popup.open()

    def add_pls(self):
        self.popup = Popup(content=self.type_w, auto_dismiss=True, title='Type')
        self.popup.open()

    def conf_pls(self):
        self.popup = Popup(content=self.conf_w, auto_dismiss=True, title='Conf')
        self.popup.open()

    def del_pls(self):
        dialog = MDDialog(
            title="Delete confirmation",
            size_hint=(0.8, 0.3),
            text_button_ok="Yes",
            text="Are you sure?",
            text_button_cancel="No",
            events_callback=self.on_new_del,
        )
        dialog.open()

    def rename_pls(self):
        self.popup = Popup(content=self.rename_w, auto_dismiss=True, title='Update')
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
