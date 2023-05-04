from aiohttp_security.abc import AbstractAuthorizationPolicy
import hashlib


class DictAuthorizationPolicy(AbstractAuthorizationPolicy):
    def __init__(self):
        super().__init__()

    async def authorized_userid(self, dct):
        clogin = dct.get('clogin', dict())
        login = dct.get('login', dict())
        csid = dct.get('csid', 'a')
        sid = dct.get('sid', 'b')
        dsid = login.get('sid', 'c')
        tokenrefresh = dct.get('tokenrefresh', -2)
        hextoken = login.get('token', 'a')
        # Nota Bug browsers basati su chromium su android: a volte anche se il browser è stato chiuso con l'utente loggato
        # questo if risulterà falso perchè fallisce il controllo sha sul token. Questo perchè il valore del cookie inviato
        # dal browser non è quello ottenuto nella precedente sessione
        # dopo l'ultimo refresh del token ma quello precedente. Questo perchè probabilmente il db dei cookie di chromium
        # per android non viene committato al momento della modifica del cookie ma in maniera asincrona più tardi.
        # Se il browser viene però killato prima di effettuare il commit della transaziione di modifica nel db dei cookie,
        # il valore del cookie rimane il precedente. Questa cosa con Firefox (basato non su chromium ma su gecko) non succede e
        # tutto funziona a dovere.
        if tokenrefresh >= 0 and dsid == login.get('sid', 'b') and dsid == sid and csid == sid and\
           login.get('uid', 'a') == clogin.get('uid', 'b') and\
           hashlib.sha256(clogin.get('token', 'a').encode('utf-8')).hexdigest() == hextoken:
            return login.get('uid'), hextoken if not tokenrefresh else ''
        else:
            return sid if len(sid) > 1 else csid if len(csid) > 1 else dsid, None

    async def permits(self, identity, permission, context=None):
        """Check user permissions.
        Return True if the identity is allowed the permission in the
        current context, else return False.
        """
        return isinstance(self.authorized_userid(identity), int)


async def check_credentials(db, username, password):
    async with db.execute(
        '''
        SELECT U.rowid as rowid,
               U.username as username,
               U.password as password from user as U WHERE username=?
        ''', (username,)
    ) as cursor:
        row = await cursor.fetchone()
        if row and row['password'] == password:
            return row['rowid']
    return None


async def identity2username(db, identity):
    if identity and (isinstance(identity, int) or identity.get('uid')):
        try:
            async with db.execute(
                    '''
                    SELECT U.rowid as rowid,
                        U.username as username
                        from user as U WHERE rowid=?
                    ''', (abs(identity) if isinstance(identity, int) else identity.get('uid'),)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row['username']
        except Exception:
            pass
    return None


def identity2id(identity):
    if identity:
        if isinstance(identity, int):
            return -identity if identity < 0 else identity
        elif isinstance(identity, dict):
            return int(identity.get('uid', -1))
    return None
