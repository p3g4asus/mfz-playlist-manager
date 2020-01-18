import logging
import re
import traceback
from datetime import datetime

import aiohttp

from common.const import (CMD_YT_PLAYLISTCHECK, MSG_YT_INVALID_PLAYLIST,
                          MSG_YT_INVALID_CHANNEL, MSG_BACKEND_ERROR,
                          MSG_NO_VIDEOS)
from common.playlist import PlaylistItem

from .refreshmessageprocessor import RefreshMessageProcessor

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(RefreshMessageProcessor):

    def interested_plus(self, msg):
        return msg.c(CMD_YT_PLAYLISTCHECK)

    def get_name(self):
        return "youtube"

    @staticmethod
    def programsUrl(plid, startFrom):
        return ('http://www.youtube.com/list_ajax?action_get_list=1&style=json&index=%d&list=%s') %\
            (startFrom, plid)

    @staticmethod
    def channelUrl(user):
        return f'https://www.youtube.com/user/{user}/videos'

    async def channel2playlist(self, session, chanid):
        url = MessageProcessor.channelUrl(chanid)
        _LOGGER.debug("Youtube: Getting processPlaylistCheck " + url)
        async with session.get(
                url,
                headers={'User-Agent': r'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'}) as resp:
            if resp.status == 200:
                txt = await resp.text()
                _LOGGER.debug("Received " + txt)
                mo = re.search(r'/playlist\?list=([^&\\]+)', txt)
                if mo:
                    return mo.group(1)
                else:
                    return 13
            else:
                return 12

    async def processPlaylistCheck(self, msg, userid):
        text = msg.f('text', (str,))
        if text:
            try:
                async with aiohttp.ClientSession() as session:
                    userfound = re.search(r'/user/([^/?&]+)', text)
                    plid = None
                    if userfound:
                        chanid = userfound.group(1)
                    else:
                        mo1 = re.search(r'/([^/]+)$', text)
                        mo2 = re.search(r'list=([^&]+)', text)
                        if mo2:
                            plid = mo2.group(1)
                        elif mo1:
                            chanid = mo1.group(1)
                        else:
                            chanid = text
                    if not plid:
                        res = await self.channel2playlist(session, chanid)
                        if isinstance(res, int):
                            if userfound:
                                return msg.err(res, MSG_YT_INVALID_CHANNEL)
                            else:
                                plid = chanid
                        else:
                            plid = res
                    url = MessageProcessor.programsUrl(plid, 1)
                    _LOGGER.debug("Youtube: Getting processPlaylistCheck " + url)
                    try:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                js = await resp.json()
                                plinfo = dict(
                                    title=js['title'],
                                    channel=js['author'],
                                    id=plid,
                                    description=js['description']
                                )
                                return msg.ok(playlistinfo=plinfo)
                            else:
                                return msg.err(15, MSG_YT_INVALID_PLAYLIST)
                    except Exception:
                        _LOGGER.error(traceback.format_exc())
                        return msg.err(16, MSG_YT_INVALID_PLAYLIST)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(17, MSG_YT_INVALID_PLAYLIST)

    def duration2int(self, val):
        mo = re.search(r"^([0-9]+)$", val)
        if mo:
            return int(mo.group(1))
        mo = re.search(r"^([0-9]+):([0-9]{2})$", val)
        if mo:
            return int(mo.group(1)) * 60 + int(mo.group(2))
        mo = re.search(r"^([0-9]+):([0-9]{2}):([0-9]{2})$", val)
        if mo:
            return int(mo.group(1))*3600+int(mo.group(2))*60+int(mo.group(3))
        else:
            return 0

    def entry2Program(self, it, set, playlist):
        conf = dict(playlist=set,
                    userid=it['user_id'],
                    author=it['author'])
        title = it['title']
        uid = it['encrypted_id']
        datepubi = it['time_created']
        datepubo = datetime.fromtimestamp(datepubi)
        datepubi = datepubi * 1000
        datepub = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
        img = it['thumbnail']
        dur = self.duration2int(it['duration'])
        link = f"http://www.youtube.com/watch?v={it['encrypted_id']}&src=plsmanager"
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
            sets = [s['id'] for s in conf['playlists']]
        except (KeyError, AttributeError):
            _LOGGER.error(traceback.format_exc())
            return msg.err(11, MSG_BACKEND_ERROR)
        if sets:
            try:
                async with aiohttp.ClientSession() as session:
                    programs = dict()
                    for set in sets:
                        startFrom = 1
                        while True:
                            async with session.get(MessageProcessor.programsUrl(set, startFrom)) as resp:
                                if resp.status == 200:
                                    js = await resp.json()
                                    for it in js['video']:
                                        try:
                                            (pr, datepubi) = self.entry2Program(it, set, playlist)
                                            _LOGGER.debug("Found [%s] = %s" % (pr.uid, str(pr)))
                                            if pr.uid not in programs:
                                                if datepubi >= datefrom:
                                                    if datepubi <= dateto or dateto < datefrom:
                                                        programs[pr.uid] = pr
                                                        _LOGGER.debug("Added [%s] = %s" % (pr.uid, str(pr)))
                                                else:
                                                    startFrom = 0
                                                    break
                                        except Exception:
                                            _LOGGER.error(traceback.format_exc())
                                    if not startFrom or 'video' not in js or len(js['video']) < 100:
                                        break
                                    else:
                                        startFrom += 100
                                else:
                                    break
                    if not len(programs):
                        return msg.err(13, MSG_NO_VIDEOS)
                    else:
                        programs = list(programs.values())
                        programs.sort(key=lambda item: item.datepub)
                        return msg.ok(items=programs)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(16, MSG_YT_INVALID_PLAYLIST)

    async def getResponse(self, msg, userid):
        if msg.c(CMD_YT_PLAYLISTCHECK):
            return await self.processPlaylistCheck(msg, userid)
        else:
            return None
