import re

from kivy.lang import Builder
from kivy.properties import ObjectProperty
from kivy.uix.anchorlayout import AnchorLayout

from common.const import CMD_RAI_CONTENTSET, CMD_RAI_LISTINGS
from common.playlist import PlaylistMessage
from gui.branditem import BrandItem

from .medrai import MedRaiBrandItemRV, MedRaiConfScreen

Builder.load_string(
    '''
<RaiListingsRequestWidget>:
    MDRaisedButton:
        on_release: root.on_click()
        text: 'Get all'
    '''
)


class RaiListingsRequestWidget(AnchorLayout):
    callback = ObjectProperty(None, allownone=True)

    def on_click(self):
        if self.callback:
            self.callback(PlaylistMessage(cmd=CMD_RAI_LISTINGS))


class RaiContentSetItem(BrandItem):
    def brandinfo2gui(self, b):
        self.secondary_text = b['id']
        self.text = b['title']


class RaiBrandItemRV(MedRaiBrandItemRV):
    def brandinfo2gui(self, b):
        self.text = b['desc'] if 'desc' in b else b['title']
        t = b['title'] + '/' if 'desc' in b else ''
        self.secondary_text = t + str(b['id'])


class RaiConfScreen(MedRaiConfScreen):

    def get_name_id(self):
        return 'rai'

    def get_subbrand_list_class(self):
        return RaiBrandItemRV

    def get_listings_request_widget_class(self):
        return RaiListingsRequestWidget

    def get_brand_id_tf_hint(self):
        return 'Prog ID'

    def get_brand_id_tf_helper(self):
        return 'Prog ID cannot be empty'

    def get_brand_id_tf_isgood(self, inst, filt):
        mo = re.search(r"^https://www.raiplay.it/programmi/([^/]+)$", filt)
        if mo:
            filt = mo.group(1)
            inst.text = filt
            self.brand_confirmed()
        return len(filt) > 0 and not re.search(r"[/:A-Z\-\.]", filt)

    def get_brand_confirmed_action(self, brand):
        return PlaylistMessage(cmd=CMD_RAI_CONTENTSET, brand=brand)

    def get_brand_rv_class_name(self):
        return 'RaiBrandItemRV'


ConfWidget = RaiConfScreen
