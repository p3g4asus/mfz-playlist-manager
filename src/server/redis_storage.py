from aiohttp_session.redis_storage import RedisStorage
from aiohttp import web
from typing import Optional


class RedisKeyStorage(RedisStorage):
    def load_cookie(self, request: web.Request) -> Optional[str]:
        cookie = super(RedisKeyStorage, self).load_cookie(request)
        if cookie is None and self._cookie_name in request:
            return request[self._cookie_name]
        else:
            return cookie
