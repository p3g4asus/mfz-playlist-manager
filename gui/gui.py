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
from functools import partial
from os.path import expanduser, join, dirname

from jnius import autoclass
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import ObjectProperty, StringProperty, ListProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.settings import Settings
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.list import OneLineAvatarListItem
from kivymd.uix.tab import MDTabs
from oscpy.client import send_message
from oscpy.server import OSCThreadServer

from common.const import CMD_DUMP, PORT_OSC_CONST
from common.playlist import PlaylistMessage, Playlist
from common.timer import Timer

from .client import PlsClient
from .plsitem import PlsItem
from .settingbuttons import SettingButtons
from .settingpassword import SettingPassword
from .typewidget import TypeWidget

if platform == "android":
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
                on_release: root.parent.toggle_nav_drawer()

            MDLabel:
                markup: True
                text: "[b]PlsManager[/b]\\nVersion: 1.0"
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

    NavigationLayout:

        ScreenManager:

            Screen:

                BoxLayout:
                    orientation: 'vertical'

                    MDToolbar:
                        id: id_toolbar
                        title: "Navigation Drawer"
                        md_bg_color: app.theme_cls.primary_color
                        left_action_items: [["menu", lambda x: nav_drawer.toggle_nav_drawer()]]
                        right_action_items: [["plus", id_tabcont.add_pls], ["delete", id_tabcont.del_pls], ["dots-vertical", app.open_menu]]

                    MyTabs:
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
    current_tab = ObjectProperty()
    client = ObjectProperty()
    useri = NumericProperty()

    def __init__(self, *args, **kwargs):
        super(MyTabs, self).__init__(*args, **kwargs)
        self.tab_list = []

    def remove_widget(self, w, *args, **kwargs):
        super(MyTabs, self).remove_widget(w)
        if isinstance(w, PlsItem):
            try:
                self.tab_list.remove(w)
            except ValueError:
                Logger.error(traceback.format_exc())
            if len(self.tab_list) == 0:
                self.current_tab = None
                Logger.debug("Gui: Currenttab = None")

    def clear_widgets(self):
        for w in self.tab_list:
            self.remove_widget(w)

    def add_widget(self, w, *args, **kwargs):
        super(MyTabs, self).add_widget(w, *args, **kwargs)
        if isinstance(w, PlsItem):
            self.tab_list.append(w)
            Logger.debug("Gui: Adding tab len = %d" % len(self.tab_list))
            if len(self.tab_list) == 1:
                Logger.debug("Gui: Currenttab = %s" % str(w))
                self.current_tab = w

    def on_tab_switch(self, inst, text):
        super(MyTabs, self).on_tab_switch(inst, text)
        Logger.debug("On tab switch to %s" % str(text))
        self.current_tab = inst.tab
        Logger.debug("Gui: Currenttab = %s" % str(inst.tab))

    def add_pls(self, *args, **kwargs):
        if self.client.is_logged_in():
            self.popup = Popup(
                content=TypeWidget(on_type=self.on_new_type),
                auto_dismiss=True, title='Type')
            self.popup.open()
        else:
            toast("Please login before adding")

    def update_pls(self, *args, **kwargs):
        if self.current_tab:
            self.current_tab.update_pls()
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
            self.current_tab.del_pls(self)
        else:
            toast("Please select a playlist tab")

    def rename_pls(self):
        if self.current_tab:
            self.current_tab.rename_pls()
        else:
            toast("Please select a playlist tab")

    def on_new_type(self, inst, name, types, confclass):
        if types != TypeWidget.ABORT:
            tab = PlsItem(
                playlist=Playlist(type=types, name=name, useri=self.useri, conf=dict()),
                client=self.client,
                launchconf=self.launchconf,
                confclass=confclass)
            self.add_widget(tab)
        if self.popup:
            self.popup.dismiss()
            self.popup = None


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
        os.mkdir(pth)
        return pth

    def open_menu(self, *args, **kwargs):
        items = [
            dict(
                viewclass="MDMenuItem",
                text="Play",
                icon="play",
                callback=self.root.ids.id_tabcont.play_pls
            ),
            dict(
                viewclass="MDMenuItem",
                text="Configure",
                icon="settings",
                callback=self.root.ids.id_tabcont.conf_pls
            ),
            dict(
                viewclass="MDMenuItem",
                text="Update",
                icon="update",
                callback=self.root.ids.id_tabcont.update_pls
            ),
            dict(
                viewclass="MDMenuItem",
                text="Rename",
                icon="textbox",
                callback=self.root.ids.id_tabcont.rename_pls
            ),
        ]
        MDDropdownMenu(items=items, width_mult=3).open(
            self.root.ids.id_toolbar.ids["right_actions"].children[0])

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
        self.settings_cls = Settings

        # We apply the saved configuration settings or the defaults
        root = Builder.load_string(KV)  # (client=self.client)
        return root

    def on_start(self):
        self.on_config_change(self.config, "network", "host", None)
        self.root.ids.id_tabcont.launchconf = self.config.get("windows", "plpath")
        self.root.ids.id_tabcont.client = self.client
        self.root.ids.content_drawer.image_path = join(
            dirname(__file__), "images", "navdrawer.png")
        for items in {
            "home-circle-outline": ("Home", self.on_nav_home),
            "settings-outline": ("Settings", self.on_nav_settings),
            "exit-to-app": ("Exit", self.on_nav_exit),
        }.items():
            self.root.ids.content_drawer.ids.box_item.add_widget(
                NavigationItem(
                    text=items[1][0],
                    icon=items[0],
                    on_release=items[1][1]
                )
            )

    def on_nav_home(self, *args, **kwargs):
        Logger.debug("On Nav Home")

    def on_nav_exit(self, *args, **kwargs):
        self.client.stop()
        self.stop()

    def on_nav_settings(self, *args, **kwargs):
        self.open_settings()

    def server_ping(self, msg):
        m = json.loads(msg)
        self.port_service = m['msgport']
        if self.server_started:
            self.server_started.cancel()
        self.server_started = Timer(5, self.server_stopped)

    async def server_stopped(self):
        if self.server_started:
            self.server_started.cancel()
            self.server_started = None

    def true_stop(self):
        self.stop_server()
        self.stop()

    def build_config(self, config):
        """
        Set the default values for the configs sections.
        """
        config.setdefaults('network',
                           {'host': '127.0.0.1', 'port': 8080,
                            'timeout': 10, 'retry': 5})
        config.setdefaults('registration',
                           {'username': 'new', 'password': 'password'})
        if platform == "win":
            config.setdefaults('windows', {'plpath': ''})
        self._init_fields()

    def _init_fields(self):
        self.port_osc = PORT_OSC_CONST
        self.server_started = None
        self.port_service = find_free_port()
        self.osc = OSCThreadServer(encoding='utf8')
        self.osc.listen(address='127.0.0.1', port=self.port_osc, default=True)
        self.osc.bind('/server_ping', self.server_ping)
        self.client = PlsClient()
        self.userid = None
        self.playlists = []
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
        if platform == "win":
            settings.add_json_panel('Windows', self.config, join(dn, 'windows.json'))  # data=json)

    def check_config(self):
        host = self.config.get("network", "host")
        if not host:
            toast("Host cannot be empty")
            return False
        port = self.config.getint("network", "port")
        if not port or port > 65535 or port <= 0:
            toast("Port should be in the range [1, 65535]")
            return False
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
        return True

    async def start_server(self):
        if platform == 'android' and not self.server_started:
            from jnius import autoclass
            package_name = 'plsapp'
            package_domain = 'org.mfz'
            service_name = 'httpPls'
            service_class = '{}.{}.Service{}'.format(
                package_domain, package_name, service_name.title())
            service = autoclass(service_class)
            mActivity = autoclass('org.kivy.android.PythonActivity').mActivity

            arg = dict(dbfile=join(MainApp.db_dir(), 'maindb.db'),
                       host='0.0.0.0', port=self.config.getint("network", "port"),
                       msgfrom=self.port_service, msgto=self.port_osc)
            argument = json.dumps(arg)
            service.start(mActivity, argument)

    def stop_server(self):
        if platform == "android" and self.port_service:
            send_message('/stop_service',
                         (json.dumps(dict(bye='bye')),),
                         '127.0.0.1',
                         self.port_service,
                         encoding='utf8')

    def on_config_change(self, config, section, key, value):
        """
        Respond to changes in the configuration.
        """
        Logger.info("main.py: App.on_config_change: {0}, {1}, {2}, {3}".format(
            config, section, key, value))
        if self.check_config():
            if section == "network" and (key == "host" or key == "port"):
                if self.server_started and value:
                    self.stop_server()
                host = self.config.get("network", "host")
                if host == "localhost" or host == "127.0.0.1":
                    Timer(6, self.start_server)
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
                self.client.start_login_process(self.on_login)
            elif section == "registration" and key == "regbuttons":
                if value == "btn_reg":
                    self.client.stop()
                    Timer(1, partial(self.client.register, callback=self.on_register))
                elif value == "btn_out":
                    Timer(1, partial(self.client.logout, callback=self.on_logout))
                elif value == "btn_mod":
                    Timer(1, partial(self.client.register, urlpart="modifypw", callback=self.on_modify_pw))

    async def on_register(self, client, rv, **kwargs):
        toast("Registration OK" if not rv else rv)

    async def on_modify_pw(self, client, rv, **kwargs):
        toast("Modify PW OK" if not rv else rv)

    async def on_logout(self, client, rv, **kwargs):
        toast("Logout OK" if not rv else rv)
        self.userid = None

    async def on_login(self, client, rv, userid=None, **kwargs):
        toast("Login OK" if not rv else rv)
        if not rv:
            self.root.ids.id_tabcont.useri = userid
            client.enqueue(PlaylistMessage(cmd=CMD_DUMP, useri=userid), self.on_ws_dump)
            await client.estabilish_connection()

    async def on_ws_dump(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv:
            toast("[E %d] %s" % (received.rv, received.err))
        else:
            self.playlists = received.f('playlists')
            self.fill_PlsListRV()

    def fill_PlsListRV(self):
        d = self.root.ids.id_tabcont.tab_list
        processed = dict()
        for t in d:
            try:
                idx = self.playlists.index(t.playlist)
                processed[str(idx)] = True
                t.set_playlist(self.playlists[idx])
            except ValueError:
                self.root.remove_widget(t)
        for x in range(len(self.playlists)):
            if str(x) not in processed:
                self.root.ids.id_tabcont.add_widget(PlsItem(
                    playlist=self.playlists[x],
                    launchconf=self.config.get("windows", "plpath"),
                    client=self.client,
                    confclass=TypeWidget.type2class(self.playlists[x].type)
                ))

    def close_settings(self, settings=None):
        """
        The settings panel has been closed.
        """
        Logger.info("main.py: App.close_settings: {0}".format(settings))
        super(MainApp, self).close_settings(settings)


def main():
    os.environ['KIVY_EVENTLOOP'] = 'async'
    loop = asyncio.get_event_loop()
    app = MainApp()
    loop.run_until_complete(app.async_run())
    loop.close()


if __name__ == '__main__':
    main()
