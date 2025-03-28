from asyncio import Event, get_event_loop, run_coroutine_threadsafe, sleep, wait_for, TimeoutError
import contextlib
from functools import partial
import json
import logging
import re
import time
import traceback
from datetime import datetime
from typing import List

import aiohttp

from common.brand import DEFAULT_TITLE, Brand
from common.const import (CMD_MEDIASET_BRANDS, CMD_MEDIASET_KEYS,
                          CMD_MEDIASET_LISTINGS, MSG_BACKEND_ERROR,
                          MSG_INVALID_DATE, MSG_INVALID_PARAM,
                          MSG_MEDIASET_INVALID_BRAND, MSG_NO_VIDEOS,
                          MSG_PLAYLISTITEM_NOT_FOUND, MSG_UNAUTHORIZED,
                          RV_NO_VIDEOS)
from common.playlist import LOAD_ITEMS_NO, Playlist, PlaylistItem
from common.user import User

from .refreshmessageprocessor import RefreshMessageProcessor

_LOGGER = logging.getLogger(__name__)


class EventUrl(object):
    def __init__(self):
        self.evt = Event()
        self.url = None

    async def wait(self, timeout):
        with contextlib.suppress(TimeoutError):
            await wait_for(self.evt.wait(), timeout)
        return self.url

    def set(self, url):
        self.url = url
        self.evt.set()


