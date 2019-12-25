import glob
import re
import traceback
from os.path import basename, dirname, isfile, join

from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.button import MDRaisedButton

Builder.load_string(
    '''
#:import MDTextFieldRound kivymd.uix.textfield.MDTextFieldRound
#:import MDRaisedButton kivymd.uix.button.MDRaisedButton
<TypeWidget>:
    orientation: 'vertical'
    id: idbox
    MDTextFieldRound:
        id: id_name
        icon_type: "without"
        hint_text: "Playlist name"
        normal_color: [0, 0, 0, .1]
        on_text: root.enable_buttons(self.text)
    MDRaisedButton:
        text: 'Abort'
        on_release: root.dispatch_on_type(self)
    '''
)


class TypeWidget(BoxLayout):
    ABORT = "Abort"
    types = ListProperty([])
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
            try:
                m = importlib.import_module("gui.pls."+x)
                clb = getattr(m, "ConfWidget")
                if clb:
                    TypeWidget.TYPES[x] = clb
            except Exception:
                Logger.warning(traceback.format_exc())

    def __init__(self, **kwargs):
        self.register_event_type('on_type')
        if not len(TypeWidget.TYPES):
            TypeWidget._get_pls_types()
        super(TypeWidget, self).__init__(**kwargs)
        self.buttons = []
        for x in self.types:
            b = MDRaisedButton(text=x, group='types', on_release=self.dispatch_on_type)
            self.buttons.append(b)

    def on_type(self, inst, name, type, confclass):
        Logger.debug("On type called %s, %s, %s" % (name, type, str(confclass)))

    def enable_buttons(self, text, *args, **kwargs):
        dis = not text or not re.search(r"[A-Za-z]", text)
        for b in self.buttons:
            b.disabled = dis

    def dispatch_on_type(self, widget):
        self.dispatch("on_type", self.ids.id_name.text, widget.text, TypeWidget.TYPES.get(widget.text))
