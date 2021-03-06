"""
Config Example
==============
This file contains a simple example of how the use the Kivy settings classes in
a real app. It allows the user to change the caption and font_size of the label
and stores these changes.
When the user next runs the programs, their changes are restored.
"""

import asyncio
import json
import os
import socket
import traceback
from contextlib import closing
from datetime import datetime
from functools import partial
from os.path import expanduser, join, dirname, exists

from kivy.core.window import Window
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import ObjectProperty, StringProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.settings import SettingsWithSpinner
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.list import OneLineAvatarListItem
from kivymd.uix.tab import MDTabs

from common.const import CMD_DUMP, PORT_OSC_CONST, CMD_MOVE
from common.playlist import PlaylistMessage, Playlist
from common.timer import Timer
from common.utils import asyncio_graceful_shutdown

from . import __prog__, __version__
from .client import PlsClient
from .playerpathwidget import PlayerPathWidget
from .plsitem import PlsItem, iorder_show_dialog
from .settingbuttons import SettingButtons
from .settingpassword import SettingPassword
from .typewidget import TypeWidget
from .playlistselect import PlaylistSelectWidget

if platform == "android":
    import certifi
    # Here's all the magic !
    os.environ['SSL_CERT_FILE'] = certifi.where()
    from android.permissions import request_permissions, Permission
    request_permissions([Permission.INTERNET, Permission.READ_EXTERNAL_STORAGE,
                         Permission.WRITE_EXTERNAL_STORAGE])


KV = \
    '''
#:import MDToolbar kivymd.uix.toolbar.MDToolbar
#:import IconLeftWidget kivymd.uix.list.IconLeftWidget
<NavigationItem>
    theme_text_color: 'Custom'
    divider: None

    IconLeftWidget:
        icon: root.icon


<ContentNavigationDrawer>

    BoxLayout:
        orientation: 'vertical'

        FloatLayout:
            size_hint_y: None
            height: "200dp"

            canvas:
                Color:
                    rgba: app.theme_cls.primary_color
                Rectangle:
                    pos: self.pos
                    size: self.size

            BoxLayout:
                id: top_box
                size_hint_y: None
                height: "200dp"
                #padding: "10dp"
                x: root.parent.x
                pos_hint: {"top": 1}

                FitImage:
                    source: root.image_path

            MDIconButton:
                icon: "close"
                x: root.parent.x + dp(10)
                pos_hint: {"top": 1}
                on_release: root.parent.set_state("toggle")

            MDLabel:
                markup: True
                text: "[b]" + app.title + "[/b]\\nVersion: " + app.format_version()
                #pos_hint: {'center_y': .5}
                x: root.parent.x + dp(10)
                y: root.height - top_box.height + dp(10)
                size_hint_y: None
                height: self.texture_size[1]

        ScrollView:
            pos_hint: {"top": 1}

            GridLayout:
                id: box_item
                cols: 1
                size_hint_y: None
                height: self.minimum_height


Screen:
    name: 'full'
    NavigationLayout:

        ScreenManager:
            id: id_screen_manager
            Screen:
                name: 'main'
                BoxLayout:
                    orientation: 'vertical'

                    MDToolbar:
                        id: id_toolbar
                        title: app.title
                        md_bg_color: app.theme_cls.primary_color
                        left_action_items: [["menu", lambda x: nav_drawer.set_state("toggle")]]
                        right_action_items: [["plus", id_tabcont.add_pls], ["delete", id_tabcont.del_pls], ["dots-vertical", app.open_menu]]

                    MyTabs:
                        manager: root.ids.id_screen_manager
                        id: id_tabcont


        MDNavigationDrawer:
            id: nav_drawer

            ContentNavigationDrawer:
                id: content_drawer
    '''


class ContentNavigationDrawer(BoxLayout):
    image_path = StringProperty()
    pass


class NavigationItem(OneLineAvatarListItem):
    icon = StringProperty()


