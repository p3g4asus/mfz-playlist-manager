from kivy.logger import Logger
from kivy.properties import ObjectProperty
from kivymd.uix.dialog import MDDialog
from .buttondatepicker import ButtonDatePicker
from datetime import datetime, timedelta


class UpdateWidget(MDDialog):
    box_buttons_ref = ObjectProperty()

    def __init__(self, **kwargs):
        self.register_event_type('on_update')
        self.register_event_type('on_exit')
        super(UpdateWidget, self).__init__(
            text="Please input update dates",
            title="Update Playlist",
            text_button_ok="Update",
            text_button_cancel="Cancel",
            events_callback=self.events_callback_f, **kwargs)
        dt = datetime.now() - timedelta(days=60)
        self.datefrom = ButtonDatePicker(on_date_picked=self.check_dates, dateformat='From %d/%m/%Y', date=dt)
        self.dateto = ButtonDatePicker(on_date_picked=self.check_dates, dateformat='To %d/%m/%Y', nulltext='')
        Logger.debug("Updatewidget: Adding buttons")
        self.box_buttons_ref = self.children[0].ids.box_buttons.__self__
        n = len(self.box_buttons_ref.children)
        self.box_buttons_ref.add_widget(self.dateto, index=n)
        Logger.debug("Updatewidget: Button added " + str(n))
        self.box_buttons_ref.add_widget(self.datefrom, index=n + 1)
        Logger.debug("Updatewidget: Button added " + str(n + 1))

    def check_dates(self, inst, dt):
        if self.dateto.date < self.datefrom.date:
            if inst == self.dateto:
                self.datefrom.apply_date(self.dateto.date)
            else:
                self.dateto.apply_date(self.datefrom.date)

    def on_exit(self):
        Logger.debug("On exit called")

    def on_update(self, df, dt):
        Logger.debug("On update called %s-%s" % (str(df), str(dt)))

    def events_callback_f(self, text, *args):
        if text == 'Update':
            self.dispatch('on_update', self.datefrom.date, self.dateto.date)
        else:
            self.dispatch('on_exit')
