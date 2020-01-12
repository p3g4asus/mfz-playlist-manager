from abc import abstractmethod
from datetime import datetime

from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import (DictProperty, ListProperty, NumericProperty,
                             ObjectProperty)
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.screenmanager import Screen
from kivymd.toast.kivytoast.kivytoast import toast

from gui.branditem import BrandItem

Builder.load_string(
    '''
<MedRaiConfScreen>:
    name: 'conf_' + root.get_name_id()
    GridLayout:
        cols: 1
        rows: 5
        spacing: dp(5)
        height: self.minimum_height
        id: id_grid
        MDToolbar:
            id: id_toolbar
            title: root.get_name_id().title() + " Configuration"
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.manager.remove_widget(root)]]
            right_action_items: [["content-save", lambda x: root.dispatch_conf(root)]]
            elevation: 10
        GridLayout:
            size_hint: (1, 0.2)
            cols: 2
            rows: 2
            spacing: [dp(10), dp(0)]
            padding: [dp(20), dp(0)]
            MDTextField:
                id: id_brandtf
                hint_text: root.get_brand_id_tf_hint()
                error: True
                helper_text_mode: "on_error"
                helper_text: root.get_brand_id_tf_helper()
            MDIconButton:
                id: id_brandbt
                on_release: root.brand_confirmed()
                icon: "subdirectory-arrow-left"
            MDTextField:
                id: id_filtertf
                hint_text: "Filter"
            MDIconButton:
                id: id_filterbt
                on_release: root.filter_brands()
                icon: "magnify"
        RecycleView:
            size_hint: (1, 0.5)
            id: id_listings
            title: 'Listings'
            viewclass: root.get_brand_rv_class_name()
            RecycleBoxLayout:
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'
        ScrollView:
            size_hint: (1, 0.2)
            MDList:
                id: id_subbrands
    '''
)


class MedRaiBrandItemRV(BrandItem, RecycleDataViewBehavior):
    index = NumericProperty(-1)

    def __init__(self, *args, **kwargs):
        self._on_brand = None
        super(MedRaiBrandItemRV, self).__init__(*args, **kwargs)

    def refresh_view_attrs(self, rv, index, dbitem):
        ''' Catch and handle the view changes '''
        Logger.debug("MedRaiBrandItemRV: r_v_a data = %s" % str(dbitem))
        self.index = index
        self.group = dbitem['group']
        self.brandinfo = dbitem['brandinfo']
        if self._on_brand:
            self.unbind(on_brand=self._on_brand)
        self.set_active(dbitem['is_brand_active'](self.brandinfo))
        self._on_brand = dbitem['result']
        self.bind(on_brand=self._on_brand)
        return super(MedRaiBrandItemRV, self).refresh_view_attrs(
            rv, index, dbitem)


