import _thread
import asyncio
import json
import logging
import logging.config
import sys
import traceback
from functools import partial
from queue import SimpleQueue
from threading import Thread

import yt_dlp as youtube_dl
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

_LOGGER = logging.getLogger(__name__)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'local': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        }
    },
    'handlers': {
        'console2': {
            'class': 'logging.StreamHandler',
            'formatter': 'local',
            'stream': 'ext://sys.stdout'
        },
    },
    'root': {
        'handlers': ['console2'],
    },
    # 'loggers': {
    #     'server': {
    #         'handlers': ['console2']
    #     },
    #     'webhandlers': {
    #         'handlers': ['console2']
    #     },
    #     'sqliteauth': {
    #         'handlers': ['console2']
    #     },
    #     'common': {
    #         'handlers': ['console2']
    #     },
    #     'pls': {
    #         'handlers': ['console2']
    #     },
    # }
}


def safe_serialize_replace(o):
    return f"<<non-serializable: {type(o).__qualname__}>>"


def safe_serialize(obj):
    return json.dumps(obj, default=safe_serialize_replace)


class OSCThread(Thread):
    def __init__(self, p1: int, p2: int, queue: SimpleQueue) -> None:
        super().__init__(name='OSCThread', daemon=False)
        self.myport = p1
        self.hisport = p2
        self.client = None
        self.queue = queue
        self.server = None
        self.loop = asyncio.new_event_loop()

    def start_job(self, _, url, json_q) -> None:
        if url and json_q and isinstance(json_q, str):
            try:
                objd = json.loads(json_q)
                _LOGGER.info(f'Put in queue {url}, {objd}')
                self.queue.put((url, objd))
                return
            except Exception:
                pass
        self.queue.put(None)

    def halt_job(self, *_):
        _thread.interrupt_main()

    def destroy(self, *_):
        self.loop.stop()

    def exit(self, exits):
        self.client.send_message('/jobdone', safe_serialize(exits))

    def run(self):
        _LOGGER.info(f'Starting osc server at port {self.myport} and client at {self.hisport}')
        dispatcher = Dispatcher()
        dispatcher.map("/startjob", self.start_job)
        dispatcher.map("/haltjob", self.halt_job)
        dispatcher.map("/destroy", self.destroy)

        ip = "127.0.0.1"

        self.server = AsyncIOOSCUDPServer((ip, self.myport), dispatcher, self.loop)
        self.client = SimpleUDPClient(ip, self.hisport)  # Create client
        self.server.serve()
        self.client.send_message("/iamalive", 1)
        self.loop.run_forever()
        _LOGGER.info('Closing osc server')


def processDl_callable_hook(resp, status=dict(), client=None):
    try:
        rv = status['sta']
    except Exception:
        rv = None
    try:
        filename = status['file']
    except Exception:
        filename = None
    try:
        files = status['files']
    except Exception:
        files = []
    if 'status' in resp:
        if resp['status'] == 'finished':
            rv = 0
        elif resp['status'] == 'error':
            rv = 601
        elif resp['status'] == 'downloading':
            rv = -1
    if 'filename' in resp:
        filename = resp['filename']
    if 'tmpfilename' in resp and resp['tmpfilename'] not in files:
        files.append(resp['tmpfilename'])
    retain_keys = ['fragment_index', 'fragment_count', 'speed', 'status']
    status.update(dict(raw={key: resp.get(key) for key in retain_keys}, file=filename, sta=rv, files=files))
    if client:
        client.send_message('/jobprogress', safe_serialize(status))


def youtube_dl_dl(url, opts, rv_err):
    try:
        with youtube_dl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url)
            rv_err['rv'] = 0
            retain_keys = ['requested_downloads']
            rv_err['raw'] = {key: info.get(key) for key in retain_keys}
    except KeyboardInterrupt:
        _LOGGER.warning(f'DL stopped {traceback.format_exc()}')
        rv_err['rv'] = 501
    except Exception:
        _LOGGER.warning(f'DL error {traceback.format_exc()}')
        rv_err['rv'] = 601


def main(myport: int, hisport: int):
    try:
        queue: SimpleQueue = SimpleQueue()
        thread: OSCThread = OSCThread(myport, hisport, queue)
        thread.start()
        val = queue.get()
        _LOGGER.info(f'New dl job {val}')
        main_hk = dict(hk=dict(), exit=dict())
        if val and isinstance(val, tuple) and len(val) == 2:
            client = SimpleUDPClient('127.0.0.1', hisport)  # Create client
            val[1]['progress_hooks'] = [partial(processDl_callable_hook, status=main_hk["hk"], client=client)]
            youtube_dl_dl(*val, main_hk['exit'])
            thread.exit(main_hk['exit'])
    except Exception:
        _LOGGER.error(f'Error in downloading {traceback.format_exc()}')
        thread.exit(dict(rv=900, err=traceback.format_exc()))


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.config.dictConfig(LOGGING)
    _LOGGER.info(f'Starting arguments {sys.argv}')
    if len(sys.argv) == 3:
        try:
            myport = int(sys.argv[1])
            if myport <= 0 or myport > 65535:
                raise Exception(f'Invalid port {myport}')
            hisport = int(sys.argv[2])
            if hisport <= 0 or hisport > 65535:
                raise Exception(f'Invalid port {hisport}')
            main(myport, hisport)
            sys.exit(0)
        except Exception:
            pass
    _LOGGER.error(f'Invalid arguments {sys.argv}')
