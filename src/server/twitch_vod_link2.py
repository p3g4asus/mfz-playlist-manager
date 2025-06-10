import logging
import aiohttp
import traceback
import re

_LOGGER = logging.getLogger(__name__)


async def get_vod_link(vodid) -> dict:
    json = '[{"operationName": "VideoMetadata", "variables": {"channelLogin": "", "videoID": "%d"}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "49b5b8f268cdeb259d75b58dcb0c1a748e3b575003448a2333dc5cdafd49adad"}}}, {"operationName": "VideoPlayer_ChapterSelectButtonVideo", "variables": {"includePrivate": false, "videoID": "%d"}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "8d2793384aac3773beab5e59bd5d6f585aedb923d292800119e03d40cd0f9b41"}}}, {"operationName": "VideoPlayer_VODSeekbarPreviewVideo", "variables": {"includePrivate": false, "videoID": "%d"}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "07e99e4d56c5a7c67117a154777b0baf85a5ffefa393b213f4bc712ccaf85dd6"}}}]' % (vodid, vodid, vodid)

    url = "https://gql.twitch.tv/gql"
    headers = {'content-type': "text/plain;charset=UTF-8", "Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko"}
    format_check = {
        '1080p60': 'chunked',
        '720p60': '720p60',
        '480p': '480p30',
        '360p': '360p30',
        '160p': '160p30',
        'Audio_Only': 'audio_only',
    }
    links = dict()

    async def test_url(base, idv):
        link = f'{base}/{idv}/index-dvr.m3u8'
        async with aiohttp.ClientSession() as session2:
            async with session2.get(link, headers=headers) as resp:
                if resp.status >= 200 and resp.status < 300:
                    txt = await resp.text()
                    if txt and txt.strip()[0] == '#':
                        return link
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=json.encode('utf8'), headers=headers) as resp:
                tokens = await resp.json()
                _LOGGER.debug(f"Auth resp {tokens}")
                for token in tokens:
                    try:
                        data = token["data"]["video"]["previewThumbnailURL"]
                        mo = re.search('/([a-z0-9]+)/([a-f0-9]+_.+?_[0-9]+_[0-9]+)/', data)
                        headers = {"range": "bytes=0-200", "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/81.0"}
                        if mo:
                            base = f'https://{mo.group(1)}.cloudfront.net/{mo.group(2)}'
                            for format, idv in format_check.items():
                                link = await test_url(base, idv)
                                if link:
                                    links[format] = link
                                    _LOGGER.debug(f"Found {format} link: {link}")
                    except Exception:
                        pass
                for token in tokens:
                    try:
                        data = token["data"]["video"]["seekPreviewsURL"]
                        mo = re.search(r'^(https://[a-z0-9]+\.cloudfront.net/[a-f0-9]+_.+?_[0-9]+_[0-9]+)/', data)
                        if mo:
                            base = mo.group(1)
                            for format, idv in format_check.items():
                                link = await test_url(base, idv)
                                if link:
                                    links[format] = link
                                    _LOGGER.debug(f"Found {format} link: {link}")
                    except Exception:
                        pass

    except Exception:
        _LOGGER.error(traceback.format_exc())
    return links


if __name__ == "__main__":
    import certifi
    import os
    import asyncio

    os.environ['SSL_CERT_FILE'] = certifi.where()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_vod_link(1762458143))
