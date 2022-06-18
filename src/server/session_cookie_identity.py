"""Identity policy for storing info into aiohttp_session session.

aiohttp_session.setup() should be called on application initialization
to configure aiohttp_session properly.
"""
from aiohttp_session import get_session, SESSION_KEY
from aiohttp_security.abc import AbstractIdentityPolicy
import json
import logging
from uuid import uuid4
import hashlib

from common.const import INVALID_SID

_LOGGER = logging.getLogger(__name__)


class SessionCookieIdentityPolicy(AbstractIdentityPolicy):

    def __init__(self, sid_key='AIOHTTP_SECURITY', login_key='AIOHTTP_LOGIN', user_key='AIOHTTP_USER', max_age=365 * 86400):
        self._sid_key = sid_key
        self._login_key = login_key
        self._user_key = user_key
        self._max_age = max_age

    async def identify(self, request):
        request[self._sid_key] = None
        csid = request.cookies.get(self._sid_key)
        clogins = request.cookies.get(self._login_key, '{}')
        if clogins:
            try:
                clogin = json.loads(clogins)
            except Exception:
                clogin = dict()
        tokenrefresh = 0
        session = await get_session(request)
        dsid = clogin.get('sid', 'a')
        sid = None
        if session.identity:
            sid = session.identity
            _LOGGER.debug(f'Session identity is {session.identity}')
            if csid != sid:
                tokenrefresh = -1
        elif session.new:
            _LOGGER.debug(f'Session is NEW and no identity dsid={dsid} csid={csid}')
            if csid:
                sid = csid
            elif len(dsid) > 1:
                sid = csid = dsid
            if sid == csid and csid:
                tokenrefresh = 1
                session.set_new_identity(csid)
                _LOGGER.debug(f'Setting new idetity as {csid} in key')
                request[SESSION_KEY] = None
                request[self._sid_key] = sid
                session = await get_session(request)
            else:
                csid = sid = dsid = str(uuid4())
                tokenrefresh = -1
        else:
            tokenrefresh = -1
            if len(dsid) > 1:
                csid = sid = dsid
            elif csid:
                sid = dsid = csid
            else:
                csid = sid = dsid = str(uuid4())
        login = json.loads(session.get(self._login_key, '{}'))
        idval = dict(tokenrefresh=tokenrefresh, sid=sid, dsid=dsid, csid=csid, login=login, clogin=clogin)
        idvals = json.dumps(idval)
        _LOGGER.debug(f'Identify {idvals}')
        return idval

    async def remember(self, request, response, logins, **kwargs):
        session = await get_session(request)
        login = json.loads(session.get(self._login_key, '{}') if logins == INVALID_SID else logins)
        if not login:
            return None
        clogins = request.cookies.get(self._login_key)
        if not clogins and logins == INVALID_SID:
            return
        elif 'max_age' not in kwargs:
            kwargs['max_age'] = self._max_age
        token = str(uuid4())
        clogin = login.copy()
        clogin['token'] = token
        login['token'] = hashlib.sha256(token.encode('utf-8')).hexdigest()
        if not session.identity and session.new:
            session.set_new_identity(login.get('sid'))
        logins = json.dumps(login)
        clogins = json.dumps(clogin)
        _LOGGER.debug(f"Clogin={clogins} login={logins} max_age={kwargs.get('max_age')}")
        session[self._login_key] = logins
        response.del_cookie(self._login_key)
        response.del_cookie(self._sid_key)
        response.del_cookie(self._user_key)
        response.set_cookie(self._login_key, clogins, max_age=kwargs.get('max_age'), httponly=True)
        response.set_cookie(self._sid_key, login.get('sid'), httponly=True)
        response.set_cookie(self._user_key, login.get('uid'))

    async def forget(self, request, response):
        session = await get_session(request)
        session.pop(self._login_key, None)
        response.del_cookie(self._login_key)
        response.del_cookie(self._sid_key)
        response.del_cookie(self._user_key)
