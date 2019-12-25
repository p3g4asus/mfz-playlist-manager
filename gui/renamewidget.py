from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.logger import Logger
import re

Builder.load_string(
    '''
#:import MDTextFieldRound kivymd.uix.textfield.MDTextFieldRound
#:import MDRaisedButton kivymd.uix.button.MDRaisedButton
<RenameWidget>:
    orientation: 'vertical'
    name: ''
    MDTextFieldRound:
        id: id_name
        text: root.name
        icon_type: "without"
        hint_text: "Playlist name"
        normal_color: [0, 0, 0, .1]
        on_text: root.enable_button(self.text)
    BoxLayout:
        orientation: 'horizontal'
        MDRaisedButton:
            id: id_renamebtn
            text: 'Update'
            on_release: root.dispatch_rename()
        MDRaisedButton:
            id: id_exitbtn
            text: 'Exit'
            on_release: root.dispatch_exit()
    '''
)


class RenameWidget(BoxLayout):
    def __init__(self, **kwargs):
        self.register_event_type('on_rename')
        self.register_event_type('on_exit')
        super(RenameWidget, self).__init__(**kwargs)

    def enable_button(self, val):
        self.ids.id_renamebtn.disabled = not (val and len(val) and re.search(r"[a-zA-Z]", val))

    def on_exit(self, inst):
        Logger.debug("On exit called")

    def on_rename(self, inst, nm):
        Logger.debug("On update called %s" % (nm))

    def dispatch_rename(self, inst):
        self.dispatch('on_rename', self.ids.id_name.text)

    def dispatch_exit(self, inst):
        self.dispatch('on_exit')
