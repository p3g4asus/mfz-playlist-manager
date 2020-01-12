import abc
from kivy.lang import Builder
from kivy.logger import Logger
from kivymd.uix.list import IRightBodyTouch, TwoLineAvatarIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox
from kivy.properties import DictProperty, StringProperty

Builder.load_string(
    '''
<BrandItem>:
    on_release: id_cb.trigger_action()
    BrandCheckbox:
        id: id_cb
        group: root.group
        disabled: root.disabled
        on_active: root.dispatch_on_brand(self, self.active)
    '''
)


class BrandItem(TwoLineAvatarIconListItem):
    brandinfo = DictProperty()
    group = StringProperty(None, allownone=True)

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_brand')
        if 'active' in kwargs:
            act = kwargs['active']
            del kwargs['active']
        else:
            act = False
        super(BrandItem, self).__init__(*args, **kwargs)
        self.set_active(act)

    @abc.abstractmethod
    def brandinfo2gui(self, b):
        pass

    def set_active(self, value):
        self.ids.id_cb.active = value

    def on_brandinfo(self, inst, v):
        self.brandinfo2gui(v)

    def dispatch_on_brand(self, inst, active):
        Logger.debug("BrandItem: Dispatching on brand")
        self.dispatch("on_brand", self.brandinfo, active)

    def on_brand(self, brandinfo, active):
        Logger.debug("BrandItem: On brand %s %d" % (str(brandinfo), active))


class BrandCheckbox(MDCheckbox, IRightBodyTouch):
    def __init__(self, *args, **kwargs):
        if 'group' in kwargs and not kwargs['group']:
            del kwargs['group']
        super(BrandCheckbox, self).__init__(*args, **kwargs)

    def on_group(self, inst, group):
        # Logger.debug("Mediaset: group = %s %s %s" % (str(group), str(type(inst)), str(type(group))))
        if group and len(group):
            super(BrandCheckbox, self).on_group(self, group)