class MessageProcessor(RefreshMessageProcessor):
    GET_CALL_SIGN_URL = 'https://feed.entertainment.tv.theplatform.eu/f/PR1GhC/mediaset-prod-all-stations-v2?fields=callSign,title,guid&form=cjson&httpError=true'
    INOCULATE_SCR = """
function dyn_module_load(link, onload, type) {
    let tag;
    if (type == 'css') {
        tag = document.createElement('link');
        tag.setAttribute('rel', 'stylesheet');
        tag.setAttribute('type', 'text/css');
        tag.setAttribute('href', link);
    }
    else {
        tag = document.createElement('script');
        tag.type = 'text/javascript';
        if (link.startsWith('//'))
            tag.text = link.substring(2);
        else
            tag.src = link;
    }
    if (onload) {
        tag.addEventListener('load', function(event) {
            console.log('script loaded ' + link);
            onload();
        });
    }
    let firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
}
dyn_module_load('//var login_needed = 0;');
var callback = arguments[arguments.length - 1];
dyn_module_load('https://code.jquery.com/jquery-3.7.1.slim.min.js', function() {
    $.noConflict();
    setTimeout(function() {
        callback(1);
    }, 3000);
});
"""

    INOCULATE_SCR2 = """
var callback = arguments[arguments.length - 1];
if (typeof(login_needed) !== 'undefined' && login_needed < 5000) {
    let spanacc = jQuery('span:contains("accesso")');
    login_needed = spanacc.length;
    console.log('login needed = ' + login_needed);
    if (login_needed) {
        login_needed = 5000;
        callback(1);
    } else callback(0);
} else callback(0);
"""

    INOCULATE_SCR3 = """
var callback = arguments[arguments.length - 1];
if (login_needed == 5000) {
    let login_log = 1;
    let $el = jQuery('div:contains("Login/R")');
    login_log |= ($el.length?2:0);
    $el.click();
    let tt = 0;
    const d1 = %d;
    const d2 = %d;
    const fn1 = function() {
        $el = jQuery('input[value*="Accedi con email"');
        login_log |= ($el.length?32:0);
        if (login_log&32) {
            $el.click();
            tt = 0;
            const fn2 = function() {
                $el = jQuery('input[name=username]');
                login_log |= ($el.length?4:0);
                $el.val('%s');
                $el = jQuery('input[name=password]');
                login_log |= ($el.length?8:0);
                $el.val('%s');
                $el = jQuery('input[value=Continua]');
                login_log |= ($el.length?16:0);
                if ((login_log&28) == 28) {
                    $el.click();
                    console.log('Exiting from script with ' + login_log);
                    callback(login_log);
                } else {
                    tt += 1000;
                    if (tt < d2) setTimeout(fn2, 1000);
                    else {
                        console.log('Exiting from script with ' + login_log);
                        callback(login_log);
                    }
                }
            }
            setTimeout(fn2, 1000);
        } else {
            tt += 1000;
            if (tt < d1) setTimeout(fn1, 1000);
            else {
                console.log('Exiting from script with ' + login_log);
                callback(login_log);
            }
        }
    }
    setTimeout(fn1, 1000);
} else callback(0);
"""

    def __init__(self, db, d1=4, d2=4, d3=65, drmurl='http://127.0.0.1:1337/api/decrypt', getsmil='selenium', **kwargs):
        self.d1 = d1
        self.d2 = d2
        self.d3 = d3
        self.drmurl = drmurl
        self.getsmil = self.processGetSMILSelenium if getsmil == 'selenium' else self.processGetSMILPlaywright
        super().__init__(db, **kwargs)

    @staticmethod
    def programsUrl(brand, subbrand, startFrom):
        return ('https://feed.entertainment.tv.theplatform.eu/'
                'f/PR1GhC/mediaset-prod-all-programs-v2?'
                'byCustomValue={brandId}{%d},{subBrandId}{%d}'
                '&sort=mediasetprogram$publishInfo_lastPublished|desc'
                '&count=true&entries=true&startIndex=%d') %\
               (brand, subbrand, startFrom)

    @staticmethod
    def brandsUrl(brand, startFrom):
        return 'https://feed.entertainment.tv.theplatform.eu/f/PR1GhC/mediaset-prod-all-programs-v2?byCustomValue={brandId}{%d}&count=true&entries=true&startIndex=%d' % (brand, startFrom)

    @staticmethod
    def listingsUrl(startmillis: int, cs: str, startFrom: int):
        return f'https://api-ott-prod-fe.mediaset.net/PROD/play/feed/allListingFeedEpg/v2.0?byListingTime={startmillis}~{startmillis + 86400000-60000}&byCallSign={cs}&startIndex={startFrom}'

    def interested_plus(self, msg):
        return msg.c(CMD_MEDIASET_BRANDS) or msg.c(CMD_MEDIASET_LISTINGS) or msg.c(CMD_MEDIASET_KEYS)

    def get_name(self):
        return "mediaset"

    def isLastPage(self, jsond):
        return jsond['entryCount'] < jsond['itemsPerPage']

    async def get_user_credentials(self, userid):
        setts = await User.get_settings(self.db, userid, 'mediaset_user', 'mediaset_password')
        return None if not setts or not setts[0] or not setts[1] else setts

    def processGetSMILSeleniumInner(self, url, resp, userid, loop):
        resp['sta'] = 'N/A'
        driver = None
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.wait import WebDriverWait

            def log_filter(log_):
                try:
                    return log_['params']['request']['url'].find('SMIL') > 0
                except Exception:
                    return False

            chrome_options = Options()
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36")
            chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})  # newer: goog:loggingPrefs

            driver = webdriver.Chrome(options=chrome_options)
            tstart = time.time()
            driver.get(url)
            try:
                elems = WebDriverWait(driver, 30).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '#rti-privacy-accept-btn-screen1-id')))
                # time.sleep(30)
                resp['sta'] = 'w1-' + str(int((time.time() - tstart) * 1000))
                if elems:
                    for e in elems:
                        if e.tag_name == 'button':
                            e.click()
            except Exception:
                resp['sta'] = 'w1-0'
            tstart = time.time()
            scriptload = False
            waitdone = 0
            uspw = None
            while True:
                logs_raw = driver.get_log("performance")
                logs = [json.loads(lr["message"])["message"] for lr in logs_raw]
                for log in filter(log_filter, logs):
                    resp['sta'] += '-w2-' + str(int((time.time() - tstart) * 1000))
                    resp['link'] = log['params']['request']['url']
                    resp['err'] = 0
                    tstart = -1
                    break
                if tstart < 0:
                    break
                else:
                    if time.time() - tstart > self.d3:
                        resp['err'] = 32
                        break
                    else:
                        if not scriptload:
                            driver.execute_async_script(self.INOCULATE_SCR)
                            scriptload = True
                            waitdone = 1
                        if waitdone >= 0 and driver.execute_async_script(self.INOCULATE_SCR2):
                            fut = run_coroutine_threadsafe(self.get_user_credentials(userid), loop)
                            uspw = fut.result()
                            if uspw:
                                rv = driver.execute_async_script(self.INOCULATE_SCR3 % (int(self.d1 * 1000), int(self.d2 * 1000), *uspw))
                                tstart = time.time()
                                _LOGGER.info('[mediaset] SMIL need login: inserted -> ' + str(rv))
                                resp['sta'] += f'-l-{rv}'
                            else:
                                resp['sta'] += '-l-0'
                            waitdone = -1
                        if waitdone <= 0:
                            time.sleep(3)
                        else:
                            waitdone = 0
        except ImportError:
            resp['err'] = 31
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

    async def processGetSMILSelenium(self, url, userid, executor):
        out_resp = dict()
        await executor(self.processGetSMILSeleniumInner, url, out_resp, userid, get_event_loop())
        _LOGGER.info(f'[mediaset] SMIL get sta={out_resp["sta"]} err={out_resp["err"]}')
        return out_resp['err'] if 'err' in out_resp and out_resp['err'] else out_resp['link']

    async def processGetSMILPlaywrightInner(self, playwright, *, url: str, userid: int) -> dict:
        from playwright.async_api import Playwright
        playwright: Playwright = playwright
        intercepted = EventUrl()
        exit_value = 0

        async def handle(route, *_, **kwargs):
            _LOGGER.debug("Intercepted: ", route)
            await route.continue_()
            if 'intercepted' in kwargs:
                kwargs['intercepted'].set(route.request.url)

        browser = await playwright.chromium.launch(
            headless=False,
            ignore_default_args=["--headless"],
            args=["--headless=new"],
        )
        context = await browser.new_context(**playwright.devices['Pixel 7'])

        # Open a new browser page.
        for _ in range(3):
            try:
                page = await wait_for(context.new_page(), timeout=30)
                exit_value |= 128
                break
            except TimeoutError as ex0:
                _LOGGER.debug(f"[mediaset-get-smil] Timeout! 0({exit_value}) -> {ex0}")
        if not page:
            await browser.close()
            return {'url': url, 'title': None, 'smilurl': None, 'exit_value': exit_value}
        await context.route(re.compile(r"format=SMIL"), partial(handle, intercepted=intercepted))

        # Short sleep to be able to see the browser in action.
        await sleep(1)

        # Navigate to the specified URL.
        await page.goto(url)
        try:
            await page.locator("#rti-privacy-accept-btn-screen1-id").click(timeout=30000)
            exit_value |= 1
            await sleep(3)
        except Exception as ex1:
            _LOGGER.debug(f"[mediaset-get-smil] Timeout! 1({exit_value}) -> {ex1}")
        tstart = time.time()

        # Intercept the route to the fruit API
        while not intercepted.url:
            now = time.time()
            if now - tstart < self.d3:
                try:
                    await page.get_by_text("Login/Registrati").click(timeout=10000)
                    exit_value |= 2
                    await sleep(3)
                    try:
                        await page.get_by_text(re.compile("^Accedi con email"), exact=False).click(timeout=self.d1 * 1000 + 10000)
                        exit_value |= 4
                        await sleep(3)
                        uspw = await self.get_user_credentials(userid)
                        if uspw:
                            await page.get_by_placeholder("Password").fill(uspw[1], timeout=self.d2 * 1000 + 10000)
                            exit_value |= 8
                            await sleep(3)
                            await page.get_by_placeholder("email").fill(uspw[0], timeout=10000)
                            exit_value |= 16
                            await sleep(3)
                            await page.get_by_text("Continua").click(timeout=10000)
                            exit_value |= 32
                        break
                    except Exception as ex3:
                        _LOGGER.debug(f"[mediaset-get-smil] Timeout! 3({exit_value}) -> {ex3}")
                        break
                except Exception as ex2:
                    _LOGGER.debug(f"[mediaset-get-smil] Timeout! 2({exit_value}) -> {ex2}")
            else:
                break
            await sleep(1)
        smilurl = await intercepted.wait(self.d3)
        if smilurl is not None:
            exit_value |= 64

        # Retrieve the title of the page.
        title = await page.title()

        # Close the browser.
        await browser.close()

        # Return the page's URL and title as a dictionary.
        return {'url': url, 'title': title, 'smilurl': smilurl, 'exit_value': exit_value}

    async def processGetSMILPlaywright(self, url, userid, executor):
        from playwright.async_api import async_playwright
        result = None
        async with async_playwright() as playwright:
            result = await self.processGetSMILPlaywrightInner(playwright, url=url, userid=userid)
            _LOGGER.info(f'[mediaset] SMIL get sta={result["exit_value"]}')
        return result['exit_value'] if not (result['exit_value'] & 64) else result['smilurl']

    async def processKeyGet(self, msg, userid, executor):
        x = msg.playlistItemId()
        it = await PlaylistItem.loadbyid(self.db, rowid=x)
        if it:
            pls = await Playlist.loadbyid(self.db, rowid=it.playlist, loaditems=LOAD_ITEMS_NO)
            if pls:
                if pls[0].useri != userid:
                    return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
                try:
                    msg.smil = None if len(msg.smil) < 10 else msg.smil
                    if not msg.smil and 'pageurl' in it.conf:
                        rv = await self.getsmil(it.conf['pageurl'], userid, executor)
                        if isinstance(rv, int):
                            return msg.err(rv, MSG_BACKEND_ERROR)
                        else:
                            smil = rv
                    elif not msg.smil:
                        return msg.err(20, MSG_INVALID_PARAM)
                    else:
                        smil = msg.smil
                    headers = {
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                        'Connection': 'keep-alive',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36',
                    }
                    url = smil
                    token = re.findall(r'auth=(.*?)&', url)[0].strip()

                    headers = {
                        'Accept': 'application/json, text/plain, */*',
                        'Origin': 'https://mediasetinfinity.mediaset.it',
                        'Referer': 'https://mediasetinfinity.mediaset.it/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
                    }

                    async with aiohttp.ClientSession(headers=headers) as session:
                        _LOGGER.debug("Mediaset: Getting SMIL from " + url)
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                response = await resp.text()
                                mpd = re.findall(r'<video src=\"(.*?)\"', response)[0].strip()
                                pid = re.findall(r'\|pid=(.*?)\|', response)[0].strip()
                                aid = re.findall(r'value=\"aid=(.*?)\|', response)[0].strip()
                                # pgid = re.findall(r'\|pgid=(.*?)\|', response)[0].strip()
                            else:
                                return msg.err(7, MSG_BACKEND_ERROR)
                    lic_url = f'https://widevine.entitlement.theplatform.eu/wv/web/ModularDrm/getRawWidevineLicense?releasePid={pid}&account=http%3A%2F%2Faccess.auth.theplatform.com%2Fdata%2FAccount%2F{aid}&schema=1.0&token={token}'
                    async with aiohttp.ClientSession(headers=headers) as session:
                        url = mpd
                        _LOGGER.debug("Mediaset: Getting mhd from " + url)
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                response = await resp.text()
                                pssh = re.findall(r'<cenc:pssh>(.{20,170})</cenc:pssh>', response)[0].strip()
                            else:
                                return msg.err(10, MSG_BACKEND_ERROR)
                    it.conf['_drm_p'] = pid
                    it.conf['_drm_a'] = aid
                    it.conf['_drm_t'] = token
                    it.conf['_drm_m'] = mpd
                    drmi = it.conf['_drm_i'] = f'b{it.conf["brand"]}s{it.conf["subbrand"]}'
                    plc = pls[0].conf
                    if '_drm_i' not in plc or drmi not in plc['_drm_i']:
                        plc['_drm_i'] = plc.get('_drm_i', [])
                        plc['_drm_i'].append(drmi)
                        await pls[0].toDB(self.db, commit=False)
                    try:
                        headers_clone = {
                            'Connection': 'keep-alive',
                            'Content-Type': 'application/json',
                            'Origin': 'https://wvclone.fly.dev',
                            'Referer': 'https://wvclone.fly.dev/',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36',
                        }
                        json_data_clone = {
                            'pssh': pssh,
                            'licurl': lic_url,
                            'headers': str({
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0',
                                'Accept': '*/*',
                                'Connection': 'keep-alive',
                                'Accept-Language': 'en-US,en;q=0.5',
                            })
                        }
                        async with aiohttp.ClientSession(headers=headers_clone) as session:
                            url = self.drmurl
                            _LOGGER.debug("Mediaset: Getting key data from " + url)
                            async with session.post(url, json=json_data_clone) as resp:
                                if resp.status == 200:
                                    clone_resp = await resp.json(content_type=None)
                                    keys = clone_resp['message'].split(':')
                                    if keys:
                                        it.conf['_drm_k'] = keys
                    except Exception:
                        _LOGGER.warning(f'[mediaset] Get key failed: {traceback.format_exc()}')
                    if await it.toDB(self.db, commit=True):
                        return msg.ok(playlistitem=it)
                    else:
                        return msg.err(9, MSG_BACKEND_ERROR)
                except Exception:
                    _LOGGER.warning(f'[Mediaset key get] Error grtting key {traceback.format_exc()}')
                    return msg.err(12, MSG_BACKEND_ERROR)
            else:
                return msg.err(3, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)
        else:
            return msg.err(1, MSG_PLAYLISTITEM_NOT_FOUND, playlistitem=None)

