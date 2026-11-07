"""One cancellable heavy-compute lane shared by renders, proxies and MSST."""
from contextlib import contextmanager
import threading
HEAVY=threading.Semaphore(1)

@contextmanager
def claim(check=lambda:None,waiting=lambda:None):
    check();waiting()
    while not HEAVY.acquire(timeout=.2):check()
    try:check();yield
    finally:HEAVY.release()
