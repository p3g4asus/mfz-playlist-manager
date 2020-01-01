from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import ObjectProperty, BooleanProperty
from kivymd.uix.list import IRightBodyTouch, OneLineRightIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox

Builder.load_string(
    '''
#:import MDTextFieldRound kivymd.uix.textfield.MDTextFieldRound
#:import MDList kivymd.uix.list.MDList
<ListItemWithRadio>:
    on_release:
        root.ids.id_cb.active = (not root.ids.id_cb.active)\
            if not isinstance(root.group, str) or not len(root.group) else\
            root.ids.id_cb.active
    MyCheckbox:
        id: id_cb
        disabled: root.disabled
        active: root.active
        group: root.group
        on_active: root.dispatch_on_sel(self, self.active)
    '''
)


class MyCheckbox(MDCheckbox, IRightBodyTouch):
    pass


class ListItemWithRadio(OneLineRightIconListItem):
    group = ObjectProperty(None)
    active = BooleanProperty(False)

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_sel')
        super(ListItemWithRadio, self).__init__(*args, **kwargs)

    def dispatch_on_sel(self, inst, active):
        if active:
            self.dispatch("on_sel", self.text)

    def on_sel(self, text):
        Logger.debug("On on_sel %s" % str(text))