class MedRaiConfScreen(Screen):
    startconf = DictProperty()
    conf = DictProperty()
    current_brand = DictProperty()
    current_subbrands = ListProperty([])
    client = ObjectProperty()
    # manager = ObjectProperty()

    @abstractmethod
    def get_brand_rv_class_name(self):
        pass

    @abstractmethod
    def get_subbrand_list_class(self):
        pass

    @abstractmethod
    def get_listings_request_widget_class(self):
        pass

    @abstractmethod
    def get_brand_id_tf_hint(self):
        pass

    @abstractmethod
    def get_brand_id_tf_helper(self):
        pass

    @abstractmethod
    def get_brand_id_tf_isgood(self, inst, filt):
        pass

    @abstractmethod
    def get_brand_confirmed_action(self, brand):
        pass

    def __init__(self, *args, **kwargs):
        super(MedRaiConfScreen, self).__init__(*args, **kwargs)
        self.on_startconf(self, self.startconf)
        self.ids.id_filtertf.icon_callback = self.filter_brands
        self.ids.id_brandtf.icon_callback = self.brand_confirmed
        self.ids.id_brandtf.bind(text=self.brand_check)
        # self.ids.id_filtertf.bind(text=self.filter_check)
        self._current_listings = []
        cls = self.get_listings_request_widget_class()
        if cls:
            clsi = cls(callback=self.on_new_listings)
            clsi.size_hint = (1, 0.1)
            self.ids.id_grid.add_widget(clsi, index=2)

    def is_brand_active(self, b):
        return True if self.current_brand and\
            self.current_brand['id'] == b['id'] else False

    def on_startconf(self, inst, co):
        br = 0
        sbr = 0
        try:
            del self.ids.id_listings.data[:]
            self.ids.id_subbrands.clear_widgets()
            self.ids.id_filtertf.text = ''
            self.ids.id_brandtf.text = ''
        except (KeyError, AttributeError):
            return
        if 'brand' in self.startconf:
            self.current_brand = self.startconf['brand']
            self.ids.id_brandtf.error = False
            self.ids.id_brandtf.text = str(self.current_brand['id'])
            self.ids.id_listings.data.append(dict(
                brandinfo=self.startconf['brand'],
                result=self.on_brand_listings_checked,
                group='brand',
                is_brand_active=self.is_brand_active
            ))
            br += 1
        if 'subbrands' in self.startconf:
            self.current_subbrands = self.startconf['subbrands']
            for sb in self.startconf['subbrands']:
                li = self.get_subbrand_list_class()(
                    brandinfo=sb,
                    active=True,
                    on_brand=self.on_brand_subbrands_checked)
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

    # def on_brand_listings_checked(self, *args):
    #     for n, a in enumerate(args):
    #         Logger.debug("b_l_c %d) %s %s" % (n, str(type(a)), str(a)))

    def on_brand_listings_checked(self, inst, brandinfo, active):
        Logger.debug("On_brand %s" % str(brandinfo))
        self.ids.id_subbrands.clear_widgets()
        self.current_subbrands = []
        if active:
            self.current_brand = brandinfo
            self.client.enqueue(self.get_brand_confirmed_action(brandinfo['id']), self.on_new_brands_result)
        else:
            self.current_brand = dict()

    def on_new_listings(self, msg):
        del self.ids.id_listings.data[:]
        self.ids.id_subbrands.clear_widgets()
        del self._current_listings[:]
        self.ids.id_brandtf.text = ''
        self.current_brand = dict()
        self.current_subbrands = []
        Logger.debug("Rai: Enqueuing %s" % str(msg))
        self.client.enqueue(msg, self.on_new_listings_result)

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
                li = dict(brandinfo=sb,
                          result=self.on_brand_listings_checked,
                          group='brand',
                          is_brand_active=self.is_brand_active)
                self.ids.id_listings.data.append(li)

    def filter_brands(self, *args, **kwargs):
        del self.ids.id_listings.data[:]
        self.fill_listings(self._current_listings)

    def brand_check(self, inst, filt):
        Logger.debug("Brand check %s" % filt)
        if self.get_brand_id_tf_isgood(inst, filt):
            inst.icon_right_disabled = False
            inst.icon_right_color = [0, 0, 0, 1]
            self.ids.id_brandbt.disabled = False
            if inst.error:
                inst.error = False
                inst.on_text(inst, filt)
        else:
            inst.icon_right_disabled = True
            inst.icon_right_color = [1, 1, 1, 1]
            self.ids.id_brandbt.disabled = True
            if not inst.error:
                inst.error = True
                inst.on_text(inst, filt)

    def filter_check(self, inst, filt):
        Logger.debug("Filter check %s" % filt)
        inst.icon_right_disabled = len(filt) < 4 or not len(filt)
        self.ids.id_filterbt.disabled = inst.icon_right_disabled

    def brand_confirmed(self, *args, **kwargs):
        del self.ids.id_listings.data[:]
        self.ids.id_subbrands.clear_widgets()
        del self._current_listings[:]
        self.current_brand = dict()
        self.ids.id_filtertf.text = ''
        txt = self.ids.id_brandtf.text
        Logger.debug("MedRai: brand_confirmed %s" % txt)
        self.client.enqueue(self.get_brand_confirmed_action(txt), self.on_new_brand_info)

    def fill_subbrands(self, lst):
        for sb in lst:
            if not self.current_brand['title']:
                self.current_brand['title'] = sb['title']
            li = self.get_subbrand_list_class()(
                brandinfo=sb,
                active=False,
                on_brand=self.on_brand_subbrands_checked)
            self.ids.id_subbrands.add_widget(li)

    async def on_new_listings_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv == 0:
            del self.ids.id_listings.data[:]
            self.fill_listings(received.brands)
        else:
            toast("[E %d] %s" % (received.rv, received.err))

    async def on_new_brand_info(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv == 0:
            self.current_brand = dict(
                title=received.brands[0]['title'],
                id=received.brand,
                starttime=int(datetime.now().timestamp() * 1000))
            del self.ids.id_listings.data[:]
            self.fill_listings([self.current_brand])
            await self.on_new_brands_result(client, sent, received)
        else:
            toast("[E %d] %s" % (received.rv, received.err))

    async def on_new_brands_result(self, client, sent, received):
        if not received:
            toast("Timeout error waiting for server response")
        elif received.rv == 0:
            self.ids.id_subbrands.clear_widgets()
            self.fill_subbrands(received.brands)
        else:
            toast("[E %d] %s" % (received.rv, received.err))

    def dispatch_conf(self, inst):
        self.conf = dict(
            brand=self.current_brand,
            subbrands=self.current_subbrands)
        Logger.debug("Rai: Dispatching conf %s" % str(self.conf))
        self.manager.remove_widget(self)
