import logging
import re
import traceback
from datetime import datetime

import aiohttp

from common.const import (CMD_RAI_CONTENTSET, MSG_BACKEND_ERROR,
                          MSG_RAI_INVALID_CONTENTSET, MSG_RAI_INVALID_PROGID)
from common.playlist import PlaylistItem

from .refreshmessageprocessor import RefreshMessageProcessor

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(RefreshMessageProcessor):

    def interested_plus(self, msg):
        return msg.c(CMD_RAI_CONTENTSET)

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

    async def processContentSet(self, msg, userid):
        progid = msg.f('progid', (str,))
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
                                pretitle = b['name'] + ' - ' if 'name' in b else ''
                                for s in b['sets']:
                                    if 'name' in s and 'id' in s and\
                                       s['id'].count('-') == 5:
                                        id = s['id']
                                        title = pretitle + s['name']
                                        desc = s['path_id']
                                        sets[id] = dict(
                                            title=title,
                                            id=id,
                                            desc=desc
                                        )
                        else:
                            return msg.err(18, MSG_RAI_INVALID_PROGID)
                if not sets or not prog:
                    return msg.err(12, MSG_RAI_INVALID_PROGID)
                else:
                    return msg.ok(contentsets=list(sets.values()), prog=prog)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(15, MSG_RAI_INVALID_PROGID)

    def duration2int(self, val):
        mo = re.search(r"^([0-9]{2,}):([0-9]{2}):([0-9]{2})", val)
        if mo:
            return int(mo.group(1))*3600+int(mo.group(2))*60+int(mo.group(3))
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
                    if 'date_published' in it2:
                        if 'time_published' in it2:
                            datepubs = it2['time_published']
                        else:
                            datepubs = '00:01'
                        datepubs = it2['date_published'] + ' ' + datepubs
                _LOGGER.debug("Date trying %s rv=%d: %s" % (url, resp2.status, str(it2)))
        except Exception:
            _LOGGER.error(traceback.format_exc())
        _LOGGER.debug("Processing date: %s" % datepubs)
        datepubo = datetime.strptime(datepubs, '%d-%m-%Y %H:%M')
        datepubi = int(datepubo.timestamp() * 1000)
        datepub = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
        return (datepub, datepubi)

    async def entry2Program(self, it, session, progid, set, playlist):
        order = -1
        if 'season' in it and re.search(r'^[0-9]+$', it['season']) and\
           'episode' in it and re.search(r'^[0-9]+$', it['episode']):
            order = int(it['season']) * 100 + int(it['episode'])
        conf = dict(progid=progid,
                    set=set,
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
            img=img,
            playlist=playlist
        ), datepubi)

    async def processPrograms(self, msg, datefrom=0, dateto=33134094791000, conf=dict(), playlist=None):
        try:
            progid = conf['prog']['id']
            sets = [s['id'] for s in conf['contentsets']]
        except (KeyError, AttributeError):
            _LOGGER.error(traceback.format_exc())
            return msg.err(11, MSG_BACKEND_ERROR)
        if sets and progid:
            try:
                async with aiohttp.ClientSession() as session:
                    programs = dict()
                    for set in sets:
                        async with session.get(MessageProcessor.programsUrl(progid, set)) as resp:
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
                        return msg.err(13, MSG_RAI_INVALID_CONTENTSET)
                    else:
                        programs = list(programs.values())
                        programs.sort(key=lambda item: item.conf['order'] if item.conf['order'] > 0 else item.datepub)
                        return msg.ok(items=programs)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(16, MSG_RAI_INVALID_CONTENTSET)

    async def getResponse(self, msg, userid):
        if msg.c(CMD_RAI_CONTENTSET):
            return await self.processContentSet(msg, userid)
        else:
            return None