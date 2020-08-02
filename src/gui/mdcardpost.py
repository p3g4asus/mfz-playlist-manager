# from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import (BooleanProperty, ListProperty, StringProperty)
from kivymd.uix.button import MDIconButton
from kivymd.uix.card import MDCardSwipe, MDCardSwipeFrontBox

ICON_IMAGE = '__image__'
ICON_TRASH = '__trash__'

Builder.load_string(
    """
<CardPostImage2>
    spacing: dp(5)
    padding: dp(5)
    orientation: 'horizontal'
    size_hint_y: None

    SmartTileWithLabel:
        pos_hint: {'top': 1}
        source: root.source
        text: ' %s' % root.tile_text
        color: root.tile_text_color
        size_hint_y: None
        # size_hint_x: None
        # width: self.ids.img.width
        font_style: root.tile_font_style
        height: root.height
        keep_ratio: root.keep_ratio
        allow_stretch: root.allow_stretch
        id: id_c1
        on_release: root.callback('__image__')
    BoxLayout:
        orientation: 'vertical'
        id: id_c2
        size_hint_y: None
        pos_hint: {'top': 1}
        height: root.height
        MDLabel:
            pos_hint: {'top': 1}
            text: root.text_post
            size_hint_y: None
            halign: 'justify'
            valign: 'top'
            height: int(root.height / 150 * 110)
            id: id_c21
            text_size: self.width - dp(20), self.height - dp(5)
        BoxLayout:
            size_hint_y: None
            height: int(root.height / 150 * 40)
            pos_hint: {'top': 1}
            id: box_buttons

<SwipeToDeleteItem>:
    size_hint_y: None
    height: dp(335)
    anchor: 'right'
    swipe_distance: 150
    max_swipe_x: 0.92

    MDCardSwipeLayerBox:
        AnchorLayout:
            anchor_x: 'right'
            anchor_y: 'center'
            # Content under the card.
            MDIconButton:
                icon: "trash-can"
                pos_hint: {"center_y": .5, "right": 1}
                on_release: root.callback(root, '__trash__')

    CardPostImage2:
        id: id_card
        height: root.height
        source: root.source
        text_post: root.text_post
        tile_text: root.tile_text
        tile_font_style: root.tile_font_style
        tile_text_color: root.tile_text_color
        keep_ratio: root.keep_ratio
        allow_stretch: root.allow_stretch
        buttons: root.buttons
    """
)


class CardPostImage2(MDCardSwipeFrontBox):
    source = StringProperty()
    text_post = StringProperty()
    tile_text = StringProperty("Title")
    tile_font_style = StringProperty("H5")
    tile_text_color = ListProperty([1, 1, 1, 1])
    buttons = ListProperty()
    keep_ratio = BooleanProperty(None, allownone=True)
    allow_stretch = BooleanProperty(None, allownone=True)

    def __init__(self, **kwargs):
        self.register_event_type('on_button_click')
        super().__init__(**kwargs)
        # self.bind(buttons=self.on_buttons)
        self.add_buttons()

    def add_buttons(self):
        for name_icon in self.buttons:
            self.ids.box_buttons.add_widget(
                MDIconButton(
                    icon=name_icon,
                    on_release=lambda x, y=name_icon: self.callback(y),
                )
            )

    def on_buttons(self, inst, val):
        while self.ids.box_buttons.children:
            self.ids.box_buttons.remove_widget(self.ids.box_buttons.children[0])
        self.add_buttons()

    def callback(self, ico_name):
        self.dispatch('on_button_click', ico_name)

    def on_button_click(self, ico_name):
        pass


class SwipeToDeleteItem(MDCardSwipe):
    source = StringProperty()
    text_post = StringProperty()
    tile_text = StringProperty("Title")
    tile_font_style = StringProperty("H5")
    tile_text_color = ListProperty([1, 1, 1, 1])
    buttons = ListProperty()
    keep_ratio = BooleanProperty(None, allownone=True)
    allow_stretch = BooleanProperty(None, allownone=True)

    def __init__(self, **kwargs):
        self.register_event_type('on_button_click')
        super().__init__(**kwargs)
        self.ids.id_card.bind(on_button_click=self.callback)

    def callback(self, inst, ico_name):
        self.dispatch('on_button_click', ico_name)

    def on_button_click(self, ico_name):
        pass
