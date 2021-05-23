import logging
import re
import traceback
import youtube_dl
from datetime import (datetime, timedelta)

from common.const import (CMD_YT_PLAYLISTCHECK, MSG_YT_INVALID_PLAYLIST,
                          MSG_BACKEND_ERROR, MSG_NO_VIDEOS)
from common.playlist import PlaylistItem

from .refreshmessageprocessor import RefreshMessageProcessor

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(RefreshMessageProcessor):

    def interested_plus(self, msg):
        return msg.c(CMD_YT_PLAYLISTCHECK)

    def get_name(self):
        return "youtube"

    @staticmethod
    def programsUrl(plid):
        if plid[0] == '&':
            return f'https://m.youtube.com/watch?v={plid[1:]}'
        elif plid[0] == '|':
            return f'https://www.youtube.com/channel/{plid[1:]}/videos'
        else:
            return f'https://m.youtube.com/playlist?list={plid}'

    async def processPlaylistCheck(self, msg, userid, executor):
        text = msg.f('text', (str,))
        if text:
            try:
                plid = ''
                mo2 = re.search(r'v=([^&?/]+)', text)
                if mo2:
                    plid = "&" + mo2.group(1)
                    url = MessageProcessor.programsUrl(plid)
                else:
                    mo2 = re.search(r'list=([^&?/]+)', text)
                    if mo2:
                        plid = mo2.group(1)
                        url = MessageProcessor.programsUrl(plid)
                    else:
                        mo2 = re.search(r'/videos$', text)
                        url = text if mo2 else text + '/videos'
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
                            channel=playlist_dict.get('uploader', playlist_dict['title']),
                            id=plid if plid else "|" + playlist_dict['id'],
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
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            playlist_dict = ydl.extract_info(current_url, download=False)
            if playlist_dict:
                out_dict.update(playlist_dict)
            else:
                out_dict.update(dict(_err=404))
            return
        out_dict.update(dict(_err=401))

    async def processPrograms(self, msg, datefrom=0, dateto=33134094791000, conf=dict(), playlist=None, executor=None):
        try:
            sets = [(s['id'], s['ordered'] if 'ordered' in s else True) for s in conf['playlists']]
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
                for set, ordered in sets:
                    startFrom = 1
                    while startFrom:
                        ydl_opts['playliststart'] = startFrom
                        ydl_opts['playlistend'] = startFrom + 99
                        current_url = MessageProcessor.programsUrl(set)
                        _LOGGER.debug("Set = %s url = %s startFrom = %d" % (set, current_url, startFrom))
                        playlist_dict = dict()
                        await executor(self.youtube_dl_get_dict, current_url, ydl_opts, playlist_dict)
                        if '_err' not in playlist_dict:
                            if set[0] == '&':
                                startFrom = 0
                                try:
                                    playlist_dict['entries'] = [dict(**playlist_dict)]
                                except Exception:
                                    _LOGGER.error(traceback.format_exc())
                            if 'entries' in playlist_dict and playlist_dict['entries']:
                                secadd = 86000
                                for video in playlist_dict['entries']:
                                    try:
                                        if 'upload_date' not in video:
                                            current_url = f"http://www.youtube.com/watch?v={video['id']}&src=plsmanager"
                                            _LOGGER.debug("Set = %s url = %s" % (set, current_url))
                                            video = dict()
                                            await executor(self.youtube_dl_get_dict, current_url, ydl_opts, video)
                                        _LOGGER.debug("Found [%s] = %s | %s | %s" % (video.get('id'),
                                                                                     video.get('title'),
                                                                                     video.get('upload_date'),
                                                                                     video.get('duration')))
                                        datepubo = datetime.strptime(video['upload_date'] + ' 00:00:01', '%Y%m%d %H:%M:%S')
                                        datepubo = datepubo + timedelta(seconds=secadd)
                                        secadd -= 1
                                        datepubi = int(datepubo.timestamp() * 1000)
                                        if video['id'] not in programs:
                                            if datepubi >= datefrom:
                                                if datepubi <= dateto or dateto < datefrom:
                                                    datepub = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
                                                    conf = dict(playlist=set,
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
                                        _LOGGER.error(traceback.format_exc())
                                if startFrom:
                                    startFrom += 100
                            else:
                                startFrom = 0
                        else:
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
