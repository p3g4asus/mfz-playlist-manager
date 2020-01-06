import abc
import json


class JSONAble(abc.ABC):
    @abc.abstractmethod
    async def toJSON(self):
        pass


class Fieldable:
    def __str__(self):
        return str(vars(self))

    def f(self, name, typetuple=None):
        try:
            a = getattr(self, name)
        except AttributeError:
            a = None
        return None if typetuple and (a is None or not isinstance(a, typetuple)) else a


class MyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, JSONAble):
            return obj.toJSON()
        else:
            return super().default(obj)


class AbstractMessageProcessor(abc.ABC):
    def __init__(self, db):
        self.db = db

    @abc.abstractmethod
    def interested(self, msg):
        pass

    @abc.abstractmethod
    async def process(self, ws, msg, userid):
        pass
