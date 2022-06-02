import abc
import datetime
import json
import asyncio


class JSONAble(abc.ABC):
    @abc.abstractmethod
    def toJSON(self, **kwargs):
        pass


class Fieldable:
    def __str__(self):
        return str(vars(self))

    def f(self, name, typetuple=None):
        try:
            a = getattr(self, name)
        except AttributeError:
            a = None
        return None if typetuple and (a is None or not isinstance(a, typetuple)) else a


class MyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, JSONAble):
            return obj.toJSON(** self.args if hasattr(self, "args") else dict())
        else:
            return super().default(obj)


def get_json_encoder(name, **kwargs):
    return type(name, (MyEncoder,), dict(args=kwargs))


def get_isosplit(s, split):
    if split in s:
        n, s = s.split(split)
    else:
        n = 0
    return n, s


def parse_isoduration(s):
    # Remove prefix
    s = s.split('P')[-1]
    # Step through letter dividers
    days, s = get_isosplit(s, 'D')
    _, s = get_isosplit(s, 'T')
    hours, s = get_isosplit(s, 'H')
    minutes, s = get_isosplit(s, 'M')
    seconds, s = get_isosplit(s, 'S')

    # Convert all to seconds
    dt = datetime.timedelta(days=int(days), hours=int(hours), minutes=int(minutes), seconds=int(seconds))
    return int(dt.total_seconds())


class AbstractMessageProcessor(abc.ABC):
    def __init__(self, db, **kwargs):
        self.db = db

    @abc.abstractmethod
    def interested(self, msg):
        pass

    @abc.abstractmethod
    async def process(self, ws, msg, userid, executor):
        pass


async def asyncio_graceful_shutdown(loop, logger, perform_loop_stop=True):
    """Cleanup tasks tied to the service's shutdown."""
    try:
        logger.debug("Shutdown: Performing graceful stop")
        tasks = [t for t in asyncio.all_tasks() if t is not
                 asyncio.current_task()]

        [task.cancel() for task in tasks]

        logger.debug(f"Shutdown: Cancelling {len(tasks)} outstanding tasks")
        await asyncio.gather(*tasks)
    except Exception:
        import traceback
        logger.error("Shutdown: " + traceback.format_exc())
    finally:
        if perform_loop_stop:
            logger.debug("Shutdown: Flushing metrics")
            loop.stop()
