from kivy.lang import Builder
from kivy.logger import Logger
from kivymd.uix.picker import MDDatePicker
from kivymd.uix.button import MDRaisedButton
from kivy.properties import ObjectProperty, StringProperty
from datetime import date

Builder.load_string(
    '''
<DatePicker>:
    text: "Date"
    pos_hint: {"center_x": .5}
    opposite_colors: True
    on_release: self.show_date_picker()
    '''
)


class DatePicker(MDRaisedButton):
    dateformat = StringProperty("%Y-%m-%d")
    startdate = StringProperty()
    date = ObjectProperty(date.today())

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_date_picked')
        super(DatePicker, self).__init__(*args, **kwargs)
        if not self.startdate:
            self.startdate = date.today().strftime(self.dateformat)
        self.apply_date(self.date)

    def show_date_picker(self):
        MDDatePicker(self.apply_date,
                     self.date.year, self.date.month, self.date.day).open()

    def on_date_picked(self, inst, dateo):
        Logger.debug("On Date Picked %s" % dateo.strftime(self.dateformat))

    def apply_date(self, dateo):
        self.date = dateo
        self.text = dateo.strftime(self.dateformat)
        self.dispatch('on_date_picked', dateo)
