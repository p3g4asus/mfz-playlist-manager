import logging
import re
import subprocess
import traceback
from datetime import datetime
from os import listdir
from os.path import basename, exists, getmtime, isdir, isfile, join, relpath, splitext
from urllib.parse import quote


from common.const import (CMD_FOLDER_CHECK, CMD_FOLDER_LIST, MSG_BACKEND_ERROR, MSG_FOLDER_EMPTY, MSG_FOLDER_INVALID_FOLDER_NAME,
                          MSG_FOLDER_NOT_EXISTS, MSG_NO_VIDEOS,
                          RV_NO_VIDEOS)
from common.playlist import PlaylistItem

from .refreshmessageprocessor import RefreshMessageProcessor

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(RefreshMessageProcessor):

    def interested_plus(self, msg):
        return msg.c(CMD_FOLDER_CHECK) or msg.c(CMD_FOLDER_LIST)

    def get_name(self):
        return "localfolder"

    def __init__(self, db, **kwargs):
        super().__init__(db, **kwargs)
        self.absolute = kwargs.get('static', '')
        self.basedir = kwargs.get('basedir', '')
        self.relative = relpath(self.basedir, self.absolute)

    def get_relative_path(self, usr, leaf):
        return re.sub(r'[\\/]', '/', join(self.relative, usr, leaf))

    async def processFolderCheck(self, msg, userid, executor):
        text = msg.f('text', (str,))
        if text:
            rel = join(usr := f'u{userid}', text)
            full = join(self.basedir, rel)
            if exists(full) and isdir(full):
                plinfo = dict(
                    title=text,
                    id=full,
                    relative=self.get_relative_path(usr, text),
                    description=text
                )
                return msg.ok(playlistinfo=plinfo)
            else:
                return msg.err(20, MSG_FOLDER_NOT_EXISTS)
        else:
            return msg.err(21, MSG_FOLDER_INVALID_FOLDER_NAME)

    async def processFolderList(self, msg, userid, executor):
        full = join(self.basedir, usr := f'u{userid}')
        if exists(full):
            fold = {ff: dict(title=f, id=ff, relative=self.get_relative_path(usr, f), description=f'{f} Folder') for f in listdir(full) if isdir(ff := join(full, f))}
            if fold:
                return msg.ok(folders=fold)
            else:
                return msg.err(21, MSG_FOLDER_EMPTY)
        else:
            return msg.err(20, MSG_FOLDER_NOT_EXISTS)

    def get_duration(self, filename, out_dict):
        try:
            result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                     "format=duration", "-of",
                                     "default=noprint_wrappers=1:nokey=1", filename],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
        except Exception:
            _LOGGER.error(f'YTDLP: {traceback.format_exc()}')
            out_dict.update(dict(_err=401))
            return
        try:
            _LOGGER.info(f'ffprobe out: {result.stdout}')
            out_dict.update(dict(dur=float(result.stdout)))
        except Exception:
            _LOGGER.info(f'ffprobe error: {traceback.format_exc()}')
            out_dict.update(dict(_err=402))

    def generate_thumb(self, video_input_path, img_output_path, framesec, out_dict):
        try:
            result = subprocess.call(['ffmpeg', '-y', '-i', video_input_path, '-ss', str(framesec), '-vframes', '1', img_output_path])
            if result:
                _LOGGER.error('ffmpeg Invalid return value')
                out_dict.update(dict(_err=404))
            else:
                out_dict.update(dict(path=img_output_path))
        except Exception:
            _LOGGER.info(f'ffmpeg error: {traceback.format_exc()}')
            out_dict.update(dict(_err=403))

    async def recursive_check_dir(self, absolute, datefrom, dateto, playlist, executor, programs, sta):
        files = [ff for f in listdir(absolute) if (isfile(ff := join(absolute, f)) and f.endswith('.mp4')) or isdir(ff)]
        relative = re.sub(r'[\\/]', '/', relpath(absolute, self.absolute))
        for f in files:
            if isdir(f):
                await self.recursive_check_dir(f, datefrom, dateto, playlist, executor, programs, sta)
            else:
                video = dict()
                tm = getmtime(f)
                tmms = tm * 1000
                self.record_status(sta, f'\U0001F50D Found {f}', 'ss')
                if tmms >= datefrom and tmms <= dateto:
                    video['timestamp'] = tm
                    datepubo = datetime.fromtimestamp(int(video['timestamp']))
                    datepub = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
                    playlist_dict = dict()
                    await executor(self.get_duration, f, playlist_dict)
                    if '_err' not in playlist_dict:
                        video['duration'] = int(playlist_dict['dur'])
                    else:
                        _LOGGER.warning(f'Cannot get duration of {f}')
                        continue
                    bn, _ = splitext(name_ext := basename(f))
                    thun = f'{bn}_thu.jpg'
                    thup = join(absolute, thun)
                    space = video['duration'] / 2
                    await executor(self.generate_thumb, f, thup, min(space, 60), playlist_dict)
                    conf = dict(todel=[f])
                    video['id'] = f
                    video['title'] = bn
                    relq = quote(relative)
                    current_url = f'@{relq}/{quote(name_ext)}'
                    if '_err' not in playlist_dict:
                        video['thumbnail'] = f'@{relq}/{quote(thun)}'
                        conf['todel'].append(thup)
                    else:
                        _LOGGER.warning(f'Cannot get duration of {f}')
                        continue
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
                    self.record_status(sta, f'\U00002795 Added {pr.title} [{pr.datepub}]', 'ss')
                    programs[video['id']] = pr

    async def processPrograms(self, msg, datefrom=0, dateto=33134094791000, conf=dict(), filter=dict(), playlist=None, userid=None, executor=None):
        try:
            sets = []
            for _, s in conf['playlists'].items():
                if not filter or (s['id'] in filter and filter[s['id']]['sel']):
                    sets.append((s['id'], s['relative'], s['description']))
        except (KeyError, AttributeError):
            _LOGGER.error(traceback.format_exc())
            return msg.err(11, MSG_BACKEND_ERROR)
        if sets:
            sta = msg.init_send_status_with_ping(ss=[])
            try:
                programs = dict()
                for absolute, relative, title in sets:
                    if not exists(absolute) or not isdir(absolute):
                        self.record_status(sta, f'\U000026A0 Folder {absolute} does not exist: ignoring', 'ss')
                        _LOGGER.warning(f'Folder {absolute} does not exist: ignoring')
                        continue
                    self.record_status(sta, f'\U0001F194 Scanning {title}...', 'ss')
                    await self.recursive_check_dir(absolute, datefrom, dateto, playlist, executor, programs, sta)
                if not len(programs):
                    self.record_status(sta, f'\U000026A0 {MSG_NO_VIDEOS}', 'ss')
                    return msg.err(RV_NO_VIDEOS, MSG_NO_VIDEOS)
                else:
                    programs = list(programs.values())
                    programs.sort(key=lambda item: item.title)
                    return msg.ok(items=programs)
            except Exception as ex:
                self.record_status(sta, f'\U000026A0 Error 11: {repr(ex)}', 'ss')
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(16, MSG_FOLDER_INVALID_FOLDER_NAME)

    async def getResponse(self, msg, userid, executor):
        if msg.c(CMD_FOLDER_CHECK):
            return await self.processFolderCheck(msg, userid, executor)
        elif msg.c(CMD_FOLDER_LIST):
            return await self.processFolderList(msg, userid, executor)
        else:
            return None
