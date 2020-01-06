from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import DictProperty, ListProperty,\
    ObjectProperty, BooleanProperty
from kivy.uix.screenmanager import Screen
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.list import IRightBodyTouch, TwoLineAvatarIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox

from common.const import CMD_MEDIASET_BRANDS, CMD_MEDIASET_LISTINGS
from common.playlist import PlaylistMessage


Builder.load_string(
    '''
#:import MDIconButton kivymd.uix.button.MDIconButton
#:import MDList kivymd.uix.list.MDList
#:import ButtonDatePicker gui.buttondatepicker.ButtonDatePicker
<ListItemWithCheckbox>:
    on_release:
        root.ids.id_cb.active = not root.ids.id_cb.active
    BrandCheckbox:
        id: id_cb
        group: root.group
        active: root.active
        disabled: root.disabled
        on_active: root.dispatch_on_brand(self, self.active)
<ConfWidget>:
    name: 'conf_mediaset'
    GridLayout:
        cols: 1
        rows: 5
        spacing: dp(5)
        height: self.minimum_height
        MDToolbar:
            id: id_toolbar
            title: 'Mediaset configuration'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.manager.remove_widget(root)]]
            right_action_items: [["content-save", lambda x: root.dispatch_conf(root)]]
            elevation: 10
        GridLayout:
            size_hint: (1, 0.2)
            cols: 2
            rows: 2
            spacing: [dp(50), dp(0)]
            padding: [dp(25), dp(5)]
            height: self.minimum_height
            MDTextFieldRound:
                size_hint: (0.65, 1)
                id: id_brandtf
                icon_type: "right"
                icon_right: "subdirectory-arrow-left"
                icon_right_disabled: True
                hint_text: "Brand ID"
            MDIconButton:
                id: id_brandbt
                size_hint: (0.35, 1)
                on_release: root.brand_confirmed()
                icon: "subdirectory-arrow-left"
            MDTextFieldRound:
                size_hint: (0.65, 1)
                id: id_filtertf
                icon_type: "right"
                icon_right: "magnify"
                icon_right_disabled: False
                hint_text: "Filter"
            MDIconButton:
                id: id_filterbt
                size_hint: (0.35, 1)
                on_release: root.filter_brands()
                icon: "magnify"
        BoxLayout:
            size_hint: (1, 0.1)
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
        ScrollView:
            size_hint: (1, 0.5)
            MDList:
                id: id_listings
        ScrollView:
            size_hint: (1, 0.2)
            MDList:
                id: id_subbrands
    '''
)


class ListItemWithCheckbox(TwoLineAvatarIconListItem):
    brandinfo = DictProperty()
    active = BooleanProperty(False)
    group = ObjectProperty(None)

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_brand')
        super(ListItemWithCheckbox, self).__init__(*args, **kwargs)
        b = self.brandinfo
        self.text = b['desc'] if 'desc' in b else b['title']
        t = b['title'] + '/' if 'desc' in b else ''
        self.secondary_text = t + str(b['id'])

    def dispatch_on_brand(self, inst, active):
        Logger.debug("Mediaset: Dispatching on brand")
        self.dispatch("on_brand", self.brandinfo, active)

    def on_brand(self, brandinfo, active):
        Logger.debug("On brand %s %d" % (str(brandinfo), active))


class BrandCheckbox(MDCheckbox, IRightBodyTouch):
    def __init__(self, *args, **kwargs):
        if 'group' in kwargs and not kwargs['group']:
            del kwargs['group']
        super(BrandCheckbox, self).__init__(*args, **kwargs)

    def on_group(self, inst, group):
        # Logger.debug("Mediaset: group = %s %s %s" % (str(group), str(type(inst)), str(type(group))))
        if group and len(group):
            super(BrandCheckbox, self).on_group(self, group)


