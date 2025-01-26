from typing import List
from common.utils import JSONAble

DEFAULT_TITLE = 'N/A'


class Brand(JSONAble):

    def __init__(self, id: int | str, title: str = DEFAULT_TITLE, desc: str = '', **_):
        self.id = id
        if isinstance(id, str):
            try:
                self.id = int(id)
            except Exception:
                pass
        self.title = title
        self.desc = desc

    def __getitem__(self, key):
        tt = vars(self)
        return tt[key]

    def __contains__(self, key):
        return key in vars(self)

    def toJSON(self, **kwargs):
        return vars(self)

    def __repr__(self):
        return f'[{self.id}] {self.title}/{self.desc}'

    def __eq__(self, value):
        if isinstance(value, (int, str)):
            return self.id == value
        return isinstance(value, Brand) and self.id == value.id

    @staticmethod
    def get_list_from_json(lstd: List[dict]) -> List["Brand"]:
        rv = []
        for dd in lstd:
            rv.append(Brand(**dd) if isinstance(dd, dict) else dd)
        return rv
