import logging
import re
import traceback
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.wait import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
except ImportError:
    webdriver = None

from server.twitch_vod_id import vod_get_id
from server.twitch_vod_fuzz import verifyURL, checkURL

_LOGGER = logging.getLogger(__name__)


def get_end_link_part(driver, url, out_dict):
    try:
        myvid = vod_get_id(url)
        driver.get(url)
        links = WebDriverWait(driver, 30).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a[data-a-target="preview-card-image-link"]')))
        sellink = None
        for link in links:
            try:
                _LOGGER.debug(f'link -> {link.get_attribute("outerHTML")}')
                itsvid = vod_get_id(link.get_attribute('href'))
                _LOGGER.debug(f'Myvid {myvid} itsvid {itsvid} -> {link}')
                if itsvid == myvid:
                    sellink = link
                    break
            except Exception:
                pass
        if sellink:
            div = sellink.find_element(by=By.CSS_SELECTOR, value="div.preview-card-thumbnail__image > img")
            if div:
                lnk = div.get_attribute('src')
                _LOGGER.debug(f'link2 -> {lnk}')
                mo = re.search('/([a-z0-9]+)/([a-f0-9]+_.+?_[0-9]+_[0-9]+)/', lnk)
                if mo:
                    # url2 = f'https://{mo.group(1)}.cloudfront.net/{mo.group(2)}/chunked/index-dvr.m3u8'
                    out_dict['cloud'] = mo.group(1)
                    out_dict['end'] = mo.group(2)
                else:
                    mo = re.search('/([a-f0-9]+_.+?_[0-9]+_[0-9]+)/', lnk)
                    if mo:
                        out_dict['cloud'] = ''
                        out_dict['end'] = mo.group(1)
        # driver.quit()
    except Exception as ex:
        out_dict['err'] = str(ex)
        _LOGGER.error(traceback.format_exc())


async def get_vod_link(url, executor):
    if webdriver:
        chrome_options = Options()
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        # chrome_options.add_experimental_option("detach", True)
        driver = webdriver.Chrome(options=chrome_options)
        out_dict = dict()
        await executor(get_end_link_part, driver, url, out_dict)
        if 'end' in out_dict:
            if 'cloud' in out_dict:
                url2 = f'https://{out_dict["cloud"]}.cloudfront.net/{out_dict["end"]}/chunked/index-dvr.m3u8'
                if await checkURL(url2):
                    return [url2]
            return await verifyURL(f'/{out_dict["end"]}/chunked/index-dvr.m3u8')
        else:
            raise Exception('Link not found')
    else:
        raise Exception('Selenium not installed')