class ConfWidget(Screen):
    startconf = DictProperty()
    conf = DictProperty()
    current_brand = DictProperty()
    current_subbrands = ListProperty([])
    client = ObjectProperty()
    # manager = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super(ConfWidget, self).__init__(*args, **kwargs)
        self.on_startconf(self, self.startconf)
        self.ids.id_filtertf.icon_callback = self.filter_brands
        self.ids.id_brandtf.icon_callback = self.brand_confirmed
        self.ids.id_brandtf.bind(text=self.brand_check)
        # self.ids.id_filtertf.bind(text=self.filter_check)
        self._current_listings = []

    def on_startconf(self, inst, co):
        br = 0
        sbr = 0
        try:
            self.ids.id_listings.clear_widgets()
            self.ids.id_subbrands.clear_widgets()
            self.ids.id_filtertf.text = ''
            self.ids.id_brandtf.text = ''
        except (KeyError, AttributeError):
            return
        if 'brand' in self.startconf:
            self.current_brand = self.startconf['brand']
            self.ids.id_brandtf.text = str(self.current_brand['id'])
            li = ListItemWithCheckbox(brandinfo=self.startconf['brand'], active=True, on_brand=self.on_brand_listings_checked, group='brand')
            self.ids.id_listings.add_widget(li)
            br += 1
        if 'subbrands' in self.startconf:
            self.current_subbrands = self.startconf['subbrands']
            for sb in self.startconf['subbrands']:
                li = ListItemWithCheckbox(brandinfo=sb, active=True, on_brand=self.on_brand_subbrands_checked)
                self.ids.id_subbrands.add_widget(li)
                sbr += 1
        self.save_button_show(br and sbr)

    def save_button_show(self, show):
        if not show:
            self.ids.id_toolbar.right_action_items = []
        else:
            self.ids.id_toolbar.right_action_items = [["content-save", lambda x: self.dispatch_conf(self)]]

    def on_brand_subbrands_checked(self, inst, brandinfo, active):
        subs = self.current_subbrands
        if active:
            subs.append(brandinfo)
        else:
            for i in range(len(subs)):
                if subs[i]['id'] == brandinfo['id']:
                    del subs[i]
                    break
        self.save_button_show(len(subs) > 0)

    def on_brand_listings_checked(self, inst, brandinfo, active):
        Logger.debug("On_brand %s" % str(brandinfo))
        self.ids.id_subbrands.clear_widgets()
        self.current_subbrands = []
        if active:
            self.current_brand = brandinfo
            self.client.enqueue(PlaylistMessage(cmd=CMD_MEDIASET_BRANDS, brand=brandinfo['id']), self.on_new_brands_result)
        else:
            self.current_brand = dict()

    def on_new_date(self, dt):
        self.ids.id_listings.clear_widgets()
        self.ids.id_subbrands.clear_widgets()
        del self._current_listings[:]
        self.ids.id_brandtf.text = ''
        self.current_brand = dict()
        self.current_subbrands = []
        Logger.debug("Mediaset: Enqueuing %s dt = %s" % (CMD_MEDIASET_LISTINGS, str(dt)))
        self.client.enqueue(PlaylistMessage(cmd=CMD_MEDIASET_LISTINGS, datestart=int(dt.timestamp() * 1000)), self.on_new_listings_result)

    def filter_apply(self, sb):
        filt = self.ids.id_filtertf.text
        found = True
        if filt:
            f3 = filt.lower().split(' ')
            for x in sb.values():
                found = True
                y = str(x).lower()
                for i in f3:
                    if y.find(i) < 0:
                        found = False
                        break
                if found:
                    break
        return found

    def fill_listings(self, lst):
        self._current_listings = lst
        for sb in lst:
            if self.filter_apply(sb):
                a = self.current_brand and self.current_brand['id'] == sb['id']
                li = ListItemWithCheckbox(brandinfo=sb, active=a, on_brand=self.on_brand_listings_checked, group='brand')
                self.ids.id_listings.add_widget(li)

    def filter_brands(self, *args, **kwargs):
        self.ids.id_listings.clear_widgets()
        self.fill_listings(self._current_listings)

    def brand_check(self, inst, filt):
        Logger.debug("Brand check %s" % filt)
        try:
            int(filt)
            inst.icon_right_disabled = False
            inst.icon_right_color = [0, 0, 0, 1]
            self.ids.id_brandbt.disabled = False
        except ValueError:
            inst.icon_right_disabled = True
            inst.icon_right_color = [1, 1, 1, 1]
            self.ids.id_brandbt.disabled = True

    def filter_check(self, inst, filt):
        Logger.debug("Filter check %s" % filt)
        inst.icon_right_disabled = len(filt) < 4 or not len(filt)
        self.ids.id_filterbt.disabled = inst.icon_right_disabled

    def brand_confirmed(self, *args, **kwargs):
        bid = int(self.ids.id_brandtf.text)
        Logger.debug("Mediaset: brand_confirmed %d" % bid)
        for c in self.ids.id_listings.children:
            c.active = c.brandinfo['id'] == bid
        self.on_brand_listings_checked(
            None,
            dict(id=bid, title='', starttime=0),
            True)

    def fill_subbrands(self, lst):
        for sb in lst:
            if not self.current_brand['title']:
                self.current_brand['title'] = sb['title']
            li = ListItemWithCheckbox(brandinfo=sb, active=False, on_brand=self.on_brand_subbrands_checked)
            self.ids.id_subbrands.add_widget(li)

    async def on_new_listings_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv == 0:
            self.fill_listings(received.brands)
        else:
            toast("[E %d] %s" % (received.rv, received.err))

    async def on_new_brands_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv == 0:
            self.fill_subbrands(received.brands)
        else:
            toast("[E %d] %s" % (received.rv, received.err))

    def dispatch_conf(self, inst):
        self.conf = dict(
            brand=self.current_brand,
            subbrands=self.current_subbrands)
        Logger.debug("Mediaset: Dispatching conf %s" % str(self.conf))
        self.manager.remove_widget(self)
