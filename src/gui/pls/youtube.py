from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import DictProperty, ListProperty, ObjectProperty
from kivy.uix.screenmanager import Screen
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.list import IRightBodyTouch, TwoLineAvatarIconListItem
from kivymd.uix.button import MDIconButton

from common.const import CMD_YT_PLAYLISTCHECK
from common.playlist import PlaylistMessage

Builder.load_string(
    '''
<YoutubeConfScreen>:
    name: 'conf_youtube'
    GridLayout:
        cols: 1
        rows: 5
        spacing: dp(5)
        height: self.minimum_height
        id: id_grid
        MDToolbar:
            id: id_toolbar
            title: "Youtube Configuration"
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.manager.remove_widget(root)]]
            right_action_items: [["content-save", lambda x: root.dispatch_conf(root)]]
            elevation: 10
        GridLayout:
            size_hint: (1, 0.1)
            cols: 2
            rows: 1
            spacing: [dp(10), dp(0)]
            padding: [dp(20), dp(0)]
            MDTextField:
                id: id_brandtf
                hint_text: 'Channel / Playlist'
                error: True
                helper_text_mode: "on_error"
                helper_text: 'Please write a playlist id or channel name'
            MDIconButton:
                id: id_brandbt
                on_release: root.brand_confirmed()
                icon: "subdirectory-arrow-left"
        ScrollView:
            size_hint: (1, 0.6)
            MDList:
                id: id_playlists
    '''
)


Builder.load_string(
    '''
<PlaylistItemW>:
    DelIconButton:
        icon: 'delete'
        on_release: root.dispatch_on_delete(self)
    '''
)


class PlaylistItemW(TwoLineAvatarIconListItem):
    playlistinfo = DictProperty()

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_delete')
        super(PlaylistItemW, self).__init__(*args, **kwargs)

    def on_playlistinfo(self, inst, b):
        self.secondary_text = (b['description'] + ' / ' if b['description'] else '') + b['id']
        self.text = (b['channel'] + '/' if 'channel' in b else '') + b['title']

    def dispatch_on_delete(self, inst):
        Logger.debug("BrandItem: Dispatching on brand")
        self.dispatch("on_delete", self.playlistinfo)

    def on_delete(self, brandinfo):
        Logger.debug("BrandItem: On delete %s" % str(brandinfo))


class DelIconButton(MDIconButton, IRightBodyTouch):
    pass


class YoutubeConfScreen(Screen):
    startconf = DictProperty()
    conf = DictProperty()
    playlists = ListProperty([])
    client = ObjectProperty()
    # manager = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super(YoutubeConfScreen, self).__init__(*args, **kwargs)
        self.on_startconf(self, self.startconf)
        self.ids.id_brandtf.icon_callback = self.brand_confirmed
        self.ids.id_brandtf.bind(text=self.brand_check)

    def on_startconf(self, inst, co):
        try:
            self.ids.id_brandtf.text = ''
        except (KeyError, AttributeError):
            return
        if 'playlists' in self.startconf:
            self.playlists = self.startconf['playlists']
            self.ids.id_brandtf.error = False
            for p in self.playlists:
                self.ids.id_playlists.add_widget(PlaylistItemW(
                    playlistinfo=p,
                    on_delete=self.remove_playlist
                ))
        self.save_button_show(len(self.playlists))

    def save_button_show(self, show):
        if not show:
            self.ids.id_toolbar.right_action_items = []
        else:
            self.ids.id_toolbar.right_action_items = [["content-save", lambda x: self.dispatch_conf(self)]]

    def remove_playlist(self, inst, brandinfo):
        self.ids.id_playlists.remove_widget(inst)
        for i, p in enumerate(self.playlists):
            if p['id'] == brandinfo['id']:
                del self.playlists[i]
                break
        self.save_button_show(len(self.playlists))

    def brand_check(self, inst, filt):
        Logger.debug("Brand check %s" % filt)
        if len(filt):
            inst.icon_right_disabled = False
            inst.icon_right_color = [0, 0, 0, 1]
            self.ids.id_brandbt.disabled = False
            if inst.error:
                inst.error = False
                inst.on_text(inst, filt)
        else:
            inst.icon_right_disabled = True
            inst.icon_right_color = [1, 1, 1, 1]
            self.ids.id_brandbt.disabled = True
            if not inst.error:
                inst.error = True
                inst.on_text(inst, filt)

    def brand_confirmed(self, *args, **kwargs):
        txt = self.ids.id_brandtf.text
        Logger.debug("MedRai: brand_confirmed %s" % txt)
        self.client.enqueue(PlaylistMessage(cmd=CMD_YT_PLAYLISTCHECK, text=txt), self.on_new_playlist_check)

    async def on_new_playlist_check(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv == 0:
            brandinfo = received.playlistinfo
            for p in self.playlists:
                if p['id'] == brandinfo['id']:
                    toast(f"Playlist {p['title']} already present!")
                    return
            self.ids.id_playlists.add_widget(PlaylistItemW(
                playlistinfo=brandinfo,
                on_delete=self.remove_playlist
            ))
            self.playlists.append(brandinfo)
            self.ids.id_brandtf.text = ''
            self.save_button_show(len(self.playlists))
        else:
            toast("[E %d] %s" % (received.rv, received.err))

    def dispatch_conf(self, inst):
        self.conf = dict(
            playlists=self.playlists)
        Logger.debug("YT: Dispatching conf %s" % str(self.conf))
        self.manager.remove_widget(self)


ConfWidget = YoutubeConfScreen
