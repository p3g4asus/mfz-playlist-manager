from kivy.lang import Builder
from kivy.logger import Logger
from kivy.uix.boxlayout import BoxLayout

Builder.load_string(
    '''
#:import MDFlatButton kivymd.uix.button.MDFlatButton
#:import MDLabel kivymd.uix.label.MDLabel
#:import DatePicker common.gui.DatePicker
<UpdateWidget>:
    orientation: 'vertical'
    BoxLayout:
        orientation: 'horizontal'
        MDLabel:
            theme_text_color: "Primary"
            text: 'From'
        DatePicker:
            dateformat: '%d/%m/%Y'
            id: id_datefrom
    BoxLayout:
        orientation: 'horizontal'
        MDLabel:
            theme_text_color: "Primary"
            text: 'To'
        DatePicker:
            dateformat: '%d/%m/%Y'
            id: id_dateto
    BoxLayout:
        orientation: 'horizontal'
        MDFlatButton:
            id: id_updatebtn
            text: 'Update'
            on_release: root.dispatch_update()
        MDFlatButton:
            id: id_exitbtn
            text: 'Exit'
            on_release: root.dispatch_exit()
    '''
)


class UpdateWidget(BoxLayout):
    def __init__(self, **kwargs):
        self.register_event_type('on_update')
        self.register_event_type('on_exit')
        super(UpdateWidget, self).__init__(**kwargs)
        self.ids.id_datefrom.bind(on_date_picked=self.check_dates)
        self.ids.id_dateto.bind(on_date_picked=self.check_dates)

    def check_dates(self, inst, dt):
        if self.ids.id_dateto.date < self.ids.id_datefrom.date:
            if inst == self.ids.id_dateto:
                self.ids.id_datefrom.set_date(self.ids.id_dateto.date)
            else:
                self.ids.id_dateto.set_date(self.ids.id_datefrom.date)

    def on_exit(self, inst):
        Logger.debug("On exit called")

    def on_update(self, inst, df, dt):
        Logger.debug("On update called %s-%s" % (str(df), str(dt)))

    def dispatch_update(self, inst):
        self.dispatch('on_update', self.ids.id_datefrom.date, self.ids.id_dateto.date)

    def dispatch_exit(self, inst):
        self.dispatch('on_exit')
