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
from contextlib import closing
from functools import partial
from os.path import expanduser, join

from jnius import autoclass
from kivy.logger import Logger
from kivy.properties import ObjectProperty
from kivy.uix.settings import Settings
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.toast.kivytoast.kivytoast import toast
from oscpy.client import send_message
from oscpy.server import OSCThreadServer

from common.const import CMD_DUMP, PORT_OSC_CONST
from common.playlist import PlaylistMessage
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


def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


class MainPls(TabbedPanel):
    client = ObjectProperty()

    def __init__(self, *args, **kwargs):
        kwargs['do_default_tab'] = True
        kwargs['default_tab_cls'] = partial(PlsItem, playlist=None, client=kwargs.get("client"))
        super(MainPls, self).__init__(args, kwargs)


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

# https://stackoverflow.com/questions/42159927/http-basic-auth-on-twisted-klein-server
# https://github.com/racker/python-twisted-core/blob/master/doc/examples/dbcred.py

    def __init__(self, *args, **kwargs):
        super(MainApp, self).__init__(*args, **kwargs)

    def build(self):
        """
        Build and return the root widget.
        """
        # The line below is optional. You could leave it out or use one of the
        # standard options, such as SettingsWithSidebar, SettingsWithSpinner
        # etc.
        self.settings_cls = Settings

        # We apply the saved configuration settings or the defaults
        self.client = PlsClient()
        root = MainPls(client=self.client)
        self.port_osc = PORT_OSC_CONST
        self.server_started = None
        self.port_service = find_free_port()
        self.osc = OSCThreadServer(encoding='utf8')
        self.osc.listen(address='127.0.0.1', port=self.port_osc, default=True)
        self.osc.bind('/server_ping', self.server_ping)
        self.userid = None
        self.playlists = []
        return root

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
        if platform == "windows":
            config.setdefaults('windows', {'plpath', ''})
        self.client.set_pars(
            host=self.config.get('network', 'host'),
            port=self.config.get('network', 'port'),
            username=self.config.get('registration', 'username'),
            password=self.config.get('registration', 'password'),
            timeout=self.config.get('network', 'timeout'),
            retry=self.config.get('network', 'retry'),
        )
        self.client.start_login_process(self.on_login)

    def build_settings(self, settings):
        """
        Add our custom section to the default configuration object.
        """
        # We use the string defined above for our JSON, but it could also be
        # loaded from a file as follows:
        #     settings.add_json_panel('My Label', self.config, 'settings.json')
        settings.register_type('password', SettingPassword)
        settings.register_type('buttons', SettingButtons)
        settings.add_json_panel('Network', self.config, 'network.json')  # data=json)
        settings.add_json_panel('Registration', self.config, 'registration.json')  # data=json)
        if platform == "windows":
            settings.add_json_panel('Windows', self.config, 'windows.json')  # data=json)
        self.on_config_change(self.config, "network", "host", None)

    def check_settings(self):
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
        if not user or len(user) < 6 or not password or len(password) < 6:
            toast("User and Password length shoul be>=6")
            return False
        if platform == "windows":
            plpath = self.config.get("windows", "plpath")
            if not plpath or len(plpath) <= 4:
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
        if self.check_settings():
            if section == "registration" and (key == "host" or key == "port"):
                if self.server_started and value:
                    self.stop_server()
                host = self.config.get("network", "host")
                if host == "localhost" or host == "127.0.0.1":
                    Timer(6, self.start_server)
            elif section == "registration" and key == "regbuttons":
                if value == "btn_reg":
                    await self.register(callback=self.on_register)
                elif value == "btn_out":
                    await self.logout(callback=self.on_logout)
                elif value == "btn_mod":
                    await self.register(urlpart="modify_pw", callback=self.on_modify_pw)

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
            client.enqueue(PlaylistMessage(cmd=CMD_DUMP, useri=userid), self.on_ws_dump)
            await client.estabilish_connection()

    async def on_ws_dump(self, client, inmsg, outmsg):
        self.playlists = outmsg.f('playlists')
        self.fill_PlsListRV()

    def fill_PlsListRV(self):
        d = self.root.tab_list
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
                self.root.add_widget(PlsItem(
                    playlist=self.playlists[x],
                    client=self.client,
                    confclass=TypeWidget.type2class(self.playlists[x].type)
                ))

    def close_settings(self, settings=None):
        """
        The settings panel has been closed.
        """
        Logger.info("main.py: App.close_settings: {0}".format(settings))
        super(MainApp, self).close_settings(settings)


os.environ['KIVY_EVENTLOOP'] = 'async'
loop = asyncio.get_event_loop()
app = MainApp()
loop.run_until_complete(app.async_run())
loop.close()
