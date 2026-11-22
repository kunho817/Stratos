import contextlib
import time

_telemetry = None
_task = None


def use(telemetry, task=None):
    from stratos import config
    if not config.TIMING:
        return
    global _telemetry, _task
    _telemetry = telemetry
    _task = task


@contextlib.contextmanager
def timed(name):
    start = time.monotonic()
    try:
        yield
    finally:
        if _telemetry is not None:
            _telemetry.record("step", name=name, task=_task, seconds=round(time.monotonic() - start, 2))
