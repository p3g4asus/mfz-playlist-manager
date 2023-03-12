import json
import re
import traceback
import aiohttp
from server.twitch_vod_quality_feeds import Feeds, getQualityV, getQualityRF, QUALITIES_MAP
import asyncio
import logging

from server.twitch_vod_id import single_regex, vod_get_id
from server.twitch_vod_fuzz import verifyURL

_LOGGER = logging.getLogger(__name__)


async def get_twitch_token(vodid, isvod):
    if isvod:
        json = "{\"operationName\": \"PlaybackAccessToken\",\"variables\": {\"isLive\": false,\"login\": \"\",\"isVod\": true,\"vodID\": \"" + str(vodid) + "\",\"playerType\": \"channel_home_live\"},\"extensions\": {\"persistedQuery\": {\"version\": 1,\"sha256Hash\": \"0828119ded1c13477966434e15800ff57ddacf13ba1911c129dc2200705b0712\"}}}"
    else:
        json = "{\"operationName\": \"PlaybackAccessToken\",\"variables\": {\"isLive\": true,\"login\": \"" + str(vodid) + "\",\"isVod\": false,\"vodID\": \"\",\"playerType\": \"channel_home_live\"},\"extensions\": {\"persistedQuery\": {\"version\": 1,\"sha256Hash\": \"0828119ded1c13477966434e15800ff57ddacf13ba1911c129dc2200705b0712\"}}}"

    url = "https://gql.twitch.tv/gql"
    headers = {'content-type': "text/plain;charset=UTF-8", "Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=json.encode('utf8'), headers=headers) as resp:
                tokens = await resp.json()
                _LOGGER.debug(f"Auth resp {resp}")
                data = tokens["data"]
                tokenCat = data["videoPlaybackAccessToken"] if isvod else data["streamPlaybackAccessToken"]
                return (tokenCat["value"].replace("\\", ""), tokenCat["signature"])
    except Exception:
        _LOGGER.error(traceback.format_exc())
        return None


class M3u8Line:
    def __init__(self, idv, dct):
        self.id = idv
        self.dict = dct

    def its_me(self, idv):
        return idv == self.id

    def __contains__(self, key):
        return key in self.dict

    def __getitem__(self, key):
        return None if key not in self.dict else self.dict[key]

    def __str__(self) -> str:
        return f'#{self.id} {self.dict}'

    @staticmethod
    def parse(line):
        if line[0] == '#':
            idx = line.find(':')
            if idx >= 2:
                idv = line[1:idx]
                dct = dict()
                line = line[idx + 1:].strip() + ','
                rx = [r'(^[^=,]+)="([^"]+)",', r'(^[^=,]+)=([^,]+),']
                while line:
                    matched = False
                    for r in rx:
                        mo = re.search(r, line)
                        if mo:
                            dct[mo.group(1)] = mo.group(2)
                            line = line[mo.end():]
                            matched = True
                            break
                    if not matched:
                        _LOGGER.warning(f'Abnormal m3u 8parser termination: {line}')
                        break
                return M3u8Line(idv, dct)
        return None


def vod_parse_feeds(m3uall):
    feeds = Feeds()
    listlines = m3uall.splitlines()
    for i, line in enumerate(listlines):
        try:
            if not line.startswith("#"):
                if listlines[i - 2].find("chunked") >= 0:
                    feeds.addEntry(line, QUALITIES_MAP['Source'])
                    if listlines[i - 2].find("Source") >= 0:
                        m3u8 = M3u8Line.parse(listlines[i - 1])
                        if m3u8 and m3u8.its_me("EXT-X-STREAM-INF") and m3u8["VIDEO"] == "chunked" and m3u8["CODECS"]:
                            tot = single_regex("(\\d+x\\d+)", m3u8["RESOLUTION"])
                            if tot:
                                feeds.addEntry(line, getQualityRF(tot, 60.000))
                    else:
                        fps = 0.0
                        m3u8 = M3u8Line.parse(listlines[i - 2])
                        if m3u8 and m3u8.its_me("EXT-X-MEDIA") and m3u8["TYPE"] == "VIDEO" and m3u8["GROUP-ID"] == "chunked":
                            tot = single_regex("^[0-9]+p([0-9]+)", m3u8["NAME"])
                            if tot:
                                fps = float(tot)
                        m3u8 = M3u8Line.parse(listlines[i - 1])
                        if m3u8 and m3u8.its_me("EXT-X-STREAM-INF") and m3u8["VIDEO"] == "chunked" and m3u8["CODECS"]:
                            tot = single_regex("(\\d+x\\d+)", m3u8["RESOLUTION"])
                            if tot:
                                feeds.addEntry(line, getQualityRF(tot, fps))
                elif listlines[i - 2].find("audio") >= 0:
                    feeds.addEntry(line, QUALITIES_MAP['AUDIO'])
                elif listlines[i - 2].find("1080p60") >= 0:
                    fps = 0.0
                    m3u8 = M3u8Line.parse(listlines[i - 2])
                    if m3u8 and m3u8.its_me("EXT-X-MEDIA") and m3u8["TYPE"] == "VIDEO" and single_regex("(1080p[0-9]*)", m3u8["GROUP-ID"]):
                        tot = single_regex("1080p([0-9]+)", m3u8["NAME"])
                        if tot:
                            fps = float(tot)
                    m3u8 = M3u8Line.parse(listlines[i - 1])
                    if m3u8 and m3u8.its_me("EXT-X-STREAM-INF") and m3u8["VIDEO"] and m3u8["CODECS"]:
                        tot = single_regex("(\\d+x\\d+)", m3u8["RESOLUTION"])
                        if tot:
                            feeds.addEntry(line, getQualityRF(tot, fps))
                else:
                    m3u8 = M3u8Line.parse(listlines[i - 2])
                    if m3u8 and m3u8.its_me("EXT-X-MEDIA") and m3u8["TYPE"] == "VIDEO" and single_regex("([0-9p]*)", m3u8["NAME"]):
                        tot = single_regex("([\\d]*p[36]0)", m3u8["GROUP-ID"])
                        if tot:
                            feeds.addEntry(line, getQualityV(tot))

        except Exception:
            pass
    return feeds


async def get_vod_playlist(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            html = await response.text()
            _LOGGER.debug(f"Playlist at {url}:\n{html}")
            return vod_parse_feeds(html)


async def get_vod_feeds(vodid):
    auth = await get_twitch_token(vodid, True)
    _LOGGER.debug(f'Auth received{auth}')
    feeds = await get_vod_playlist(f"https://usher.ttvnw.net/vod/{vodid}.m3u8?sig={auth[1]}&token={auth[0]}&allow_source=true&player=twitchweb&allow_spectre=true&allow_audio_only=true")
    if not feeds:
        feeds = await get_sub_vod_feeds(vodid, False)
    feeds.sort()
    return feeds


async def get_sub_vod_feeds(vodid, highlight):
    feeds = Feeds()
    response = ""
    try:
        url = f"https://api.twitch.tv/kraken/videos/{vodid}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/vnd.twitchtv.v5+json",
            "Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                jO = await response.json()
                baseURL = single_regex("https://[a-z0-9]*.cloudfront.net/([a-z0-9_]*)/storyboards/[0-9]*-info.json", jO["seek_previews_url"])
                auth = await get_twitch_token(vodid, True)
                jo = json.loads(auth[0])
                restricted = jo["chansub"]["restricted_bitrates"]
                if highlight:
                    domain = single_regex("(https://[a-z0-9\\-]*.[a-z_]*.(?:net|com|tv)/[a-z0-9_]*/)chunked/highlight-[0-9]*.m3u8", (await verifyURL(f"/{baseURL}/chunked/highlight-{vodid}.m3u8"))[0])
                    for r in restricted:
                        feeds.addEntry(f"{domain}{r}/highlight-{vodid}.m3u8", getQualityV(r))
                else:
                    domain = single_regex("(https://[a-z0-9\\-]*.[a-z_]*.(?:net|com|tv)/[a-z0-9_]*/)chunked/index-dvr.m3u8", (await verifyURL(f"/{baseURL}/chunked/index-dvr.m3u8"))[0])
                    for r in restricted:
                        feeds.addEntry(f"{domain}{r}/index-dvr.m3u8", getQualityV(r))
    except Exception:
        _LOGGER.error(traceback.format_exc())
    return feeds


if __name__ == '__main__':
    import sys
    import os
    import certifi
    logging.basicConfig(level=logging.DEBUG)
    os.environ['SSL_CERT_FILE'] = certifi.where()
    asyncio.run(get_vod_feeds(vod_get_id(sys.argv[1])))
