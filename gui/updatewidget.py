from kivy.lang import Builder
from kivy.logger import Logger
from kivy.uix.gridlayout import GridLayout

Builder.load_string(
    '''
#:import MDIconButton kivymd.uix.button.MDIconButton
#:import MDLabel kivymd.uix.label.MDLabel
#:import ButtonDatePicker gui.buttondatepicker.ButtonDatePicker
<UpdateWidget>:
    cols: 1
    rows: 3
    spacing: dp(5)
    height: self.minimum_height
    BoxLayout:
        size_hint: (1, 0.4)
        orientation: 'horizontal'
        MDLabel:
            theme_text_color: "Primary"
            text: 'From'
        ButtonDatePicker:
            nulltext: ''
            dateformat: '%d/%m/%Y'
            id: id_datefrom
    BoxLayout:
        size_hint: (1, 0.4)
        orientation: 'horizontal'
        MDLabel:
            theme_text_color: "Primary"
            text: 'To'
        ButtonDatePicker:
            nulltext: ''
            dateformat: '%d/%m/%Y'
            id: id_dateto
    BoxLayout:
        size_hint: (1, 0.2)
        orientation: 'horizontal'
        MDIconButton:
            id: id_updatebtn
            icon: 'update'
            on_release: root.dispatch_update()
        MDIconButton:
            id: id_exitbtn
            icon: 'close'
            on_release: root.dispatch_exit()
    '''
)


class UpdateWidget(GridLayout):
    def __init__(self, **kwargs):
        self.register_event_type('on_update')
        self.register_event_type('on_exit')
        super(UpdateWidget, self).__init__(**kwargs)
        self.ids.id_datefrom.bind(on_date_picked=self.check_dates)
        self.ids.id_dateto.bind(on_date_picked=self.check_dates)

    def check_dates(self, inst, dt):
        if self.ids.id_dateto.date < self.ids.id_datefrom.date:
            if inst == self.ids.id_dateto:
                self.ids.id_datefrom.apply_date(self.ids.id_dateto.date)
            else:
                self.ids.id_dateto.apply_date(self.ids.id_datefrom.date)

    def on_exit(self):
        Logger.debug("On exit called")

    def on_update(self, df, dt):
        Logger.debug("On update called %s-%s" % (str(df), str(dt)))

    def dispatch_update(self):
        self.dispatch('on_update', self.ids.id_datefrom.date, self.ids.id_dateto.date)

    def dispatch_exit(self):
        self.dispatch('on_exit')
