from os.path import isfile

from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import StringProperty, ObjectProperty, BooleanProperty
from kivy.uix.screenmanager import Screen
from kivy.utils import platform
from kivymd.uix.filemanager import MDFileManager, FloatButton
from kivymd.uix.list import OneLineListItem


Builder.load_string(
    '''
#:import MDTextFieldRound kivymd.uix.textfield.MDTextFieldRound
#:import MDList kivymd.uix.list.MDList
#:import MDFileManager kivymd.uix.filemanager.MDFileManager

<PlayerPathWidget>:
    name: 'playerpath'
    BoxLayout:
        spacing: dp(5)
        height: self.minimum_height
        orientation: 'vertical'
        MDToolbar:
            id: id_toolbar
            pos_hint: {'top': 1}
            size_hint: (1, 0.2)
            title: 'Player path'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.manager.remove_widget(root)]]
            elevation: 10
            size_hint_x: 1
            size_hint_y: None
            height: dp(60)
        BoxLayout:
            padding: [dp(30), dp(5)]
            size_hint_y: None
            height: dp(60)
            MDTextFieldRound:
                id: id_name
                icon_type: "without"
                hint_text: "Playlist name"
                normal_color: [0, 0, 0, 0.1]
                foreground_color: [0, 0, 0, 1]
                on_text: root.enable_buttons(self.text)
                size_hint_y: None
                height: dp(60)
        ScrollView:
            size_hint: (1, 0.7)
            MDList:
                id: id_types
    '''
)


class PlayerPathWidget(Screen):
    startpath = StringProperty('')
    modal_open = BooleanProperty(False)
    modal = ObjectProperty()
    file_manager = ObjectProperty()

    def get_win_drives(self):
        if platform == 'win':
            import win32api

            drives = win32api.GetLogicalDriveStrings()
            drives = drives.split('\000')[:-1]

            return drives
        else:
            return []

    def file_manager_open(self, inst):
        if not self.file_manager:
            self.file_manager = MDFileManager(
                select_path=self.check_path,
                exit_manager=self.exit_manager,
                ext=['.exe', '.bat', '.cmd', '.com']
                )
            for i in self.file_manager.children:
                if isinstance(i, FloatButton):
                    self.file_manager.remove_widget(i)
                    break
        self.file_manager.show(inst.text)  # output modal to the screen
        self.modal_open = True

    def exit_manager(self, *args):
        """Called when the user reaches the root of the directory tree."""

        self.file_manager.close()
        self.modal_open = False

    def __init__(self, **kwargs):
        self.register_event_type('on_player_path')
        super(PlayerPathWidget, self).__init__(**kwargs)
        if not isfile(self.startpath):
            self.startpath = __file__
        self.ids.id_name.text = self.startpath
        drives = self.get_win_drives()
        self.buttons = []
        for x in drives:
            b = OneLineListItem(
                text=x,
                on_release=self.file_manager_open)
            self.buttons.append(b)
            self.ids.id_types.add_widget(b)

    def check_path(self, path):
        if path and isfile(path):
            self.ids.id_name.text = path
            self.exit_manager()

    def on_player_path(self, path):
        Logger.debug("on_player_path called %s" % path)

    def enable_buttons(self, text, *args, **kwargs):
        if not text or not isfile(text):
            self.ids.id_toolbar.right_action_items = []
        else:
            self.ids.id_toolbar.right_action_items = [["content-save", lambda x: self.dispatch_player_path()]]

    def dispatch_player_path(self):
        self.manager.remove_widget(self)
        self.dispatch("on_player_path", self.ids.id_name.text)
