import glob
import re
import traceback
from os.path import basename, dirname, isfile, join, splitext

from kivy.lang import Builder
from kivy.logger import Logger
from kivy.uix.screenmanager import Screen

from kivymd.uix.list import OneLineListItem

Builder.load_string(
    '''
#:import MDList kivymd.uix.list.MDList
<TypeWidget>:
    name: 'type'
    BoxLayout:
        spacing: dp(5)
        height: self.minimum_height
        orientation: 'vertical'
        MDToolbar:
            pos_hint: {'top': 1}
            title: 'New Playlist'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_type('Cancel')]]
            elevation: 10
            size_hint_x: 1
            size_hint_y: None
            height: dp(60)
        BoxLayout:
            padding: [dp(30), dp(5)]
            size_hint_y: None
            height: dp(60)
            MDTextField:
                id: id_name
                icon_type: "without"
                error: True
                hint_text: "Playlist name"
                helper_text_mode: "on_error"
                helper_text: "Enter at least a letter"
                on_text: root.enable_buttons(self, self.text)
                size_hint_y: None
                height: dp(60)
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
        modules = glob.glob(join(dirname(__file__), "pls", "*.py*"))
        pls = [splitext(basename(f))[0] for f in modules if isfile(f) and not f.endswith('__init__.py')]
        for x in pls:
            if x not in TypeWidget.TYPES:
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
            b = OneLineListItem(text=x, on_release=self.dispatch_on_type, disabled=True)
            self.buttons.append(b)
            self.ids.id_types.add_widget(b)
        b = OneLineListItem(text=TypeWidget.ABORT, on_release=self.dispatch_on_type)
        self.ids.id_types.add_widget(b)

    def on_type(self, name, type, confclass):
        Logger.debug("On type called %s, %s, %s" % (name, type, str(confclass)))

    def enable_buttons(self, inst, text, *args, **kwargs):
        dis = not text or not re.search(r"[A-Za-z]", text)
        if inst.error and not dis:
            inst.error = False
            inst.on_text(inst, text)
        elif not inst.error and dis:
            inst.error = True
            inst.on_text(inst, text)
        for b in self.buttons:
            b.disabled = dis

    def dispatch_on_type(self, widget):
        self.manager.remove_widget(self)
        if isinstance(widget, str):
            text = widget
        else:
            text = widget.text
        self.dispatch("on_type", self.ids.id_name.text, text, TypeWidget.TYPES.get(text))
