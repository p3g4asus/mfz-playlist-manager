import json
import logging
import re
import time
import traceback
from datetime import datetime

import aiohttp

from common.const import (CMD_MEDIASET_BRANDS, CMD_MEDIASET_KEYS,
                          CMD_MEDIASET_LISTINGS, MSG_BACKEND_ERROR,
                          MSG_INVALID_DATE, MSG_INVALID_PARAM,
                          MSG_MEDIASET_INVALID_BRAND, MSG_NO_VIDEOS,
                          MSG_PLAYLISTITEM_NOT_FOUND, MSG_UNAUTHORIZED,
                          RV_NO_VIDEOS)
from common.playlist import LOAD_ITEMS_NO, Playlist, PlaylistItem

from .refreshmessageprocessor import RefreshMessageProcessor

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(RefreshMessageProcessor):
    @staticmethod
    def programsUrl(brand, subbrand, startFrom):
        return ('https://feed.entertainment.tv.theplatform.eu/'
                'f/PR1GhC/mediaset-prod-all-programs?'
                'byCustomValue={brandId}{%d},{subBrandId}{%d}'
                '&sort=mediasetprogram$publishInfo_lastPublished|desc'
                '&count=true&entries=true&startIndex=%d') %\
               (brand, subbrand, startFrom)

    @staticmethod
    def brandsUrl(brand, startFrom):
        return ('https://feed.entertainment.tv.theplatform.eu/'
                'f/PR1GhC/mediaset-prod-all-brands?'
                'byCustomValue={brandId}{%d}&sort=mediasetprogram$order'
                '&count=true&entries=true&startIndex=%d') %\
               (brand, startFrom)

    @staticmethod
    def listingsUrl(startmillis, startFrom):
        return ('https://feed.entertainment.tv.theplatform.eu/'
                'f/PR1GhC/mediaset-prod-all-listings?'
                'byListingTime=%d~%d'
                '&count=true&entries=true&startIndex=%d') %\
               (startmillis, startmillis + 2000 * 3600000 / 60, startFrom)

    def interested_plus(self, msg):
        return msg.c(CMD_MEDIASET_BRANDS) or msg.c(CMD_MEDIASET_LISTINGS) or msg.c(CMD_MEDIASET_KEYS)

    def get_name(self):
        return "mediaset"

    def isLastPage(self, jsond):
        return jsond['entryCount'] < jsond['itemsPerPage']

    def processGetSMIL(self, url, resp):
        resp['sta'] = 'N/A'
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
                    if time.time() - tstart > 65:
                        resp['err'] = 32
                        break
                    else:
                        time.sleep(3)
        except ImportError:
            resp['err'] = 31

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
                        out_resp = dict()
                        await executor(self.processGetSMIL, it.conf['pageurl'], out_resp)
                        _LOGGER.info(f'[mediaset] SMIL get sta={out_resp["sta"]} err={out_resp["err"]}')
                        if 'err' in out_resp and out_resp['err']:
                            return msg.err(out_resp['err'], MSG_BACKEND_ERROR)
                        smil = out_resp['link']
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
                    try:
                        headers_clone = {
                            'Connection': 'keep-alive',
                            'Content-Type': 'application/json',
                            'Origin': 'https://wvclone.fly.dev',
                            'Referer': 'https://wvclone.fly.dev/',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36',
                        }
                        json_data_clone = {
                            'password': 'password',
                            'license': lic_url,
                            'headers': 'Connection: keep-alive\n',
                            'pssh': pssh,
                            'buildInfo': '',
                            'cache': True,
                        }
                        async with aiohttp.ClientSession(headers=headers_clone) as session:
                            url = 'https://cdrm-project.com/api'
                            _LOGGER.debug("Mediaset: Getting key data from " + url)
                            async with session.post(url, json=json_data_clone) as resp:
                                if resp.status == 200:
                                    clone_resp = await resp.json(content_type=None)
                                    keys = [a['key'] for a in clone_resp['keys']]
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
                    brands = dict()
                    while True:
                        url = MessageProcessor.brandsUrl(brand, startFrom)
                        _LOGGER.debug("Mediaset: Getting processBrands " + url)
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                js = await resp.json()
                                _LOGGER.debug("Mediaset: Rec processBrands " + str(js))
                                title = ''
                                for e in js['entries']:
                                    if 'mediasetprogram$subBrandId' in e and\
                                       e['mediasetprogram$subBrandId'] not in brands:
                                        id = e['mediasetprogram$subBrandId']
                                        brands[id] = dict(
                                            title=title,
                                            id=int(id),
                                            desc=e['description']
                                        )
                                    else:
                                        title = e['title']

                                if self.isLastPage(js):
                                    if not brands:
                                        return msg.err(18, MSG_MEDIASET_INVALID_BRAND)
                                    else:
                                        _LOGGER.debug("Brands found %s" % str(brands))
                                        return msg.ok(brands=list(brands.values()))
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
                    startFrom = 1
                    brands = dict()
                    while True:
                        url = MessageProcessor.listingsUrl(datestart, startFrom)
                        _LOGGER.debug("Mediaset: Getting " + url)
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                js = await resp.json()
                                _LOGGER.debug("Mediaset: Rec " + str(js))
                                for e in js['entries']:
                                    if 'listings' in e:
                                        for lst in e['listings']:
                                            if 'program' in lst:
                                                if 'mediasetprogram$brandId' in lst['program'] and\
                                                   'mediasetprogram$brandTitle' in lst['program'] and\
                                                   lst['program']['mediasetprogram$brandId'] not in brands:
                                                    title = lst['program']['mediasetprogram$brandTitle']
                                                    id = lst['program']['mediasetprogram$brandId']
                                                    starttime = lst['startTime']
                                                    brands[id] = dict(
                                                        title=title,
                                                        id=int(id),
                                                        starttime=starttime
                                                    )

                                if self.isLastPage(js):
                                    brands = list(brands.values())
                                    brands.sort(key=lambda item: item['title'])
                                    return msg.ok(brands=brands)
                                else:
                                    startFrom += js['itemsPerPage']
                            else:
                                return msg.err(12, MSG_BACKEND_ERROR)
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

    async def processPrograms(self, msg, datefrom=0, dateto=33134094791000, conf=dict(), playlist=None, executor=None):
        try:
            brand = conf['brand']['id']
            subbrands = [s['id'] for s in conf['subbrands']]
        except (KeyError, AttributeError):
            _LOGGER.error(traceback.format_exc())
            return msg.err(11, MSG_BACKEND_ERROR)
        if brand and subbrands:
            try:
                async with aiohttp.ClientSession() as session:
                    programs = dict()
                    for subbrand in subbrands:
                        startFrom = 1
                        while True:
                            url = MessageProcessor.programsUrl(brand, subbrand, startFrom)
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    js = await resp.json()
                                    for e in js['entries']:
                                        try:
                                            (pr, datepubi) = self.entry2Program(e, brand, subbrand, playlist)
                                            _LOGGER.debug("Found [%s] = %s" % (pr.uid, str(pr)))
                                            if pr.uid not in programs and datepubi >= datefrom and\
                                               (datepubi <= dateto or dateto < datefrom):
                                                programs[pr.uid] = pr
                                                _LOGGER.debug("Added [%s] = %s" % (pr.uid, str(pr)))
                                        except Exception:
                                            _LOGGER.error(traceback.format_exc())
                                    if self.isLastPage(js):
                                        break
                                    else:
                                        startFrom += js['itemsPerPage']
                                else:
                                    return msg.err(12, MSG_BACKEND_ERROR)
                    if not len(programs):
                        return msg.err(RV_NO_VIDEOS, MSG_NO_VIDEOS)
                    else:
                        programs = list(programs.values())
                        programs.sort(key=lambda item: item.datepub)
                        return msg.ok(items=programs)
            except Exception:
                _LOGGER.error(traceback.format_exc())
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
