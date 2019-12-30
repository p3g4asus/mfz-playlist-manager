import glob
import re
import traceback
from os.path import basename, dirname, isfile, join

from kivy.lang import Builder
from kivy.logger import Logger
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.list import IRightBodyTouch, OneLineRightIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox

Builder.load_string(
    '''
#:import MDTextFieldRound kivymd.uix.textfield.MDTextFieldRound
#:import MDList kivymd.uix.list.MDList
<ListItemWithRadio>:
    on_release:
        root.ids.id_cb.active = not root.ids.id_cb.active
    MyCheckbox:
        id: id_cb
        disabled: root.disabled
        group: "types"
        on_active: root.dispatch_on_sel(self, self.active)

<TypeWidget>:
    spacing: 10
    orientation: 'vertical'
    id: idbox
    pos_hint: {"center_x": .5, "center_y": 1}
    MDTextFieldRound:
        id: id_name
        icon_type: "without"
        hint_text: "Playlist name"
        normal_color: [0, 0, 0, .1]
        pos_hint: {"center_x": .5, "center_y": 1}
        size_hint: 1, None
        on_text: root.enable_buttons(self.text)
    MDList:
        id: id_types
    '''
)


class MyCheckbox(MDCheckbox, IRightBodyTouch):
    pass


class ListItemWithRadio(OneLineRightIconListItem):

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_sel')
        super(ListItemWithRadio, self).__init__(*args, **kwargs)

    def dispatch_on_sel(self, inst, active):
        if active:
            self.dispatch("on_sel", self.text)

    def on_sel(self, text):
        Logger.debug("On on_sel %s" % str(text))


class TypeWidget(BoxLayout):
    ABORT = "Abort"
    TYPES = dict()

    @staticmethod
    def type2class(types):
        if not len(TypeWidget.TYPES):
            TypeWidget._get_pls_types()
        return TypeWidget.TYPES.get(types)

    @staticmethod
    def _get_pls_types():
        import importlib
        modules = glob.glob(join(dirname(__file__), "pls", "*.py"))
        pls = [basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py')]
        for x in pls:
            Logger.debug("Processing %s" % x)
            try:
                m = importlib.import_module("gui.pls."+x)
                clb = getattr(m, "ConfWidget")
                if clb:
                    Logger.debug("Class found: adding")
                    TypeWidget.TYPES[x] = clb
            except Exception:
                Logger.warning(traceback.format_exc())

    def __init__(self, **kwargs):
        self.register_event_type('on_type')
        if not len(TypeWidget.TYPES):
            TypeWidget._get_pls_types()
        super(TypeWidget, self).__init__(**kwargs)
        self.buttons = []
        for x in TypeWidget.TYPES.keys():
            b = ListItemWithRadio(text=x, on_sel=self.dispatch_on_type)
            self.buttons.append(b)
            self.ids.id_types.add_widget(b)
        b = ListItemWithRadio(text="Abort", on_sel=self.dispatch_on_type)
        self.ids.id_types.add_widget(b)

    def on_type(self, name, type, confclass):
        Logger.debug("On type called %s, %s, %s" % (name, type, str(confclass)))

    def enable_buttons(self, text, *args, **kwargs):
        dis = not text or not re.search(r"[A-Za-z]", text)
        for b in self.buttons:
            b.disabled = dis

    def dispatch_on_type(self, widget, text):
        self.dispatch("on_type", self.ids.id_name.text, text, TypeWidget.TYPES.get(text))
