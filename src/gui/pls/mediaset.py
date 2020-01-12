import re

from kivy.lang import Builder
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout

from common.const import CMD_MEDIASET_BRANDS, CMD_MEDIASET_LISTINGS
from common.playlist import PlaylistMessage

from .medrai import MedRaiBrandItemRV, MedRaiConfScreen

Builder.load_string(
    '''
#:import ButtonDatePicker gui.buttondatepicker.ButtonDatePicker
<MediasetListingsRequestWidget>:
    orientation: 'horizontal'
    padding: dp(15)
    MDLabel:
        theme_text_color: "Primary"
        text: 'Get listings'
    ButtonDatePicker:
        dateformat: '%d/%m/%Y'
        nulltext: 'Unset'
        id: id_datefrom
        on_date_picked: root.on_new_date(self.date)
    '''
)


class MediasetListingsRequestWidget(BoxLayout):
    callback = ObjectProperty(None, allownone=True)

    def on_new_date(self, dt):
        if self.callback:
            self.callback(PlaylistMessage(cmd=CMD_MEDIASET_LISTINGS, datestart=int(dt.timestamp() * 1000)))


class MediasetBrandItemRV(MedRaiBrandItemRV):
    def brandinfo2gui(self, b):
        self.text = b['desc'] if 'desc' in b else b['title']
        t = b['title'] + '/' if 'desc' in b else ''
        self.secondary_text = t + str(b['id'])


class MediasetConfScreen(MedRaiConfScreen):
    def get_name_id(self):
        return 'mediaset'

    def get_subbrand_list_class(self):
        return MediasetBrandItemRV

    def get_listings_request_widget_class(self):
        return MediasetListingsRequestWidget

    def get_brand_id_tf_hint(self):
        return 'Brand ID'

    def get_brand_id_tf_helper(self):
        return 'Brand ID should be numeric'

    def get_brand_id_tf_isgood(self, inst, filt):
        try:
            if re.search(r"^https://www.mediasetplay.mediaset.it/[^/]+/[^/]+$", filt):
                mo = re.search(r"_b([0-9]+)$", filt)
                if mo:
                    filt = mo.group(1)
                    inst.text = filt
                    self.brand_confirmed()
            int(filt)
            return True
        except ValueError:
            return False

    def get_brand_confirmed_action(self, brand):
        return PlaylistMessage(cmd=CMD_MEDIASET_BRANDS, brand=int(brand))

    def get_brand_rv_class_name(self):
        return 'MediasetBrandItemRV'


ConfWidget = MediasetConfScreen
