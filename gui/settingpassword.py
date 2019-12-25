from kivy.uix.settings import SettingString
from kivy.uix.label import Label
from kivy.lang import Builder


class PasswordLabel(Label):
    pass


Builder.load_string('''
<SettingPassword>:
    PasswordLabel:
        text: '(set)' if root.value else '(unset)'
        pos: root.pos
        font_size: '15sp'
Button:
    on_release: app.open_settings()
''')


class SettingPassword(SettingString):
    def _create_popup(self, instance):
        super(SettingPassword, self)._create_popup(instance)
        self.textinput.password = True

    def add_widget(self, widget, *largs):
        if self.content is None:
            super(SettingString, self).add_widget(widget, *largs)
        if isinstance(widget, PasswordLabel):
            return self.content.add_widget(widget, *largs)
