from aiohttp_security.abc import AbstractAuthorizationPolicy
import json
from time import time


class SqliteAuthorizationPolicy(AbstractAuthorizationPolicy):
    def __init__(self, sqlitedb):
        super().__init__()
        self.db = sqlitedb

    async def authorized_userid(self, identity):
        """Retrieve authorized user id.
        Return the user_id of the user identified by the identity
        or 'None' if no user exists related to the identity.
        """
        try:
            dct = json.loads(identity)
            async with self.db.execute(
                '''
                select count(*) from user WHERE username=? AND rowid=?
                ''', dct['username'], dct['rowid']
            ) as cursor:
                n = await cursor.fetchone()[0]
                if n:
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
    async with db.execute(
        '''
        select * from user WHERE username=?
        ''', username
    ) as cursor:
        row = await cursor.fetchone()
        if row and row['password'] == password:
            return json.dumps(
                dict(rowid=row['rowid'], username=username, time=time()))
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
