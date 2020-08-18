from datetime import datetime, timedelta

from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import NumericProperty, ObjectProperty
from kivy.uix.screenmanager import Screen

Builder.load_string(
    '''
#:import ButtonDatePicker gui.buttondatepicker.ButtonDatePicker
<UpdateWidget>:
    name: 'update'
    BoxLayout:
        spacing: dp(25)
        height: self.minimum_height
        orientation: 'vertical'
        MDToolbar:
            id: id_toolbar
            pos_hint: {'top': 1}
            title: 'Update dates'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.manager.remove_widget(root)]]
            right_action_items: [["run-fast", lambda x: root.dispatch_update(True)], ["update", lambda x: root.dispatch_update(False)]]
            elevation: 10
            size_hint_x: 1
            size_hint_y: None
            height: dp(60)
        AnchorLayout:
            ButtonDatePicker:
                size_hint: (0.85, 0.25)
                id: id_datefrom
                font_size: "12sp"
                dateformat: 'From: %d/%m/%Y'
                on_date_picked: root.check_dates(self, self.date)
        AnchorLayout:
            ButtonDatePicker:
                size_hint: (0.85, 0.25)
                id: id_dateto
                dateformat: 'To: %d/%m/%Y'
                font_size: "12sp"
                nulltext: ''
                on_date_picked: root.check_dates(self, self.date)
        BoxLayout:
            orientation: 'vertical'
    '''
)


class UpdateWidget(Screen):
    box_buttons_ref = ObjectProperty()
    datefrom = NumericProperty(None, allownone=True)

    def __init__(self, **kwargs):
        self.register_event_type('on_update')
        super(UpdateWidget, self).__init__(**kwargs)
        dt = datetime.now() - timedelta(days=60) if not self.datefrom else datetime.fromtimestamp(self.datefrom / 1000)
        self.ids.id_datefrom.set_date(dt)
        self.ids.id_dateto.set_date(datetime.now())

    def check_dates(self, inst, dt):
        if self.ids.id_dateto.date < self.ids.id_datefrom.date:
            if inst == self.ids.id_dateto.__self__:
                self.ids.id_datefrom.set_date(self.ids.id_dateto.date)
            else:
                self.ids.id_dateto.set_date(self.ids.id_datefrom.date)

    def on_update(self, df, dt):
        Logger.debug("On update called %s-%s" % (str(df), str(dt)))

    def dispatch_update(self, fast):
        self.manager.remove_widget(self)
        self.dispatch('on_update',
                      self.ids.id_datefrom.date if not fast else datetime(1980, 1, 1),
                      self.ids.id_dateto.date if not fast else datetime.now())
