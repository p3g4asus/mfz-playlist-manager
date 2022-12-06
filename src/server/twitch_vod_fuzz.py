import traceback
import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)

domains = []
domains_default = True


async def getDomains():
    global domains
    global domains_default
    if not domains or domains_default:
        domains_default = True
        domains = []
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            async with aiohttp.ClientSession() as session:
                async with session.get("https://raw.githubusercontent.com/TwitchRecover/TwitchRecover/main/domains.txt", headers=headers) as response:
                    text = await response.text()
                    for line in text.splitlines():
                        domains.append(line)
        except Exception:
            _LOGGER.error(traceback.format_exc())
        finally:
            if not domains:
                domains.append("https://vod-secure.twitch.tv")
                domains.append("https://vod-metro.twitch.tv")
                domains.append("https://d2e2de1etea730.cloudfront.net")
                domains.append("https://dqrpb9wgowsf5.cloudfront.net")
                domains.append("https://ds0h3roq6wcgc.cloudfront.net")
                domains.append("https://dqrpb9wgowsf5.cloudfront.net")
            else:
                domains_default = False
        _LOGGER.debug(f'Domains: {domains}')
    return domains


async def checkURL(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return True
    except Exception:
        _LOGGER.error(traceback.format_exc())
    return False


async def verifyURL(url):
    domains = await getDomains()
    results = []
    for d in domains:
        if await checkURL(d + url):
            results.append(d + url)
    return results
