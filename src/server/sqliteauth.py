from aiohttp_security.abc import AbstractAuthorizationPolicy
import json
from time import time

from common.user_alc_ses import User
from server.db.base import UsesAlchemicDB


class SqliteAuthorizationPolicy(AbstractAuthorizationPolicy):
    def __init__(self, sqlitedb):
        super().__init__()
        self.db = sqlitedb

    @UsesAlchemicDB
    async def authorized_userid(self, identity, **kwargs):
        db = kwargs.get('db', self.db)
        db.sk('_err', None)
        """Retrieve authorized user id.
        Return the user_id of the user identified by the identity
        or 'None' if no user exists related to the identity.
        """
        try:
            dct = json.loads(identity)
            users: list[User] = await User.loadbyid(db, rowid=dct['rowid'])
            if users and users[0].username == dct['username']:
                return identity
        except Exception:
            pass
        return None

    async def permits(self, identity, permission, context=None):
        """Check user permissions.
        Return True if the identity is allowed the permission in the
        current context, else return False.
        """
        return self.authorized_userid(identity) is not None


async def check_credentials(db, username, password):
    users: list[User] = await User.loadbyid(db, username=username, password=password)
    if users:
        return json.dumps(dict(rowid=users[0].rowid, username=username, time=time()))
    else:
        return None


def identity2username(identity):
    if identity:
        try:
            dct = json.loads(identity)
            return dct['username']
        except Exception:
            pass
    return None


def identity2id(identity):
    if identity:
        try:
            dct = json.loads(identity)
            return dct['rowid']
        except Exception:
            pass
    return None
