from abc import ABC, abstractmethod

from server.db.base import AlchemicDB


class AbstractMessageProcessor(ABC):
    def __init__(self, db: AlchemicDB, **kwargs):
        self.db: AlchemicDB = db
        self.status = dict()

    @abstractmethod
    def interested(self, msg):
        pass

    @abstractmethod
    async def process(self, ws, msg, userid, executor):
        pass
