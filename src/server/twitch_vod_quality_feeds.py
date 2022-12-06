from collections import OrderedDict


class VODQuality:
    def __init__(self, t, v, r, f):
        self.text = t
        self.video = v
        self.resolution = r
        self.fps = f

    def __str__(self):
        return self.text


QUALITIES_MAP = OrderedDict([
    ("Source", VODQuality("Source", "chunked", "source", 0.00)),
    ("QUADK60", VODQuality("4k60fps", "1080p60", "3840x2160", 60.000)),
    ("QUADK", VODQuality("4k30fps", "1080p30", "3840x2160", 30.000)),
    ("QHD4k60", VODQuality("2580p60fps", "1080p60fps", "2580x1080", 60.000)),
    ("QHD4k", VODQuality("2580p30fps", "1080p30", "2580x1080", 30.000)),
    ("QHD60", VODQuality("1440p60fps", "1080p60", "2560x1440", 60.000)),
    ("QHD", VODQuality("1440p30fps", "1080p30", "2560x1440", 60.000)),
    ("FHD60", VODQuality("1080p60fps", "1080p60", "1920x1080", 60.000)),
    ("FHD", VODQuality("1080p30fps", "1080p30", "1920x1080", 30.000)),
    ("FMHD60", VODQuality("936p60fps", "936p60", "1664x936", 60.000)),
    ("FMHD", VODQuality("936p30fps", "936p30", "1664x936", 30.000)),
    ("MHD60", VODQuality("900p60fps", "900p60", "1600x900", 60.000)),
    ("MHD", VODQuality("900p30fps", "900p30", "1600x900", 30.000)),
    ("HD60", VODQuality("720p60fps", "720p60", "1280x720", 60.000)),
    ("HD", VODQuality("720p30fps", "720p30", "1280x720", 30.000)),
    ("SHD160", VODQuality("480p60fps", "480p60", "852x480", 60.000)),
    ("SHD1", VODQuality("480p30fps", "480p30", "852x480", 30.000)),
    ("SHD260", VODQuality("360p60fps", "360p60", "640x360", 60.000)),
    ("SHD2", VODQuality("360p30fps", "360p30", "640x360", 30.000)),
    ("LHD60", VODQuality("160p60fps", "160p60", "284x160", 60.000)),
    ("LHD", VODQuality("160p30fps", "160p30", "284x160", 30.000)),
    ("SLHD60", VODQuality("144p60fps", "144p60", "256×144", 60.000)),
    ("SLHD", VODQuality("144p30fps", "144p30", "256×144", 30.000)),
    ("AUDIO", VODQuality("Audio only", "audio_only", "0x0", 0.000)),
])


def getQualityV(qual):
    for quality in QUALITIES_MAP.values():
        if quality.video == qual:
            return quality
    return None


def getQualityR(qual):
    for quality in QUALITIES_MAP.values():
        if quality.resolution == qual:
            return quality
    return None


def getQualityRF(res, fps):
    for quality in QUALITIES_MAP.values():
        if quality.resolution == res and quality.fps == fps:
            return quality
    return None


class FQ:
    def __init__(self, f, q) -> None:
        self.feed = f
        self.quality = q

    def get_idx(self):
        for i, q in enumerate(QUALITIES_MAP.values()):
            if q == self.quality:
                return i
        return -1

    def __lt__(self, other):
        return self.get_idx() < other.get_idx()


class Feeds:

    def __init__(self):
        self.fqs = []

    def sort(self):
        self.fqs.sort()

    def __len__(self):
        return len(self.fqs)

    def __bool__(self):
        return bool(self.fqs)

    def __str__(self) -> str:
        s = ''
        for i, fq in enumerate(self.fqs):
            s += f'{i + 1}) {fq.feed} [{fq.quality}]\n'
        return s

    def addEntry(self, f, q):
        self.fqs.append(FQ(f, q))

    def addEntryPos(self, f, q, i):
        self.fqs.insert(i, FQ(f, q))

    def getFeed(self, i):
        return self.fqs[i].feed

    def getFeedQual(self, q):
        for fq in self.fqs:
            if fq.quality == q:
                return fq.feed
        return None

    def getQuality(self, i):
        return self.fqs[i].quality

    def getQualityFeed(self, f):
        for fq in self.fqs:
            if fq.feed == f:
                return fq.quality
        return None

    def getFeeds(self):
        return self.fqs
