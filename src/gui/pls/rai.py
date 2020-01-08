from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import DictProperty, ListProperty,\
    ObjectProperty, BooleanProperty
from kivy.uix.screenmanager import Screen
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.list import IRightBodyTouch, TwoLineAvatarIconListItem, ThreeLineListItem
from kivymd.uix.selectioncontrol import MDCheckbox

from common.const import CMD_RAI_CONTENTSET
from common.playlist import PlaylistMessage


Builder.load_string(
    '''
#:import MDIconButton kivymd.uix.button.MDIconButton
#:import MDList kivymd.uix.list.MDList
#:import ButtonDatePicker gui.buttondatepicker.ButtonDatePicker
<ContentSetItem>:
    on_release:
        id_cb.state = 'down' if id_cb.state == 'normal' else 'normal'
    ProgCheckbox:
        id: id_cb
        group: root.group
        active: root.active
        disabled: root.disabled
        on_active: root.dispatch_on_prog(self, self.active)
<RaiConfScreen>:
    name: 'conf_mediaset'
    GridLayout:
        cols: 1
        rows: 4
        spacing: dp(5)
        height: self.minimum_height
        MDToolbar:
            id: id_toolbar
            title: 'Rai configuration'
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
                hint_text: "Prog ID"
                required: True
                helper_text_mode: "on_error"
                id: id_progtf
            MDIconButton:
                id: id_progbt
                on_release: root.prog_confirmed()
                icon: "subdirectory-arrow-left"
        ScrollView:
            size_hint: (1, 0.15)
            MDList:
                id: id_listings
        ScrollView:
            size_hint: (1, 0.55)
            MDList:
                id: id_contentsets
    '''
)


class ProgItem(ThreeLineListItem):
    proginfo = DictProperty()

    def __init__(self, *args, **kwargs):
        super(ProgItem, self).__init__(*args, **kwargs)
        b = self.proginfo
        self.text = b['title']
        self.secondary_text = '[' + b['channel'] + '] ' + b['desc'] + '\n' +\
            b['id']


class ContentSetItem(TwoLineAvatarIconListItem):
    proginfo = DictProperty()
    active = BooleanProperty(False)
    group = ObjectProperty(None)

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_prog')
        super(ContentSetItem, self).__init__(*args, **kwargs)
        b = self.proginfo
        self.secondary_text = b['id']
        self.text = b['title']

    def dispatch_on_prog(self, inst, active):
        Logger.debug("Rai: Dispatching on prog")
        self.dispatch("on_prog", self.proginfo, active)

    def on_prog(self, proginfo, active):
        Logger.debug("On prog %s %d" % (str(proginfo), active))


class ProgCheckbox(MDCheckbox, IRightBodyTouch):
    def __init__(self, *args, **kwargs):
        if 'group' in kwargs and not kwargs['group']:
            del kwargs['group']
        super(ProgCheckbox, self).__init__(*args, **kwargs)

    def on_group(self, inst, group):
        # Logger.debug("Mediaset: group = %s %s %s" % (str(group), str(type(inst)), str(type(group))))
        if group and len(group):
            super(ProgCheckbox, self).on_group(self, group)


class RaiConfScreen(Screen):
    startconf = DictProperty()
    conf = DictProperty()
    current_prog = DictProperty()
    current_contentsets = ListProperty([])
    client = ObjectProperty()
    # manager = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super(RaiConfScreen, self).__init__(*args, **kwargs)
        self.on_startconf(self, self.startconf)
        self.ids.id_progtf.icon_callback = self.prog_confirmed
        self.ids.id_progtf.bind(text=self.prog_check)
        # self.ids.id_filtertf.bind(text=self.filter_check)

    def on_startconf(self, inst, co):
        br = 0
        sbr = 0
        try:
            self.ids.id_listings.clear_widgets()
            self.ids.id_contentsets.clear_widgets()
            self.ids.id_progtf.text = ''
        except (KeyError, AttributeError):
            return
        if 'prog' in self.startconf:
            self.current_prog = self.startconf['prog']
            self.ids.id_progtf.text = str(self.current_prog['id'])
            li = ProgItem(proginfo=self.startconf['prog'])
            self.ids.id_listings.add_widget(li)
            br += 1
        if 'contentsets' in self.startconf:
            self.current_contentsets = self.startconf['contentsets']
            for sb in self.startconf['contentsets']:
                li = ContentSetItem(proginfo=sb, active=True, on_prog=self.on_prog_contentsets_checked)
                self.ids.id_contentsets.add_widget(li)
                sbr += 1
        self.save_button_show(br and sbr)

    def save_button_show(self, show):
        if not show:
            self.ids.id_toolbar.right_action_items = []
        else:
            self.ids.id_toolbar.right_action_items = [["content-save", lambda x: self.dispatch_conf(self)]]

    def on_prog_contentsets_checked(self, inst, proginfo, active):
        subs = self.current_contentsets
        if active:
            subs.append(proginfo)
        else:
            for i in range(len(subs)):
                if subs[i]['id'] == proginfo['id']:
                    del subs[i]
                    break
        self.save_button_show(len(subs) > 0)

    def prog_check(self, inst, filt):
        Logger.debug("Prog check %s" % filt)
        if len(filt):
            inst.icon_right_disabled = False
            inst.icon_right_color = [0, 0, 0, 1]
            self.ids.id_progbt.disabled = False
        else:
            inst.icon_right_disabled = True
            inst.icon_right_color = [1, 1, 1, 1]
            self.ids.id_progbt.disabled = True

    def prog_confirmed(self, *args, **kwargs):
        bid = self.ids.id_progtf.text
        Logger.debug("Rai: prog_confirmed %s" % bid)
        self.ids.id_contentsets.clear_widgets()
        self.ids.id_listings.clear_widgets()
        self.current_contentsets = []
        self.client.enqueue(PlaylistMessage(cmd=CMD_RAI_CONTENTSET, progid=bid), self.on_new_progs_result)

    def fill_info(self, prog, lst):
        li = ProgItem(proginfo=prog)
        self.current_prog = prog
        self.ids.id_listings.add_widget(li)
        for sb in lst:
            li = ContentSetItem(proginfo=sb, active=False, on_prog=self.on_prog_contentsets_checked)
            self.ids.id_contentsets.add_widget(li)

    async def on_new_progs_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv == 0:
            self.fill_info(received.prog, received.contentsets)
        else:
            toast("[E %d] %s" % (received.rv, received.err))

    def dispatch_conf(self, inst):
        self.conf = dict(
            prog=self.current_prog,
            contentsets=self.current_contentsets)
        Logger.debug("Rai: Dispatching conf %s" % str(self.conf))
        self.manager.remove_widget(self)


ConfWidget = RaiConfScreen
