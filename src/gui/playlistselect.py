from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import DictProperty
from kivy.uix.screenmanager import Screen

from kivymd.uix.list import OneLineListItem

Builder.load_string(
    '''
#:import MDList kivymd.uix.list.MDList
<PlaylistSelectWidget>:
    name: 'playlistselect'
    BoxLayout:
        spacing: dp(5)
        height: self.minimum_height
        orientation: 'vertical'
        MDToolbar:
            pos_hint: {'top': 1}
            title: 'New Playlist'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_playlist('Cancel')]]
            elevation: 10
            size_hint_x: 1
            size_hint_y: None
            height: dp(60)
        ScrollView:
            size_hint: (1, 0.8)
            MDList:
                id: id_playlists
    '''
)


class PlaylistSelectWidget(Screen):
    ABORT = "Cancel"
    items = DictProperty()

    def __init__(self, **kwargs):
        self.register_event_type('on_playlist')
        super(PlaylistSelectWidget, self).__init__(**kwargs)
        self.buttons = []
        for x in self.items.keys():
            b = OneLineListItem(text=x, on_release=self.dispatch_on_playlist)
            self.buttons.append(b)
            self.ids.id_playlists.add_widget(b)
        self.abort_widget = OneLineListItem(text=PlaylistSelectWidget.ABORT, on_release=self.dispatch_on_playlist)
        self.ids.id_playlists.add_widget(self.abort_widget)

    def on_playlist(self, playlist, dictv):
        Logger.debug(f"On playlist called pl[{playlist}]={str(dictv)}")

    def dispatch_on_playlist(self, widget):
        self.manager.remove_widget(self)
        if isinstance(widget, str):
            text = widget
            elem = None
        else:
            text = widget.text
            elem = None if widget is self.abort_widget else self.items.get(text)
        self.dispatch("on_playlist", text, elem)
