import logging
import aiohttp
import traceback
import re

_LOGGER = logging.getLogger(__name__)


async def get_vod_link(vodid):
    json = '[{"operationName": "VideoMetadata", "variables": {"channelLogin": "", "videoID": "%d"}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "49b5b8f268cdeb259d75b58dcb0c1a748e3b575003448a2333dc5cdafd49adad"}}}, {"operationName": "VideoPlayer_ChapterSelectButtonVideo", "variables": {"includePrivate": false, "videoID": "1762458143"}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "8d2793384aac3773beab5e59bd5d6f585aedb923d292800119e03d40cd0f9b41"}}}, {"operationName": "VideoPlayer_VODSeekbarPreviewVideo", "variables": {"includePrivate": false, "videoID": "1762458143"}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "07e99e4d56c5a7c67117a154777b0baf85a5ffefa393b213f4bc712ccaf85dd6"}}}]' % vodid

    url = "https://gql.twitch.tv/gql"
    headers = {'content-type': "text/plain;charset=UTF-8", "Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=json.encode('utf8'), headers=headers) as resp:
                tokens = await resp.json()
                _LOGGER.debug(f"Auth resp {tokens}")
                try:
                    data = tokens[0]["data"]["video"]["previewThumbnailURL"]
                    mo = re.search('/([a-z0-9]+)/([a-f0-9]+_.+?_[0-9]+_[0-9]+)/', data)
                    if mo:
                        link = f'https://{mo.group(1)}.cloudfront.net/{mo.group(2)}/chunked/index-dvr.m3u8'
                        return link
                except Exception:
                    pass
                data = tokens[0]["data"]["video"]["seekPreviewsURL"]
                mo = re.search(r'^(https://[a-z0-9]+\.cloudfront.net/[a-f0-9]+_.+?_[0-9]+_[0-9]+)/', data)
                if mo:
                    link = f'{mo.group(1)}/chunked/index-dvr.m3u8'
                    return link

    except Exception:
        _LOGGER.error(traceback.format_exc())
    return None


if __name__ == "__main__":
    import certifi
    import os
    import asyncio

    os.environ['SSL_CERT_FILE'] = certifi.where()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_vod_link(1762458143))
