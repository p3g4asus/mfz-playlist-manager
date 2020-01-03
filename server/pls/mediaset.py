from common.utils import AbstractMessageProcessor, MyEncoder
from common.const import (
    CMD_MEDIASET_PROGRAMS,
    CMD_MEDIASET_BRANDS,
    CMD_MEDIASET_LISTINGS,
    CMD_REFRESH,
    MSG_MEDIASET_INVALID_SUBBRAND,
    MSG_MEDIASET_BACKEND_ERROR,
    MSG_MEDIASET_INVALID_BRAND,
    MSG_MEDIASET_INVALID_DATE,
    MSG_PLAYLIST_NOT_FOUND,
    MSG_DB_ERROR,
    MSG_UNAUTHORIZED
)
from common.playlist import Playlist, PlaylistItem
import json
import aiohttp
import logging
import traceback
from datetime import datetime

_LOGGER = logging.getLogger(__name__)


class MessageProcessor(AbstractMessageProcessor):
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
                (startmillis, startmillis+2000*3600000/60, startFrom)

    def interested(self, msg):
        if msg.c(CMD_MEDIASET_PROGRAMS) or msg.c(CMD_MEDIASET_BRANDS) or msg.c(CMD_MEDIASET_LISTINGS):
            return True
        elif msg.c(CMD_REFRESH):
            x = msg.playlistObj()
            if x:
                return x.type == "mediaset"
            return False

    def isLastPage(self, jsond):
        return jsond['entryCount'] < jsond['itemsPerPage']

# https://feed.entertainment.tv.theplatform.eu/f/PR1GhC/mediaset-prod-all-programs?byCustomValue={brandId}{100000696},{subBrandId}{100000977}&sort=mediasetprogram$publishInfo_lastPublished|desc&count=true&entries=true&startIndex=1
# https://feed.entertainment.tv.theplatform.eu/f/PR1GhC/mediaset-prod-all-brands?byCustomValue={brandId}{100002223}&sort=mediasetprogram$order
# https://feed.entertainment.tv.theplatform.eu/f/PR1GhC/mediaset-prod-all-listings?byListingTime=1577001614000~1577001976000
    async def processBrands(self, msg, userid):
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
                                    return msg.ok(brands=list(brands.values()))
                                else:
                                    startFrom += js['itemsPerPage']
                            else:
                                return msg.err(12, MSG_MEDIASET_BACKEND_ERROR)

            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_MEDIASET_BACKEND_ERROR)
        else:
            return msg.err(15, MSG_MEDIASET_INVALID_BRAND)

    async def processListings(self, msg, userid):
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
                                        for l in e['listings']:
                                            if 'program' in l:
                                                if 'mediasetprogram$brandId' in l['program'] and\
                                                   'mediasetprogram$brandTitle' in l['program'] and\
                                                   l['program']['mediasetprogram$brandId'] not in brands:
                                                    title = l['program']['mediasetprogram$brandTitle']
                                                    id = l['program']['mediasetprogram$brandId']
                                                    starttime = l['startTime']
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
                                return msg.err(12, MSG_MEDIASET_BACKEND_ERROR)

            except Exception:
                return msg.err(11, MSG_MEDIASET_BACKEND_ERROR)
        else:
            return msg.err(14, MSG_MEDIASET_INVALID_DATE)

    def entry2Program(self, e, brand, subbrand, playlist):
        conf = dict(subbrand=subbrand, brand=brand)
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
        for imgo in e['thumbnails'].values():
            if 'title' in imgo and\
                imgo['title'] == 'Keyframe_Poster Image' and\
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

    async def processPrograms(self, msg, userid, playlist=None):
        brand = msg.f('brand', (int,))
        subbrands = msg.f('subbrands')
        datefrom = msg.f('datefrom', (int,))
        dateto = msg.f('dateto', (int,))
        if brand and subbrands:
            try:
                async with aiohttp.ClientSession() as session:
                    programs = dict()
                    for subbrand in subbrands:
                        startFrom = 1
                        while True:
                            async with session.get(MessageProcessor.programsUrl(brand, subbrand, startFrom)) as resp:
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
                                    return msg.err(12, MSG_MEDIASET_BACKEND_ERROR)
                    if not len(programs):
                        return msg.err(13, MSG_MEDIASET_INVALID_SUBBRAND)
                    else:
                        programs = list(programs.values())
                        programs.sort(key=lambda item: item.datepub)
                        return msg.ok(items=programs)
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_MEDIASET_BACKEND_ERROR)
        else:
            return msg.err(16, MSG_MEDIASET_INVALID_BRAND)

    async def processRefresh(self, msg, userid):
        x = msg.playlistObj()
        if x:
            if x.useri != userid:
                return msg.err(501, MSG_UNAUTHORIZED, playlist=None)
            try:
                msg.brand = x.conf['brand']['id']
                msg.subbrands = [s['id'] for s in x.conf['subbrands']]
            except (KeyError, AttributeError):
                _LOGGER.error(traceback.format_exc())
                return msg.err(11, MSG_MEDIASET_BACKEND_ERROR)
            datefrom = msg.f('datefrom')
            if datefrom is None:
                msg.datefrom = 0
            dateto = msg.f('dateto')
            if dateto is None:
                msg.dateto = 33134094791000
            if x.rowid is not None:
                c = x.conf
                n = x.name
                x = await Playlist.loadbyid(self.db, x.rowid)
                if x and len(x):
                    x = x[0]
                else:
                    return msg.err(5, MSG_PLAYLIST_NOT_FOUND, playlist=None)
                if x.useri != userid:
                    return msg.err(502, MSG_UNAUTHORIZED, playlist=None)
                x.conf = c
                x.name = n
            elif x.items is None:
                x.items = []
            resp = await self.processPrograms(msg, userid, playlist=x.rowid)
            if resp.rv == 0:
                for i in resp.items:
                    if i not in x.items:
                        x.items.append(i)
                        _LOGGER.debug("PlsItem new %s" % str(i))
                    else:
                        idx = x.items.index(i)
                        _LOGGER.debug("PlsItem exists %s. Is %s [%d]" % (str(i), x.items[idx], not x.items[idx].seen))
                        if not x.items[idx].seen:
                            x.items[idx] = i
                try:
                    rv = await x.toDB(self.db)
                    if rv:
                        return msg.ok(playlist=x)
                    else:
                        return msg.err(18, MSG_DB_ERROR, playlist=None)
                except Exception:
                    _LOGGER.error(traceback.format_exc())
                    return msg.err(20, MSG_DB_ERROR, playlist=None)
            else:
                return resp
        else:
            return msg.err(1, MSG_PLAYLIST_NOT_FOUND, playlist=None)

    async def process(self, ws, msg, userid):
        resp = None
        if msg.c(CMD_MEDIASET_BRANDS):
            resp = await self.processBrands(msg, userid)
        elif msg.c(CMD_MEDIASET_PROGRAMS):
            resp = await self.processPrograms(msg, userid)
        elif msg.c(CMD_REFRESH):
            resp = await self.processRefresh(msg, userid)
        elif msg.c(CMD_MEDIASET_LISTINGS):
            resp = await self.processListings(msg, userid)
        if resp:
            await ws.send_str(json.dumps(resp, cls=MyEncoder))
        return True
