import logging
import re
import traceback
from datetime import datetime
from functools import cmp_to_key
from urllib.parse import urlencode

import aiohttp

from common.const import (CMD_RAI_CONTENTSET, CMD_RAI_LISTINGS, MSG_BACKEND_ERROR,
                          MSG_RAI_INVALID_CONTENTSET, MSG_RAI_INVALID_PROGID,
                          MSG_NO_VIDEOS, RV_NO_VIDEOS)
from common.playlist import PlaylistItem

from .refreshmessageprocessor import RefreshMessageProcessor

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(RefreshMessageProcessor):

    def interested_plus(self, msg):
        return msg.c(CMD_RAI_CONTENTSET) or msg.c(CMD_RAI_LISTINGS)

    def get_name(self):
        return "rai"

    @staticmethod
    def contentSetUrl(progid):
        return 'https://www.raiplay.it/programmi/%s.json' % progid

    @staticmethod
    def programsUrl(progid, set):
        return ('https://www.raiplay.it/programmi/%s/%s.json') %\
            (progid, set)

    @staticmethod
    def relativeUrl(part):
        return ('https://www.raiplay.it%s') % part

    async def processContentSet(self, msg, userid, executor):
        progid = msg.f('brand', (str,))
        if progid:
            try:
                async with aiohttp.ClientSession() as session:
                    sets = dict()
                    prog = dict()
                    url = MessageProcessor.contentSetUrl(progid)
                    _LOGGER.debug("Rai: Getting processContentSet " + url)
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            js = await resp.json()
                            _LOGGER.debug("Rai: Rec processContentSet " + str(js))
                            prog['id'] = progid
                            prog['title'] = js['name']
                            prog['desc'] = ''
                            prog['channel'] = ''
                            try:
                                prog['desc'] = js['program_info']['description']
                                prog['channel'] = js['program_info']['channel']
                            except KeyError:
                                pass
                            for b in js['blocks']:
                                predesc = b['name'] + ' - ' if 'name' in b else ''
                                for s in b['sets']:
                                    if 'name' in s and 'id' in s and\
                                       s['id'].count('-') == 5:
                                        id = s['id']
                                        desc = predesc + s['name']
                                        sets[id] = dict(
                                            title=prog['title'],
                                            id=id,
                                            desc=desc
                                        )
                        else:
                            return msg.err(18, MSG_RAI_INVALID_PROGID)
                if not sets or not prog:
                    return msg.err(12, MSG_RAI_INVALID_PROGID)
                else:
                    return msg.ok(brands=list(sets.values()), prog=prog)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(15, MSG_RAI_INVALID_PROGID)

    def duration2int(self, val):
        mo = re.search(r"^([0-9]{2,}):([0-9]{2}):([0-9]{2})", val)
        if mo:
            return int(mo.group(1)) * 3600 + int(mo.group(2)) * 60 + int(mo.group(3))
        else:
            return 0

    async def get_duration_string(self, it, session):
        if 'duration' in it and len(it['duration']):
            return it['duration']
        else:
            try:
                async with session.get(it['video_url'] + '&output=45') as resp2:
                    if resp2.status == 200:
                        txt = await resp2.text()
                        mo = re.search(r'<duration>([0-9]{2,}:[0-9]{2}:[0-9]{2})<', txt)
                        if mo:
                            return mo.group(1)
            except Exception:
                _LOGGER.error(traceback.format_exc())
            return ''

    async def get_datepub(self, it, session):
        datepubs = '01-01-1980 00:01'
        try:
            url = MessageProcessor.relativeUrl(it["path_id"])
            async with session.get(url) as resp2:
                it2 = dict()
                if resp2.status == 200:
                    it2 = await resp2.json()
                    if ((updd := it2.get('track_info', dict()).get('update_date', '')) and (fmt := '%Y-%m-%d %H:%M')) or\
                       ((updd := it2.get('date_published', '')) and (fmt := '%d-%m-%Y %H:%M')):
                        if 'time_published' in it2:
                            datepubs = it2['time_published']
                        else:
                            datepubs = '00:01'
                        datepubs = updd + ' ' + datepubs
                _LOGGER.debug("Date trying %s rv=%d: %s" % (url, resp2.status, str(it2)))
        except Exception:
            _LOGGER.error(traceback.format_exc())
        _LOGGER.debug("Processing date: %s" % datepubs)
        datepubo = datetime.strptime(datepubs, fmt)
        datepubi = int(datepubo.timestamp() * 1000)
        datepub = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
        return (datepub, datepubi)

    async def entry2Program(self, it, session, progid, set, playlist):
        order = -1
        if 'season' in it and re.search(r'^[0-9]+$', it['season']) and\
           'episode' in it and re.search(r'^[0-9]+$', it['episode']):
            order = int(it['season']) * 100 + int(it['episode'])
        lnk = it.get('weblink')
        conf = dict(progid=progid,
                    set=set,
                    pageurl=MessageProcessor.relativeUrl(lnk) if lnk else None,
                    path=it["path_id"] if "path_id" in it else '',
                    order=order)
        title = it['name'] if 'name' in it else it['episode_title']
        uid = it['id']
        img = None
        keys = ["landscape",
                "portrait",
                "square",
                "landscape43",
                "portrait43",
                "portrait_logo",
                "landscape_logo"]
        try:
            imgs = it['images']
            for k in keys:
                if k in imgs and len(imgs[k]):
                    img = MessageProcessor.relativeUrl(imgs[k])
                    break
        except Exception:
            img = None
        dur = self.duration2int(await self.get_duration_string(it, session))
        link = it['video_url']
        (datepub, datepubi) = await self.get_datepub(it, session)
        return (PlaylistItem(
            link=link,
            title=title,
            datepub=datepub,
            dur=dur,
            conf=conf,
            uid=uid,
            img=f'?{urlencode(dict(link=img))}',
            playlist=playlist
        ), datepubi)

    async def processPrograms(self, msg, datefrom=0, dateto=33134094791000, conf=dict(), playlist=None, userid=None, executor=None):
        try:
            progid = conf['brand']['id']
            sets = [s['id'] for s in conf['subbrands']]
        except (KeyError, AttributeError):
            _LOGGER.error(traceback.format_exc())
            return msg.err(11, MSG_BACKEND_ERROR)
        if sets and progid:
            try:
                async with aiohttp.ClientSession() as session:
                    programs = dict()
                    for set in sets:
                        url = MessageProcessor.programsUrl(progid, set)
                        _LOGGER.info(f'Getting {url}')
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                js = await resp.json()
                                for it in js['items']:
                                    try:
                                        (pr, datepubi) = await self.entry2Program(it, session, progid, set, playlist)
                                        _LOGGER.debug("Found [%s] = %s" % (pr.uid, str(pr)))
                                        if pr.uid not in programs and datepubi >= datefrom and\
                                                (datepubi <= dateto or dateto < datefrom):
                                            programs[pr.uid] = pr
                                            _LOGGER.debug("Added [%s] = %s" % (pr.uid, str(pr)))
                                    except Exception:
                                        _LOGGER.error(traceback.format_exc())
                            else:
                                return msg.err(12, MSG_BACKEND_ERROR)
                    if not len(programs):
                        return msg.err(RV_NO_VIDEOS, MSG_NO_VIDEOS)
                    else:
                        programs = list(programs.values())

                        def compare_items(a, b):
                            if a.conf['order'] > 0 and b.conf['order'] > 0:
                                return a.conf['order'] - b.conf['order']
                            elif a.conf['order'] > 0:
                                return 1
                            elif b.conf['order'] > 0:
                                return -1
                            elif a.datepub < b.datepub:
                                return -1
                            elif a.datepub > b.datepub:
                                return 1
                            else:
                                return 0
                        programs.sort(key=cmp_to_key(compare_items))
                        return msg.ok(items=programs)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(16, MSG_RAI_INVALID_CONTENTSET)

    def processSingleListing(self, js):
        rv = dict()
        if 'contents' in js:
            for content in js['contents']:
                rv.update(self.processSingleListing(content))
        elif 'path_id' in js and 'name' in js:
            mo = re.search(r"/([^A-Z\-\./]+)\.json$", js['path_id'])
            if mo:
                idv = mo.group(1)
                rv[idv] = dict(
                    id=idv,
                    title=js['name'],
                    starttime=int(datetime.now().timestamp() * 1000)
                )
        return rv

    async def processListings(self, msg, userid, executor):
        try:
            async with aiohttp.ClientSession() as session:
                programs = dict()
                rurls = ['/tipologia/film', '/tipologia/bambini', '/tipologia/programmi', '/tipologia/sport', '/tipologia/serieitaliane']
                for rurl in rurls:
                    try:
                        url = MessageProcessor.relativeUrl(rurl) + '/index.json'
                        _LOGGER.debug("Rai: Getting processListings " + url)
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                js = await resp.json()
                                _LOGGER.debug("Rai: Rec processListings " + str(js))
                                programs.update(self.processSingleListing(js))
                    except Exception:
                        _LOGGER.warning(traceback.format_exc())
            if not programs:
                return msg.err(12, MSG_BACKEND_ERROR)
            else:
                programs = list(programs.values())
                programs.sort(key=lambda item: item['title'])
                return msg.ok(brands=programs)
        except Exception:
            _LOGGER.error(traceback.format_exc())
            return msg.err(11, MSG_BACKEND_ERROR)

    async def getResponse(self, msg, userid, executor):
        if msg.c(CMD_RAI_CONTENTSET):
            return await self.processContentSet(msg, userid, executor)
        elif msg.c(CMD_RAI_LISTINGS):
            return await self.processListings(msg, userid, executor)
        else:
            return None