# https://feed.entertainment.tv.theplatform.eu/f/PR1GhC/mediaset-prod-all-programs?byCustomValue={brandId}{100000696},{subBrandId}{100000977}&sort=mediasetprogram$publishInfo_lastPublished|desc&count=true&entries=true&startIndex=1
# https://feed.entertainment.tv.theplatform.eu/f/PR1GhC/mediaset-prod-all-brands?byCustomValue={brandId}{100002223}&sort=mediasetprogram$order
# https://feed.entertainment.tv.theplatform.eu/f/PR1GhC/mediaset-prod-all-listings?byListingTime=1577001614000~1577001976000
    async def processBrands(self, msg, userid, executor):
        brand = msg.f('brand', (int,))
        if brand:
            try:
                async with aiohttp.ClientSession() as session:
                    startFrom = 1
                    brands: List[Brand] = []
                    bdetails = dict()
                    while True:
                        url = MessageProcessor.brandsUrl(brand, startFrom)
                        _LOGGER.debug("Mediaset: Getting processBrands " + url)
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                js = await resp.json()
                                _LOGGER.debug("Mediaset: Rec processBrands " + str(js))
                                for e in js['entries']:
                                    if 'mediasetprogram$subBrandId' in e and\
                                       (brid := int(e['mediasetprogram$subBrandId'])) not in brands:
                                        brands.append(Brand(brid, e.get('mediasetprogram$subBrandTitle', DEFAULT_TITLE), e.get('mediasetprogram$subBrandDescription', '')))
                                        if not bdetails and 'mediasetprogram$brandTitle' in e and (ttl := e['mediasetprogram$brandTitle']):
                                            bdetails['title'] = ttl
                                if self.isLastPage(js):
                                    if not brands:
                                        return msg.err(18, MSG_MEDIASET_INVALID_BRAND)
                                    else:
                                        _LOGGER.debug("Brands found %s" % str(brands))
                                        return msg.ok(brands=brands, **bdetails)
                                else:
                                    startFrom += js['itemsPerPage']
                            else:
                                return msg.err(12, MSG_BACKEND_ERROR)
                return msg.err(19, MSG_MEDIASET_INVALID_BRAND)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(15, MSG_MEDIASET_INVALID_BRAND)

    async def processListings(self, msg, userid, executor):
        datestart = msg.f('datestart', (int,))
        if datestart:
            try:
                async with aiohttp.ClientSession() as session:
                    css = []
                    async with session.get(MessageProcessor.GET_CALL_SIGN_URL) as resp:
                        if resp.status == 200:
                            js = await resp.json()
                            css = js.get('entries', [])
                        else:
                            return msg.err(14, MSG_BACKEND_ERROR)
                    brands: List[Brand] = list()
                    for cso in css:
                        try:
                            cs = cso.get('callSign')
                            startFrom = 1
                            while True:
                                url = MessageProcessor.listingsUrl(datestart, cs, startFrom)
                                _LOGGER.debug("Mediaset: Getting " + url)
                                async with session.get(url) as resp:
                                    if resp.status == 200:
                                        js = await resp.json()
                                        _LOGGER.debug("Mediaset: Rec " + str(js))
                                        if 'response' not in js or (js := js['response'])['startIndex'] != startFrom:
                                            break
                                        for e in js['entries']:
                                            if 'listings' in e:
                                                for lst in e['listings']:
                                                    if 'program' in lst:
                                                        if 'mediasetprogram$brandId' in (lstp := lst['program']) and\
                                                            'mediasetprogram$brandTitle' in lstp and\
                                                                (brid := int(lstp['mediasetprogram$brandId'])) not in brands:
                                                            title = lstp['mediasetprogram$brandTitle']
                                                            desc = lstp.get('mediasetprogram$brandDescription', '')
                                                            brands.append(Brand(
                                                                brid,
                                                                title,
                                                                desc
                                                            ))

                                        if self.isLastPage(js):
                                            break
                                        else:
                                            startFrom += js['itemsPerPage']
                                    else:
                                        return msg.err(12, MSG_BACKEND_ERROR)
                        except Exception:
                            _LOGGER.warning(f'Error getting listings for {cs} -> {traceback.format_exc()}')
                    if brands:
                        brands.sort(key=lambda item: item.title)
                        return msg.ok(brands=brands)
                return msg.err(15, MSG_BACKEND_ERROR)
            except Exception:
                _LOGGER.warning(f'Error searching for listings {traceback.format_exc()}')
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(14, MSG_INVALID_DATE)

    def entry2Program(self, e, brand, subbrand, playlist):
        lnk = e.get('mediasetprogram$videoPageUrl')
        conf = dict(subbrand=subbrand, brand=brand, pageurl=f'https:{lnk}' if lnk else None)
        title = e['title']
        uid = e['guid']
        img = None
        # minheight = 1300
        # for imgo in e['thumbnails'].values():
        #     if 'title' in imgo and\
        #         imgo['title'] == 'Keyframe_Poster Image' and\
        #        (not img or imgo['height'] < minheight):
        #         minheight = imgo['height']
        #         img = imgo['url']
        maxheight = 0
        _LOGGER.debug("ThumbMed = %s" % str(e['thumbnails'].values()))
        for imgo in e['thumbnails'].values():
            if 'title' in imgo and\
                (imgo['title'] == 'Keyframe_Poster Image'
                 or imgo['title'].startswith('image_keyframe_poster')) and\
               (not img or imgo['height'] > maxheight):
                maxheight = imgo['height']
                img = imgo['url']
        datepubi = e["mediasetprogram$publishInfo_lastPublished"]
        datepubo = datetime.fromtimestamp(datepubi / 1000)
        datepub = datepubo.strftime('%Y-%m-%d %H:%M:%S.%f')
        dur = e["mediasetprogram$duration"]
        link = e["media"][0]["publicUrl"]
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

    async def processPrograms(self, msg, datefrom=0, dateto=33134094791000, conf=dict(), playlist=None, userid=None, executor=None):
        try:
            brand = conf['brand']['id']
            brandt = conf['brand']['title'] if 'title' in conf['brand'] else brand
            subbrands = [(s['id'], s['desc'] if 'desc' in s and s['desc'] else s['title']) for s in conf['subbrands']]
        except (KeyError, AttributeError):
            _LOGGER.error(traceback.format_exc())
            return msg.err(11, MSG_BACKEND_ERROR)
        if brand and subbrands:
            sta = msg.init_send_status_with_ping(ss=[])
            try:
                async with aiohttp.ClientSession() as session:
                    programs = dict()
                    for subbrand, title in subbrands:
                        startFrom = 1
                        while True:
                            url = MessageProcessor.programsUrl(brand, subbrand, startFrom)
                            self.record_status(sta, f'\U0001F194 Set {brandt} - {title}', 'ss')
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    js = await resp.json()
                                    for e in js['entries']:
                                        try:
                                            (pr, datepubi) = self.entry2Program(e, brand, subbrand, playlist)
                                            _LOGGER.debug("Found [%s] = %s" % (pr.uid, str(pr)))
                                            self.record_status(sta, f'\U0001F50D Found {pr.title} [{pr.datepub}]', 'ss')
                                            if pr.uid not in programs and datepubi >= datefrom and\
                                               (datepubi <= dateto or dateto < datefrom):
                                                programs[pr.uid] = pr
                                                self.record_status(sta, f'\U00002795 Added {pr.title} [{pr.datepub}]', 'ss')
                                                _LOGGER.debug("Added [%s] = %s" % (pr.uid, str(pr)))
                                        except Exception as ex:
                                            self.record_status(sta, f'\U000026A0 Error 0: {repr(ex)}', 'ss')
                                            _LOGGER.error(traceback.format_exc())
                                    if self.isLastPage(js):
                                        break
                                    else:
                                        startFrom += js['itemsPerPage']
                                else:
                                    self.record_status(sta, '\U000026A0 Error 12', 'ss')
                                    return msg.err(12, MSG_BACKEND_ERROR)
                    if not len(programs):
                        self.record_status(sta, f'\U000026A0 {MSG_NO_VIDEOS}', 'ss')
                        return msg.err(RV_NO_VIDEOS, MSG_NO_VIDEOS)
                    else:
                        programs = list(programs.values())
                        programs.sort(key=lambda item: item.datepub)
                        return msg.ok(items=programs)
            except Exception as ex:
                _LOGGER.error(traceback.format_exc())
                self.record_status(sta, f'\U000026A0 Error 11: {repr(ex)}', 'ss')
                return msg.err(11, MSG_BACKEND_ERROR)
        else:
            return msg.err(16, MSG_MEDIASET_INVALID_BRAND)

    async def getResponse(self, msg, userid, executor):
        resp = None
        if msg.c(CMD_MEDIASET_BRANDS):
            resp = await self.processBrands(msg, userid, executor)
        elif msg.c(CMD_MEDIASET_KEYS):
            resp = await self.processKeyGet(msg, userid, executor)
        elif msg.c(CMD_MEDIASET_LISTINGS):
            resp = await self.processListings(msg, userid, executor)
        return resp
