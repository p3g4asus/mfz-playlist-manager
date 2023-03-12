import re


def single_regex(pattern, v):
    if v:
        mo = re.search(pattern, v)
        if mo:
            return mo.group(1)
    return None


def vod_get_id(url):
    ids = single_regex("twitch.tv/[a-z0-9]*/v/([0-9]+)", url)
    if ids:
        return int(ids)
    ids = single_regex("twitch.tv/[a-z0-9]*/videos/([0-9]+)", url)
    if ids:
        return int(ids)
    ids = single_regex("twitch.tv/videos/([0-9]+)", url)
    if ids:
        return int(ids)
    return int(url)
