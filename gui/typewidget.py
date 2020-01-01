import glob
import re
import traceback
from os.path import basename, dirname, isfile, join

from kivy.lang import Builder
from kivy.logger import Logger
from kivy.uix.screenmanager import Screen

from kivymd.uix.list import OneLineListItem

Builder.load_string(
    '''
#:import MDTextFieldRound kivymd.uix.textfield.MDTextFieldRound
#:import MDList kivymd.uix.list.MDList
<TypeWidget>:
    name: 'type'
    GridLayout:
        spacing: dp(5)
        height: self.minimum_height
        rows: 3
        cols: 1
        MDToolbar:
            pos_hint: {'top': 1}
            size_hint: (1, 0.2)
            title: 'New Playlist'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_type('Cancel')]]
            elevation: 10
        MDTextFieldRound:
            id: id_name
            size_hint: (1, 0.1)
            icon_type: "without"
            hint_text: "Playlist name"
            normal_color: [0, 0, 0, 0.1]
            foreground_color: [0, 0, 0, 1]
            on_text: root.enable_buttons(self.text)
        ScrollView:
            size_hint: (1, 0.7)
            MDList:
                id: id_types
    '''
)


class TypeWidget(Screen):
    ABORT = "Cancel"
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
            b = OneLineListItem(text=x, on_release=self.dispatch_on_type)
            self.buttons.append(b)
            self.ids.id_types.add_widget(b)
        b = OneLineListItem(text=TypeWidget.ABORT, on_release=self.dispatch_on_type)
        self.ids.id_types.add_widget(b)

    def on_type(self, name, type, confclass):
        Logger.debug("On type called %s, %s, %s" % (name, type, str(confclass)))

    def enable_buttons(self, text, *args, **kwargs):
        dis = not text or not re.search(r"[A-Za-z]", text)
        for b in self.buttons:
            b.disabled = dis

    def dispatch_on_type(self, widget):
        self.manager.remove_widget(self)
        if isinstance(widget, str):
            text = widget
        else:
            text = widget.text
        self.dispatch("on_type", self.ids.id_name.text, text, TypeWidget.TYPES.get(text))
