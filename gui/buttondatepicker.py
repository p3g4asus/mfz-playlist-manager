from kivy.lang import Builder
from kivy.logger import Logger
from kivymd.uix.picker import MDDatePicker
from kivymd.uix.button import MDRaisedButton
from kivy.properties import ObjectProperty, StringProperty, NumericProperty
from datetime import date, datetime

Builder.load_string(
    '''
<ButtonDatePicker>:
    nulltext: ''
    pos_hint: {"center_x": .5}
    opposite_colors: False
    on_release: self.show_date_picker()
    '''
)


class ButtonDatePicker(MDRaisedButton):
    dateformat = StringProperty("%Y-%m-%d")
    startdate = StringProperty()
    date = ObjectProperty(datetime.now())
    nulltext = StringProperty('Unset')
    _pickedstate = NumericProperty(0)

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_date_picked')
        super(ButtonDatePicker, self).__init__(*args, **kwargs)
        if self.startdate:
            self.date = datetime.strptime(self.startdate, self.dateformat)
        Logger.debug("Nulltext = %s (%d)" % (self.nulltext, len(self.nulltext)))
        self.apply_date(self.date)

    def show_date_picker(self):
        MDDatePicker(self.apply_date,
                     self.date.year, self.date.month, self.date.day).open()
        self._pickedstate = 1

    def on_date_picked(self, dateo):
        Logger.debug("On Date Picked %s" % dateo.strftime(self.dateformat))

    def apply_date(self, dateo):
        if isinstance(dateo, date):
            dateo = datetime.combine(dateo, datetime.now().time())
        elif isinstance(dateo, str):
            dateo = datetime.strptime(dateo, self.dateformat)
        if len(self.nulltext) and self._pickedstate == 0:
            self.text = self.nulltext
        elif self._pickedstate == 0:
            self.text = dateo.strftime(self.dateformat)
        elif self._pickedstate > 0:
            self._pickedstate = 0
            self.date = dateo
            self.text = dateo.strftime(self.dateformat)
            self.dispatch('on_date_picked', dateo)
