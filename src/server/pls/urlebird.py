import json
import logging
import re
import traceback
from datetime import datetime, timedelta

import aiohttp

from common.const import (CMD_TT_PLAYLISTCHECK, MSG_BACKEND_ERROR, MSG_NO_VIDEOS, MSG_TT_INVALID_PLAYLIST, RV_NO_VIDEOS)
from common.playlist import PlaylistItem
from common.utils import parse_isoduration

from dateparser import parse as dateparser_parse
from dateutil.parser import parse as dateutil_parse
from pyquery import PyQuery as pq
from .refreshmessageprocessor import RefreshMessageProcessor
from urllib.parse import urlunparse, urlencode, urlparse, parse_qs

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(RefreshMessageProcessor):

    def interested_plus(self, msg):
        return msg.c(CMD_TT_PLAYLISTCHECK)

    def get_name(self):
        return "urlebird"

    def get_scraper_headers(self) -> dict:
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }

    async def get_video_info_from_url(self, session: aiohttp.ClientSession, url: str):
        for x in range(3):
            try:
                _LOGGER.debug(f"Urlebird: getting video info from {url} (attempt {x + 1})")
                async with session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        pqdoc = pq(html)
                        video_info = pqdoc('#VideoObject').text()
                        if video_info:
                            return json.loads(video_info)
                        else:
                            return 7
                    else:
                        return response.status
            except Exception as e:
                _LOGGER.error(f"Error fetching video info from {url}: {e}")
                return 1000
        return 1001

    async def get_all_videos_from_user(self, session: aiohttp.ClientSession, user: str | dict) -> pq | int:
        if isinstance(user, str):
            url = 'https://urlebird.com/user/' + user + '/'
            method = 'GET'
            data = None
        else:
            url = 'https://urlebird.com/ajax/'
            method = 'POST'
            data = aiohttp.FormData()
            data.add_field('action', 'user')
            data.add_field('data', json.dumps(user))
        for x in range(3):
            try:
                _LOGGER.debug(f"Urlebird: getting videos from {url} (attempt {x + 1})")
                async with session.request(method=method, url=url, data=data) as response:
                    if response.status == 200:
                        if method == 'POST':
                            json_data = await response.text()
                            json_data = json.loads(json_data)
                            if 'u' in json_data:
                                user['user_id'] = json_data['u']
                            if 'x' in json_data:
                                user['x'] = json_data['x']
                            if 'cursor' in json_data:
                                user['cursor'] = json_data['cursor']
                            if 's' in json_data:
                                user['sec_uid'] = json_data['s']
                            if 'thumbs' in json_data and json_data['thumbs']:
                                html = '<div id="thumbs">' + json_data['thumbs'].replace('\\n', '\n').replace('\\t', '\t') + '</div>'
                            else:
                                return 8
                        else:
                            html = await response.text()
                        return pq(html)
                    else:
                        return response.status
            except Exception as e:
                _LOGGER.error(f"Error fetching video info from {url}: {e}")
                return 1001
        return 1000

    async def processPlaylistCheck(self, msg, userid, executor):
        text = msg.f('text', (str,))
        if text:
            try:
                params = dict()
                urlp = urlparse(text)
                if urlp and urlp.scheme:
                    params2 = parse_qs(urlp.query)
                    if not isinstance(params2, dict):
                        params2 = dict()
                    for np2, vp2 in params2.copy().items():
                        if np2.endswith('_mfzpm'):
                            params[np2[0:-6]] = vp2
                            del params2[np2]
                    urlp = urlp._replace(query=urlencode(params2, doseq=True))
                    text = urlunparse(urlp)
                else:
                    urlp = None
                if urlp:
                    if (mo := re.search(r'^https://urlebird.com/user/([^/]+)', text)):
                        text = mo.group(1)
                    else:
                        return msg.err(17, MSG_TT_INVALID_PLAYLIST)
                async with aiohttp.ClientSession(headers=self.get_scraper_headers()) as session:
                    videosdoc = await self.get_all_videos_from_user(session, text)
                    if isinstance(videosdoc, int):
                        return msg.err(videosdoc, MSG_TT_INVALID_PLAYLIST)
                    elf = videosdoc('#thumbs div.thumb:first')
                    elf('div.info3 div.author-name').remove()
                    if3 = elf('div.info3 a').attr('href')
                    playlist_dict = await self.get_video_info_from_url(session, if3)
                    if isinstance(playlist_dict, int):
                        return msg.err(playlist_dict, MSG_TT_INVALID_PLAYLIST)
                    author = playlist_dict.get('creator', dict(name=text)).get('name', text)
                    plinfo = dict(
                        title=author,
                        params=self.process_filters(params),
                        id=text,
                        description=f'Videos from {author}',
                    )
                    return msg.ok(playlistinfo=plinfo)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(19, MSG_TT_INVALID_PLAYLIST)

    @staticmethod
    def video_is_not_filtered_out(video, filters) -> bool:
        if 'duration' in video and not video['duration']:
            return False
        return RefreshMessageProcessor.video_is_not_filtered_out(video, filters)

    def entry2Program(self, it, alternate_date: datetime | None, set, playlist):
        conf = dict(playlist=set,
                    userid=it.get('creator', dict(alternateName=set))['alternateName'])
        try:
            datepubo = dateutil_parse(it['uploadDate'])
            if alternate_date:
                if datepubo.day != alternate_date.day or datepubo.month != alternate_date.month or datepubo.year != alternate_date.year:
                    datepubo = alternate_date
        except ValueError:
            _LOGGER.debug("Invalid added field is %s" % str(it))
            datepubo = alternate_date if alternate_date else datetime.now()
        datepubi = int(datepubo.replace(hour=0, minute=0, second=0).timestamp() * 1000)
        datepub = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
        img = it['thumbnailURL']
        if mo := re.search(r'\-(\d{5,})/?$', it['url']):
            uid = mo.group(1)
        else:
            uid = it['url']
        dur = parse_isoduration(it['duration'])
        return (PlaylistItem(
            link=it['url'],
            title=it['name'],
            datepub=datepub,
            dur=dur,
            conf=conf,
            uid=uid,
            img=img,
            playlist=playlist
        ), datepubi)

    async def processPrograms(self, msg, datefrom=0, dateto=33134094791000, conf=dict(), filter=dict(), playlist=None, userid=None, executor=None):
        try:
            sets = []
            for s in conf['playlists'].values():
                if not filter or (s['id'] in filter and filter[s['id']]['sel']):
                    sets.append((s['id'], s['params'], s['title']))
        except (KeyError, AttributeError):
            _LOGGER.error(traceback.format_exc())
            return msg.err(11, MSG_BACKEND_ERROR)
        if sets:
            programs = dict()
            try:
                sta = msg.init_send_status_with_ping(ss=[])
                setidx = 0
                headers = self.get_scraper_headers()
                while True:
                    if len(sets) <= setidx:
                        break
                    set, filters, title = sets[setidx]
                    setidx += 1
                    page = 1
                    rel_s = 0
                    rel_base = datetime.now()
                    userinfo = None
                    async with aiohttp.ClientSession(headers=headers) as session:
                        while True:
                            _LOGGER.debug(f"Set = {set} page = {page}")
                            self.record_status(sta, f'\U0001F194 Set {title} [{page}]...', 'ss')
                            videosdoc = await self.get_all_videos_from_user(session, set if page == 1 else userinfo)
                            if isinstance(videosdoc, int):
                                self.record_status(sta, f'\U000026A0 Error Set {title} [{page}] : {videosdoc}', 'ss')
                                break
                            # videosdoc('#thumbs div.thumb div.info3 div.author-name').remove()
                            thumbs = videosdoc('#thumbs div.thumb')
                            for th in thumbs:
                                thumb = pq(th)
                                thumb('div.info3 div.author-name').remove()
                                vurl = thumb('div.info3 a').attr('href')
                                stat_els = thumb('div.stats span')
                                when = None
                                for se in stat_els:
                                    stat_el = pq(se)
                                    if len(stat_el('.fa-clock')):
                                        when = stat_el.text()
                                        break
                                try:
                                    rel_base = rel_base - timedelta(seconds=rel_s)
                                    rel_s += 1
                                    when = dateparser_parse(when, settings=dict(RELATIVE_BASE=rel_base))
                                except Exception:
                                    _LOGGER.debug(f"[urlebird] Invalid date field is {when}")
                                    when = None
                                vidinfo = await self.get_video_info_from_url(session, vurl)
                                if isinstance(vidinfo, int):
                                    self.record_status(sta, f'\U000026A0 Error Set {title}: {vurl} [{vidinfo}]', 'ss')
                                else:
                                    pr, datepubi_conf = self.entry2Program(vidinfo, when, set, playlist)
                                    if datepubi_conf >= datefrom:
                                        if (datepubi_conf <= dateto or dateto < datefrom) and self.video_is_not_filtered_out(dict(title=pr.title, duration=pr.dur), filters):
                                            programs[pr.uid] = pr
                                            _LOGGER.debug("Added [%s] = %s" % (pr.uid, str(pr)))
                                            self.record_status(sta, f'\U00002795 Added {pr.title} [{pr.datepub}]', 'ss')
                                    elif page >= 3:
                                        page = 0
                                        break
                            if not page:
                                break
                            else:
                                page += 1
                                if page == 2:
                                    btn = videosdoc('#load_more')
                                    userinfo = dict(
                                        user_id=btn.attr('data-user-id'),
                                        sec_uid=btn.attr('data-sec-uid'),
                                        cursor=btn.attr('data-cursor'),
                                        lang=btn.attr('data-lang'),
                                        page="2",
                                        x=btn.attr('data-x'),
                                    )
                                else:
                                    userinfo['page'] = f'{page}'
                if not len(programs):
                    self.record_status(sta, f'\U000026A0 {MSG_NO_VIDEOS}', 'ss')
                    return msg.err(RV_NO_VIDEOS, MSG_NO_VIDEOS)
                else:
                    programs = list(programs.values())
                    programs.sort(key=lambda item: item.datepub)
                    return msg.ok(items=programs)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(16, MSG_TT_INVALID_PLAYLIST)

    async def getResponse(self, msg, userid, executor):
        if msg.c(CMD_TT_PLAYLISTCHECK):
            return await self.processPlaylistCheck(msg, userid, executor)
        else:
            return None