class MyTabs(MDTabs):
    client = ObjectProperty()
    launchconf = StringProperty()
    cardsize = NumericProperty()
    cardtype = StringProperty()
    useri = NumericProperty()
    sel_tab = NumericProperty()
    manager = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super(MyTabs, self).__init__(*args, **kwargs)
        self.tab_list = []
        self.current_tab = None

    def on_cardtype(self, inst, val):
        for t in self.tab_list:
            t.cardtype = val

    def remove_widget(self, w, *args, **kwargs):
        if isinstance(w, PlsItem):
            super(MyTabs, self).remove_widget(w.tab_label)
            idx = -3
            try:
                idx = self.tab_list.index(w)
                self.tab_list.remove(w)
            except ValueError:
                Logger.error(traceback.format_exc())
            if len(self.tab_list) == 0:
                self.dispatch("on_tab_switch", None, None, None)
                idx = -2
            elif idx > 0:
                idx = idx - 1
            elif idx == 0:
                idx = 0
            if idx >= 0:
                self.select_tab(idx, is_rowid=False)

    def clear_widgets(self):
        for w in self.tab_list:
            self.remove_widget(w)

    def add_widget(self, tab, *args, **kwargs):
        super(MyTabs, self).add_widget(tab, *args, **kwargs)
        if isinstance(tab, PlsItem):
            self.tab_list.append(tab)
            Logger.debug("Gui: Adding tab len = %d" % len(self.tab_list))
            self.select_tab(tab)

    def on_tab_switch(self, instance_tab, instance_tab_label, text):
        Logger.debug("On tab switch to %s" % str(text))
        self.current_tab = instance_tab
        Logger.debug("Gui: Currenttab = %s" % str(instance_tab))

    def add_pls(self, *args, **kwargs):
        if self.client.is_logged_in():
            typew = TypeWidget(on_type=self.on_new_type)
            self.manager.add_widget(typew)
            self.manager.current = typew.name
        else:
            toast("Please login before adding")

    def update_pls(self, *args, **kwargs):
        if self.current_tab:
            self.current_tab.update_pls(True)
        else:
            toast("Please select a playlist tab")

    def update_fast_pls(self, *args, **kwargs):
        if self.current_tab:
            self.current_tab.update_pls(False)
        else:
            toast("Please select a playlist tab")

    def conf_pls(self, *args, **kwargs):
        if self.current_tab:
            self.current_tab.conf_pls()
        else:
            toast("Please select a playlist tab")

    def play_pls(self, *args, **kwargs):
        if self.current_tab:
            self.current_tab.play_pls()
        else:
            toast("Please select a playlist tab")

    def del_pls(self, *args, **kwargs):
        if self.current_tab:
            self.current_tab.del_pls()
        else:
            toast("Please select a playlist tab")

    def rename_pls(self, *args, **kwargs):
        if self.current_tab:
            self.current_tab.rename_pls()
        else:
            toast("Please select a playlist tab")

    def sort_pls(self, *args, **kwargs):
        if self.current_tab:
            self.current_tab.sort_pls()
        else:
            toast("Please select a playlist tab")

    def on_new_move_item(self, item):
        items = dict()
        for t in self.tab_list:
            items[t.playlist.name] = t
        selectp = PlaylistSelectWidget(on_playlist=partial(self.on_new_move_item_dest, delitem=item), items=items)
        self.manager.add_widget(selectp)
        self.manager.current = selectp.name

    def on_new_move_item_dest(self, inst, plname, pltab, delitem=None):
        if delitem and pltab:
            self.client.enqueue(PlaylistMessage(
                cmd=CMD_MOVE,
                playlistitem=delitem.rowid,
                playlist=pltab.playlist),
                partial(self.on_new_move_item_dest_result, delitem=delitem, totab=pltab))

    async def on_new_move_item_dest_result(self, client, sent, received, delitem=None, totab=None):
        if not received:
            toast("Timeout error waiting for server response")
        elif isinstance(received, PlaylistMessage):
            if received.rv:
                toast("[E %d] %s" % (received.rv, received.err))
            elif delitem and totab:
                delitem.tab.del_item(delitem.index)
                totab.set_playlist(received.playlist)
                for di in received.playlist.items:
                    if di.rowid == delitem.rowid:
                        break
                toast(f"{delitem.title} moved to {totab.playlist.name}")
                if di and di.rowid == delitem.rowid:
                    iorder_show_dialog(di, di.uid, totab)

    def select_tab(self, tab, is_rowid=False):
        for idx, t in enumerate(self.tab_list):
            if tab == t or (idx == tab and not is_rowid) or (t.playlist.rowid == tab and is_rowid):
                self.carousel.index = idx
                t.tab_label.state = "down"
                t.tab_label.on_release()

    def on_new_type(self, inst, name, types, confclass):
        if types != TypeWidget.ABORT:
            pl = Playlist(type=types, name=name, useri=self.useri, conf=dict())
            tab = PlsItem(
                playlist=pl,
                tabcont=self,
                client=self.client,
                cardsize=self.cardsize,
                manager=self.manager,
                launchconf=self.launchconf,
                confclass=confclass,
                cardtype=self.cardtype)
            self.add_widget(tab)
            tab.conf_pls()

    def ws_dump(self, playlist_to_ask=None, fast_videoidx=None, multicmd=0):
        if fast_videoidx is None:
            multicmd = 0
        elif not multicmd:
            multicmd = int(datetime.now().timestamp() * 1000)
        self.client.enqueue(PlaylistMessage(cmd=CMD_DUMP, multicmd=multicmd, playlist=playlist_to_ask, useri=self.useri, fast_videoidx=fast_videoidx), self.on_ws_dump)

    async def on_ws_dump(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv:
            toast("[E %d] %s" % (received.rv, received.err))
        else:
            self.fill_PlsListRV(
                received.f('playlists'),
                sent.f('playlist'),
                fast_videoidx=received.f('fast_videoidx'),
                fast_videostep=received.f('fast_videostep'),
                multicmd=received.f('multicmd'))

    def fill_PlsListRV(self, playlists, playlist_asked=None, fast_videoidx=None, fast_videostep=None, multicmd=0):
        Logger.debug(f'Dump OK: filling {fast_videoidx}/{fast_videostep}')
        d = self.tab_list
        processed = dict()
        removelist = []
        no_items = True
        for t in d:
            try:
                idx = playlists.index(t.playlist)
                processed[str(idx)] = True
                Logger.debug(f'Playlist {playlists[idx].name} nitems={len(playlists[idx].items)}')
                if playlists[idx].items or not fast_videostep or fast_videoidx == 0:
                    t.set_playlist(playlists[idx], fast_videoidx=fast_videoidx, fast_videostep=fast_videostep)
                if fast_videostep is not None and len(playlists[idx].items) == fast_videostep:
                    no_items = False
            except ValueError:
                if t.playlist.rowid is not None and playlist_asked is None:
                    removelist.append(t)
        for r in removelist:
            self.remove_widget(r)
        for x in range(len(playlists)):
            if str(x) not in processed:
                self.add_widget(PlsItem(
                    playlist=playlists[x],
                    fast_videoidx=fast_videoidx,
                    fast_videostep=fast_videostep,
                    manager=self.manager,
                    tabcont=self,
                    cardsize=self.cardsize,
                    launchconf=self.launchconf,
                    client=self.client,
                    confclass=TypeWidget.type2class(playlists[x].type),
                    cardtype=self.cardtype
                ))
                if fast_videostep is not None and len(playlists[x].items) == fast_videostep:
                    no_items = False
        if self.sel_tab >= 0:
            Logger.debug(f'Setting sel_tab {self.sel_tab}')
            self.select_tab(self.sel_tab, is_rowid=True)
            self.sel_tab = -1
        if not no_items:
            Logger.debug(f'Calling dump again with idx = {fast_videoidx + fast_videostep}')
            self.ws_dump(playlist_to_ask=playlist_asked, fast_videoidx=fast_videoidx + fast_videostep, multicmd=multicmd)
        elif fast_videostep is not None:
            toast('Load Playlists Ended OK')


def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


class MainApp(MDApp):
    playlist_types = dict()

    @staticmethod
    def db_dir():
        if platform == "android":
            from jnius import autoclass
            Environment = autoclass('android.os.Environment')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            ctx = PythonActivity.mActivity
            strg = ctx.getExternalFilesDirs(None)
            dest = strg[0]
            for f in strg:
                if Environment.isExternalStorageRemovable(f):
                    dest = f
                    break
            pth = dest.getAbsolutePath()
        else:
            home = expanduser("~")
            pth = join(home, '.kivypls')
        if not exists(pth):
            os.mkdir(pth)
        return pth

    def _get_user_data_dir(self):
        # Determine and return the user_data_dir.
        if platform == 'android':
            from jnius import autoclass, cast
            Environment = autoclass('android.os.Environment')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            ctx = PythonActivity.mActivity
            strg = ctx.getExternalFilesDirs(None)
            if strg:
                dest = strg[0]
                for f in strg:
                    if Environment.isExternalStorageRemovable(f):
                        dest = f
                        break
                data_dir = dest.getAbsolutePath()
            else:
                file_p = cast('java.io.File', ctx.getFilesDir())
                data_dir = file_p.getAbsolutePath()
            if not exists(data_dir):
                os.mkdir(data_dir)
            return data_dir
        else:
            super(MainApp, self)._get_user_data_dir()

    def format_version(self):
        return "%d.%d.%d" % __version__

    def open_menu(self, *args, **kwargs):
        items = [
            dict(
                text="Play",
                icon="play",
                font_style="Caption",
                height="36dp",
                top_pad="10dp",
                bot_pad="10dp",
                divider=None
            ),
            dict(
                text="Configure",
                icon="cog",
                font_style="Caption",
                height="36dp",
                top_pad="10dp",
                bot_pad="10dp",
                divider=None
            ),
            dict(
                text="Update (fast)",
                icon="run-fast",
                font_style="Caption",
                height="36dp",
                top_pad="10dp",
                bot_pad="10dp",
                divider=None
            ),
            dict(
                text="Update",
                icon="update",
                font_style="Caption",
                height="36dp",
                top_pad="10dp",
                bot_pad="10dp",
                divider=None
            ),
            dict(
                text="Rename",
                icon="text-box",
                font_style="Caption",
                height="36dp",
                top_pad="10dp",
                bot_pad="10dp",
                divider=None
            ),
            dict(
                text="Sort by date",
                icon="sort-alphabetical-ascending",
                font_style="Caption",
                height="36dp",
                top_pad="10dp",
                bot_pad="10dp",
                divider=None
            ),
        ]

        def menu_callback(instance):
            if instance.text == "Play":
                self.root.ids.id_tabcont.play_pls()
            elif instance.text == "Configure":
                self.root.ids.id_tabcont.conf_pls()
            elif instance.text == "Update (fast)":
                self.root.ids.id_tabcont.update_fast_pls()
            elif instance.text == "Update":
                self.root.ids.id_tabcont.update_pls()
            elif instance.text == "Rename":
                self.root.ids.id_tabcont.rename_pls()
            elif instance.text == "Sort by date":
                self.root.ids.id_tabcont.sort_pls()
            while instance:
                instance = instance.parent
                if isinstance(instance, MDDropdownMenu):
                    instance.dismiss()
                    break

        MDDropdownMenu(
            items=items,
            width_mult=3.5,
            caller=self.root.ids.id_toolbar.ids["right_actions"].children[0],
            callback=menu_callback).open()

# https://stackoverflow.com/questions/42159927/http-basic-auth-on-twisted-klein-server
# https://github.com/racker/python-twisted-core/blob/master/doc/examples/dbcred.py

    def __init__(self, *args, **kwargs):
        super(MainApp, self).__init__(*args, **kwargs)

    def build(self):
        """
        Build and return the root widget.
        """
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "LightBlue"
        # The line below is optional. You could leave it out or use one of the
        # standard options, such as SettingsWithSidebar, SettingsWithSpinner
        # etc.
        self.settings_cls = SettingsWithSpinner

        # We apply the saved configuration settings or the defaults
        root = Builder.load_string(KV)  # (client=self.client)
        return root

    def on_start(self):
        Window.bind(on_keyboard=self._on_keyboard)
        if platform == "win":
            self.root.ids.id_tabcont.launchconf = self.config.get("windows", "plpath")
        else:
            self.root.ids.id_tabcont.launchconf = ''
        self.root.ids.id_tabcont.cardsize = int(self.config.get("gui", "cardsize"))
        self.root.ids.id_tabcont.cardtype = self.config.get("gui", "cardtype")
        self.root.ids.id_tabcont.client = self.client
        self.root.ids.id_tabcont.sel_tab = int(self.config.get("gui", "current_tab"))
        self.root.ids.id_tabcont.bind(on_tab_switch=self.on_tab_switch)
        self.on_config_change(self.config, "network", "host", None)
        self.root.ids.content_drawer.image_path = join(
            dirname(__file__), "images", "navdrawer.png")
        for items in {
            "home-outline": ("Home", self.on_nav_home),
            "cog-outline": ("Settings", self.on_nav_settings),
            "exit-to-app": ("Exit", self.on_nav_exit),
        }.items():
            self.root.ids.content_drawer.ids.box_item.add_widget(
                NavigationItem(
                    text=items[1][0],
                    icon=items[0],
                    on_release=items[1][1]
                )
            )

    def on_tab_switch(self, inst, tab, *args):
        v = '-1' if tab is None or tab.playlist.rowid is None else str(tab.playlist.rowid)
        Logger.debug(f'Setting current_tab to {v}')
        self.config.set("gui", "current_tab", v)
        self.config.write()

    def on_nav_home(self, *args, **kwargs):
        Logger.debug("On Nav Home")

    def on_nav_exit(self, *args, **kwargs):
        self.true_stop()

    def on_nav_settings(self, *args, **kwargs):
        self.open_settings()

    def server_ping(self, address, port, *args, **kwargs):
        port = int(port)
        Logger.debug("Gui: Ping received with port %s" % str(port))
        self.osc_port_service = port
        if self.timer_server_online:
            self.timer_server_online.cancel()
        self.timer_server_online = Timer(5, self.set_server_offline)

    async def set_server_offline(self):
        if self.timer_server_online:
            self.timer_server_online = None
        self.start_server()

    def stop_me(self):
        if platform == "android":
            if self.osc_timer:
                self.osc_timer.cancel()
                self.osc_timer = None
            if self.osc_transport:
                self.osc_transport.close()
                self.osc_transport = None
        Timer(0, self.stop_client_gracefully)

    async def stop_client_gracefully(self):
        if self.client:
            await self.client.stop()
        self.stop()

    def true_stop(self):
        if platform == "android":
            self.stop_server()
        self.stop_me()

    def build_config(self, config):
        """
        Set the default values for the configs sections.
        """
        config.setdefaults('network',
                           {'host': '127.0.0.1', 'port': 8080,
                            'timeout': 10, 'retry': 5})
        config.setdefaults('registration',
                           {'username': 'new', 'password': 'password'})
        config.setdefaults('gui',
                           {'cardsize': 150, 'cardtype': 'RESIZE',
                            'current_tab': -1})
        if platform == "win":
            config.setdefaults('windows', {'plpath': ''})
        self._init_fields()

    async def osc_init(self):
        from pythonosc.osc_server import AsyncIOOSCUDPServer
        try:
            Logger.debug("Binding osc port %d" % self.osc_port)
            self.osc_server = AsyncIOOSCUDPServer(
                ('127.0.0.1', self.osc_port),
                self.osc_dispatcher, asyncio.get_event_loop())
            self.osc_transport, self.osc_protocol = await self.osc_server.create_serve_endpoint()  # Create datagram endpoint and start serving
            if self.osc_timer:
                self.osc_timer = None
            Logger.debug("OSC OK")
        except (Exception, OSError):
            self.osc_timer = Timer(1, self.osc_init)

    def _init_fields(self):
        self.title = __prog__
        self.osc_port = PORT_OSC_CONST
        self.timer_server_online = None
        self.osc_port_service = find_free_port()
        self.osc_server = None
        self.osc_transport = None
        self.osc_protocol = None
        if platform == 'android':
            from pythonosc.dispatcher import Dispatcher
            self.osc_dispatcher = Dispatcher()
            self.osc_dispatcher.map("/server_ping", self.server_ping)
            self.osc_timer = Timer(0, self.osc_init)
        else:
            self.osc_dispatcher = None
            self.osc_timer = None
        self.client = PlsClient()
        self.userid = None
        self.win_notifyed = False

    def build_settings(self, settings):
        """
        Add our custom section to the default configuration object.
        """
        dn = dirname(__file__)
        # We use the string defined above for our JSON, but it could also be
        # loaded from a file as follows:
        #     settings.add_json_panel('My Label', self.config, 'settings.json')
        settings.register_type('password', SettingPassword)
        settings.register_type('buttons', SettingButtons)
        settings.add_json_panel('Network', self.config, join(dn, 'network.json'))  # data=json)
        settings.add_json_panel('Registration', self.config, join(dn, 'registration.json'))  # data=json)
        settings.add_json_panel('GUI', self.config, join(dn, 'gui.json'))  # data=json)
        if platform == "win":
            settings.add_json_panel('Windows', self.config, join(dn, 'windows.json'))  # data=json)

    def check_host_port_config(self):
        host = self.config.get("network", "host")
        if not host:
            toast("Host cannot be empty")
            return False
        port = self.config.getint("network", "port")
        if not port or port > 65535 or port <= 0:
            toast("Port should be in the range [1, 65535]")
            return False
        return True

    def check_other_config(self):
        user = self.config.get("registration", "username")
        password = self.config.get("registration", "password")
        Logger.debug("User = {user} Password = {password}".format(user=user, password=password))
        if not user or len(user) < 6 or not password or len(password) < 6:
            toast("User and Password length shoul be>=6")
            return False
        if platform == "win":
            plpath = self.config.get("windows", "plpath")
            if (not plpath or len(plpath) <= 4) and not self.win_notifyed:
                self.win_notifyed = True
                toast("For windows playback to work you should set correct player path")
        try:
            to = int(self.config.get("network", "timeout"))
        except Exception:
            to = -1
        if to <= 0:
            toast('Please insert a valid timeout value (int>=0)')
            return False
        try:
            to = int(self.config.get("network", "retry"))
        except Exception:
            to = -1
        if to <= 1:
            toast('Please insert a valid retry value (int>=1)')
            return False
        return True

    def start_server(self):
        host = self.config.get("network", "host")
        if platform == 'android' and not self.timer_server_online and\
           (host == "localhost" or host == "127.0.0.1"):
            try:
                from jnius import autoclass
                package_name = 'org.kivymfz.playlistmanager'
                service_name = 'Httpserverservice'
                service_class = '{}.Service{}'.format(
                    package_name, service_name.title())
                service = autoclass(service_class)
                mActivity = autoclass('org.kivy.android.PythonActivity').mActivity

                arg = dict(dbfile=join(MainApp.db_dir(), 'maindb.db'),
                           host='0.0.0.0', port=self.config.getint("network", "port"),
                           msgfrom=self.osc_port_service, msgto=self.osc_port, verbose=True)
                argument = json.dumps(arg)
                Logger.info("Starting %s [%s]" % (service_class, argument))
                service.start(mActivity, argument)
                self.client.start_login_process(self.on_login)
            except Exception:
                Logger.error(traceback.format_exc())
            finally:
                self.timer_server_online = Timer(5, self.set_server_offline)

    def stop_server(self):
        if platform == "android" and self.osc_port_service and self.timer_server_online:
            self.timer_server_online.cancel()
            self.timer_server_online = None
            from pythonosc.udp_client import SimpleUDPClient
            Logger.debug("Sending stop service message to %d" % self.osc_port_service)
            client = SimpleUDPClient('127.0.0.1', self.osc_port_service)  # Create client
            client.send_message("/stop_service", 0)   # Send float message

    def rec_player_path(self, inst, path):
        self.config.set("windows", "plpath", path)
        self.config.write()

    def _on_keyboard(self, win, scancode, *largs):
        if scancode == 27:
            if self.root.ids.nav_drawer.state == 'open':
                self.root.ids.nav_drawer.set_state("close")
            else:
                self.stop_me()
            return True
        return False

    def on_config_change(self, config, section, key, value):
        """
        Respond to changes in the configuration.
        """
        Logger.info("main.py: App.on_config_change: {0}, {1}, {2}, {3}".format(
            config, section, key, value))
        dologin = True
        if section == "windows" and key == "pathbuttons" and value == "btn_sel":
            plwidget = PlayerPathWidget(
                startpath=self.config.get("windows", "plpath"),
                on_player_path=self.rec_player_path
            )
            self.close_settings()
            self.root.ids.nav_drawer.set_state("close")
            self.root.ids.id_screen_manager.add_widget(plwidget)
            self.root.ids.id_screen_manager.current = plwidget.name
        if section == "gui" and key == "cardtype":
            self.root.ids.id_tabcont.cardtype = value
        elif self.check_host_port_config():
            if section == "network" and (key == "host" or key == "port"):
                if self.timer_server_online and value:
                    self.stop_server()
                host = self.config.get("network", "host")
                Logger.info("Host port good %s" % host)
                if not self.timer_server_online:
                    if host == "localhost" or host == "127.0.0.1":
                        Logger.info("Have to start server")
                        dologin = platform != 'android'
                        self.timer_server_online = Timer(0, self.set_server_offline)
        else:
            return
        if self.check_other_config():
            if (section == "network" and (key == "host" or key == "port")) or\
               (section == "registration" and (key == "username" or key == "password")):
                self.client.set_pars(
                    host=self.config.get('network', 'host'),
                    port=int(self.config.get('network', 'port')),
                    username=self.config.get('registration', 'username'),
                    password=self.config.get('registration', 'password'),
                    timeout=int(self.config.get('network', 'timeout')),
                    retry=int(self.config.get('network', 'retry')),
                )
                if dologin:
                    self.client.start_login_process(self.on_login)
            elif section == "registration" and key.startswith("regbuttons"):
                if value == "btn_reg":
                    Timer(0, self.do_register)
                elif value == "btn_out":
                    Timer(0, partial(self.client.logout, callback=self.on_logout))
                elif value == "btn_mod":
                    Timer(0, partial(self.client.register, urlpart="modifypw", callback=self.on_modify_pw))

    async def do_register(self):
        await self.client.stop()
        await self.client.register(callback=self.on_register)

    async def on_register(self, client, rv, **kwargs):
        toast("Registration OK" if not rv else rv)
        self.client.start_login_process(self.on_login)

    async def on_modify_pw(self, client, rv, **kwargs):
        toast("Modify PW OK" if not rv else rv)

    async def on_logout(self, client, rv, **kwargs):
        toast("Logout OK" if not rv else rv)
        self.userid = None

    async def on_login(self, client, rv, userid=None, **kwargs):
        toast("Login OK" if not rv else rv)
        if not rv:
            self.root.ids.id_tabcont.useri = userid
            self.root.ids.id_tabcont.ws_dump(fast_videoidx=0)
            await client.estabilish_connection()

    def close_settings(self, settings=None):
        """
        The settings panel has been closed.
        """
        Logger.info("main.py: App.close_settings: {0}".format(settings))
        super(MainApp, self).close_settings(settings)


def main():
    os.environ['KIVY_EVENTLOOP'] = 'async'
    if platform == "win":
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()
    app = MainApp()
    loop.run_until_complete(app.async_run())
    loop.run_until_complete(asyncio_graceful_shutdown(loop, Logger, False))
    Logger.debug("Gui: Closing loop")
    loop.close()


if __name__ == '__main__':
    main()
