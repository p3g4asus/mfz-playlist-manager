import logging
import traceback
from datetime import datetime

import aiohttp
from common.const import (CMD_MEDIASET_BRANDS, CMD_MEDIASET_LISTINGS,
                          MSG_BACKEND_ERROR, MSG_INVALID_DATE,
                          MSG_MEDIASET_INVALID_BRAND, MSG_NO_VIDEOS, RV_NO_VIDEOS)
from common.playlist import PlaylistItem

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
        return msg.c(CMD_MEDIASET_BRANDS) or msg.c(CMD_MEDIASET_LISTINGS)

    def get_name(self):
        return "mediaset"

    def isLastPage(self, jsond):
        return jsond['entryCount'] < jsond['itemsPerPage']

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
        elif msg.c(CMD_MEDIASET_LISTINGS):
            resp = await self.processListings(msg, userid, executor)
        return resp
