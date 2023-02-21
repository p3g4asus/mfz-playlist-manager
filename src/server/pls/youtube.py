import logging
import re
import traceback
import yt_dlp as youtube_dl
from datetime import (datetime, timedelta, timezone)

from common.const import (CMD_YT_PLAYLISTCHECK, MSG_YT_INVALID_PLAYLIST,
                          MSG_BACKEND_ERROR, MSG_NO_VIDEOS)
from common.playlist import PlaylistItem
from common.utils import parse_isoduration

from .refreshmessageprocessor import RefreshMessageProcessor
from urllib.parse import urlunparse, urlencode, urlparse, parse_qs

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(RefreshMessageProcessor):

    def interested_plus(self, msg):
        return msg.c(CMD_YT_PLAYLISTCHECK)

    def get_name(self):
        return "youtube"

    def __init__(self, db, **kwargs):
        super().__init__(db, **kwargs)
        try:
            from googleapiclient.discovery import build
            self.apikey = kwargs.get('apikey', '')
        except ImportError:
            self.apikey = ''
        self.youtube = None

    @staticmethod
    def programsUrl(plid):
        if plid[0] == '&':
            return f'https://m.youtube.com/watch?v={plid[1:]}'
        elif plid[0] == '%':
            return plid[1:]
        elif plid[0] == '|':
            return f'https://www.youtube.com/channel/{plid[1:]}/videos'
        elif plid[0] == '(':
            return f'https://www.youtube.com/channel/{plid[1:]}/streams'
        else:
            return f'https://m.youtube.com/playlist?list={plid}'

    def youtubeApiBuild(self):
        if self.youtube is None:
            from googleapiclient.discovery import build
            self.youtube = build('youtube', 'v3', developerKey=self.apikey)
        return self.youtube

    async def processPlaylistCheck(self, msg, userid, executor):
        text = msg.f('text', (str,))
        if text:
            try:
                params = dict()
                plid = ''
                urlp = urlparse(text)
                if urlp and urlp.scheme:
                    params2 = parse_qs(urlp.query)
                    if not isinstance(params2, dict):
                        params2 = dict()
                    for np2, vp2 in params2.copy().items():
                        if np2.endswith('_mfzpm'):
                            params[np2[0:-6]] = vp2
                            del params2[np2]
                    urlp = urlp._replace(query=urlencode(params2))
                    text = urlunparse(urlp)
                else:
                    urlp = None
                if text.find('twitch.tv') >= 0:
                    plid = '%'
                    if text.find('/videos') >= 0:
                        url = text
                    else:
                        url = text + '/videos?filter=archives&sort=time'
                    plid += url
                elif text.find('youtu') >= 0:
                    mo2 = re.search(r'v=([^&?/]+)', text)
                    if mo2:
                        plid = "&" + mo2.group(1)
                        url = MessageProcessor.programsUrl(plid)
                    else:
                        mo2 = re.search(r'list=([^&?/]+)', text)
                        if mo2:
                            plid = mo2.group(1)
                            url = MessageProcessor.programsUrl(plid)
                        elif urlp:
                            mo2 = re.search(r'/channel/([^/]+)/?$', urlp.path)
                            mo3 = re.search(r'/@([^/]+)/?$', urlp.path)
                            if (mo2 or mo3) and self.apikey:
                                req = self.youtubeApiBuild().channels().list(part="contentDetails", **(dict(id=mo2.group(1)) if mo2 else dict(forUsername=mo3.group(1))))
                                resp = req.execute()
                                plid = resp['items'][0]['contentDetails']['relatedPlaylists']['uploads']
                                url = MessageProcessor.programsUrl(plid)
                            else:
                                mo2 = re.search(r'/(videos|streams)$', urlp.path)
                                plid = '|'
                                if mo2:
                                    if mo2.group(1)[0] == 's':
                                        plid = '('
                                else:
                                    urlp = urlp._replace(path=urlp.path + '/videos')
                                    text = urlunparse(urlp)
                                url = text
                        else:
                            return msg.err(20, MSG_YT_INVALID_PLAYLIST)
                else:
                    plid = '%' + text
                    url = text
                _LOGGER.debug("Youtube: Getting processPlaylistCheck " + url)
                ydl_opts = {
                    'ignoreerrors': True,
                    'quiet': True,
                    'playliststart': 1,
                    'playlistend': 100,
                    'extract_flat': True
                }
                playlist_dict = dict()
                plinfo = dict()
                try:
                    await executor(self.youtube_dl_get_dict, url, ydl_opts, playlist_dict)
                    if '_err' not in playlist_dict:
                        plinfo = dict(
                            title=playlist_dict['title'],
                            params=params,
                            channel=playlist_dict.get('uploader', playlist_dict['title']),
                            id=plid if len(plid) > 1 else plid + playlist_dict['id'],
                            description=playlist_dict.get('description', playlist_dict['title'])
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
            return int(mo.group(1)) * 3600 + int(mo.group(2)) * 60 + int(mo.group(3))
        else:
            return 0

    def entry2Program(self, it, set, playlist):
        conf = dict(playlist=set,
                    userid=it['user_id'],
                    author=it['author'])
        title = it['title']
        uid = it['encrypted_id']
        try:
            datepubo = datetime.strptime(it['added'] + ' 12:30', '%m/%d/%y %H:%M')
            datepubi = int(datepubo.timestamp() * 1000)
        except ValueError:
            _LOGGER.debug("Invalid added field is %s" % str(it))
            datepubi = it['time_created']
            datepubo = datetime.fromtimestamp(datepubi)
            datepubi = datepubi * 1000
        datepub = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
        img = it['thumbnail']
        if img.endswith('default.jpg'):
            img = img[0:-11] + 'hqdefault.jpg'
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

    def youtube_dl_get_dict(self, current_url, ydl_opts, out_dict):
        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                try:
                    playlist_dict = ydl.extract_info(current_url, download=False)
                except Exception:
                    _LOGGER.error(f'YTDLP2: {traceback.format_exc()}')
                    playlist_dict = None
                if playlist_dict:
                    out_dict.update(playlist_dict)
                else:
                    out_dict.update(dict(_err=404))
                return
        except Exception:
            _LOGGER.error(f'YTDLP: {traceback.format_exc()}')
            out_dict.update(dict(_err=401))

    def video_is_not_filtered_out(self, video, filters):
        if 'yes' in filters:
            for x in filters['yes']:
                if not re.search(x, video['title'], re.IGNORECASE):
                    return False
        if 'no' in filters:
            for x in filters['no']:
                if re.search(x, video['title'], re.IGNORECASE):
                    return False
        # keep maybe checking last
        if 'maybe' in filters:
            for x in filters['maybe']:
                if re.search(x, video['title'], re.IGNORECASE):
                    return True
            return False
        return True

    async def processPrograms(self, msg, datefrom=0, dateto=33134094791000, conf=dict(), playlist=None, executor=None):
        try:
            sets = [(s['id'], s['ordered'] if 'ordered' in s else True, s['params'] if 'params' in s else dict()) for s in conf['playlists']]
        except (KeyError, AttributeError):
            _LOGGER.error(traceback.format_exc())
            return msg.err(11, MSG_BACKEND_ERROR)
        if sets:
            try:
                ydl_opts = {
                    'ignoreerrors': True,
                    'quiet': True,
                    'playliststart': 1,
                    'playlistend': 100,
                    'extract_flat': True
                }
                programs = dict()
                localtz = datetime.now(timezone.utc).astimezone().tzinfo
                for set, ordered, filters in sets:
                    startFrom = 1
                    while startFrom:
                        ydl_opts['playliststart'] = startFrom
                        ydl_opts['playlistend'] = startFrom + 99
                        current_url = MessageProcessor.programsUrl(set)
                        playlist_dict = dict()
                        cont_ok = False
                        cont_n = 0
                        while not cont_ok and cont_n < 3:
                            cont_ok = True
                            cont_n += 1
                            _LOGGER.debug(f"Set = {set} url = {current_url} startFrom = {startFrom} ({cont_n}/3)")
                            try:
                                await executor(self.youtube_dl_get_dict, current_url, ydl_opts, playlist_dict)
                                # self.youtube_dl_get_dict(current_url, ydl_opts, playlist_dict)
                                if '_err' not in playlist_dict:
                                    if set[0] == '&' or 'entries' not in playlist_dict:
                                        startFrom = 0
                                        try:
                                            playlist_dict['entries'] = [dict(**playlist_dict)]
                                        except Exception:
                                            _LOGGER.error(traceback.format_exc())
                                    if 'entries' in playlist_dict and playlist_dict['entries']:
                                        secadd = 86000
                                        for video in playlist_dict['entries']:
                                            try:
                                                if set[0] == '%':
                                                    current_url = video['url']
                                                    if set.find('twitch.tv') >= 0:
                                                        if 'timestamp' not in video:
                                                            mo = re.search(r'_([0-9]{7,})/+thumb', video["thumbnail"])
                                                            if mo:
                                                                tsi = int(mo.group(1))
                                                                if tsi >= 1590734846:
                                                                    try:
                                                                        datetime.fromtimestamp(tsi)
                                                                        video['timestamp'] = tsi
                                                                    except Exception:
                                                                        pass
                                                        if 'timestamp' not in video:
                                                            _LOGGER.debug("thumb does not match " + video["thumbnail"])
                                                            _LOGGER.debug("SetTwitch = %s url = %s" % (set, current_url))
                                                            video = dict()
                                                            await executor(self.youtube_dl_get_dict, current_url, ydl_opts, video)

                                                        else:
                                                            mo = re.search(r'twitch.tv/([^/]+)/videos', set)
                                                            if mo:
                                                                video['uploader_id'] = video['uploader'] = mo.group(1)
                                                        if video['id'][0] == 'v':
                                                            video['id'] = video['id'][1:]
                                                        if 'timestamp' in video:
                                                            datepubo = datepubo_conf = datetime.fromtimestamp(int(video['timestamp']))
                                                        else:
                                                            datepubo = datepubo_conf = datetime.now()
                                                        video['upload_date'] = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
                                                        video['thumbnail'] = re.sub(r'[0-9]+x[0-9]+\.jpg', '0x0.jpg', video['thumbnail'])
                                                    else:
                                                        if 'timestamp' not in video or 'thumbnail' not in video or not video['timestamp'] or not video['thumbnail']:
                                                            video = dict()
                                                            await executor(self.youtube_dl_get_dict, current_url, ydl_opts, video)
                                                        if 'timestamp' in video and video['timestamp']:
                                                            datepubo = datepubo_conf = datetime.fromtimestamp(int(video['timestamp']))
                                                            video['upload_date'] = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
                                                        elif 'upload_date' in video and video['upload_date']:
                                                            datepubo = datepubo_conf = datetime.strptime(video['upload_date'], '%Y%m%d')
                                                        else:
                                                            datepubo = datepubo_conf = datetime.now()
                                                        if 'thumbnail' not in video or not video['thumbnail']:
                                                            video['thumbnail'] = ''
                                                        if 'id' not in video or not video['id']:
                                                            video['id'] = video['url']
                                                        if 'duration' not in video or not video['duration']:
                                                            video['duration'] = 0
                                                        video['upload_date'] = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
                                                else:
                                                    current_url = f"http://www.youtube.com/watch?v={video['id']}&src=plsmanager"
                                                    if self.apikey:
                                                        try:
                                                            req = self.youtubeApiBuild().videos().list(part="snippet,contentDetails", id=video['id'])
                                                            resp = req.execute()
                                                            _LOGGER.debug(f'Using apikey: resp is {resp}')
                                                            if 'items' in resp and resp['items']:
                                                                base = resp['items'][0]
                                                                if 'snippet' in base and 'contentDetails' in base:
                                                                    cdt = base['contentDetails']
                                                                    base = base['snippet']
                                                                    if 'publishedAt' in base and 'thumbnails' in base and 'duration' in cdt:
                                                                        datepubo = datepubo_conf = datetime.strptime(base['publishedAt'], "%Y-%m-%dT%H:%M:%S%z").astimezone(localtz)
                                                                        video['upload_date'] = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
                                                                        ths = ['maxres', 'standard', 'medium', 'default']
                                                                        video['duration'] = 0 if not cdt['duration'] else parse_isoduration(cdt['duration'])
                                                                        video['uploader'] = base.get('channelTitle')
                                                                        video['uploader_id'] = base.get('channelId')
                                                                        video['title'] = base.get('title', video['title'])
                                                                        for x in ths:
                                                                            if x in base['thumbnails']:
                                                                                video['thumbnail'] = base['thumbnails'][x]['url']
                                                                                break
                                                        except Exception:
                                                            _LOGGER.error(f'APIKEY ERROR {traceback.format_exc()}')
                                                    if 'upload_date' not in video:
                                                        _LOGGER.debug("Set = %s url = %s" % (set, current_url))
                                                        video = dict()
                                                        await executor(self.youtube_dl_get_dict, current_url, ydl_opts, video)
                                                        datepubo_conf = datetime.strptime(video['upload_date'], '%Y%m%d')
                                                        datepubo = datetime.strptime(video['upload_date'] + ' 00:00:01', '%Y%m%d %H:%M:%S')
                                                        datepubo = datepubo + timedelta(seconds=secadd)
                                                        secadd -= 1
                                                _LOGGER.debug("Found [%s] = %s | %s | %s" % (video.get('id'),
                                                                                            video.get('title'),
                                                                                            video.get('upload_date'),
                                                                                            video.get('duration')))
                                                # datepubi = int(datepubo.timestamp() * 1000)
                                                datepubi_conf = int(datepubo_conf.timestamp() * 1000)
                                                if video['id'] not in programs and self.video_is_not_filtered_out(video, filters):
                                                    if datepubi_conf >= datefrom:
                                                        if datepubi_conf <= dateto or dateto < datefrom:
                                                            datepub = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
                                                            extr = video.get('extractor')
                                                            if not extr:
                                                                extr = playlist_dict.get('extractor')
                                                            conf = dict(playlist=set,
                                                                        extractor=extr,
                                                                        userid=video.get('uploader_id'),
                                                                        author=video.get('uploader'))
                                                            pr = PlaylistItem(
                                                                link=current_url,
                                                                title=video['title'],
                                                                datepub=datepub,
                                                                dur=video['duration'],
                                                                conf=conf,
                                                                uid=video['id'],
                                                                img=video['thumbnail'],
                                                                playlist=playlist
                                                            )
                                                            programs[video['id']] = pr
                                                            _LOGGER.debug("Added [%s] = %s" % (pr.uid, str(pr)))
                                                    elif ordered:
                                                        startFrom = 0
                                                        break
                                            except Exception:
                                                _LOGGER.error(f'YTDLPM0 {traceback.format_exc()}')
                                        if startFrom:
                                            startFrom += 100
                                    else:
                                        startFrom = 0
                                else:
                                    startFrom = 0
                            except Exception:
                                _LOGGER.error(f'YTDLPM1 {cont_n}/3 {traceback.format_exc()}')
                                cont_ok = False
                                if cont_n >= 3:
                                    startFrom = 0
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

    async def getResponse(self, msg, userid, executor):
        if msg.c(CMD_YT_PLAYLISTCHECK):
            return await self.processPlaylistCheck(msg, userid, executor)
        else:
            return None
