"""Process-local shutdown gate shared by HTTP writes and background submissions."""
from collections import Counter
from contextlib import contextmanager
import threading
import uuid

INSTANCE = uuid.uuid4().hex
LOCK = threading.RLock()
ACTIVE = Counter()
STOPPING = False


class Stopping(ValueError):
    pass


@contextmanager
def operation(label='网页请求'):
    with LOCK:
        if STOPPING:
            raise Stopping('工作台正在退出，请从桌面快捷方式重新启动。')
        ACTIVE[label] += 1
    try:
        yield
    finally:
        with LOCK:
            ACTIVE[label] -= 1
            if not ACTIVE[label]:
                del ACTIVE[label]


def status():
    # Imports here avoid a lifecycle/workflow import cycle.
    import native_audio
    import workflow
    import video_jobs
    with LOCK:
        with native_audio.LOCK:
            auditions = sum(j['status'] in ['queued', 'running'] for j in native_audio.JOBS.values())
        with workflow.GUARD:
            deliveries = sum(j['status'] in ['queued', 'running'] for j in workflow.JOBS.values())
        with video_jobs.LOCK:
            videos = sum(j['status'] in ['queued', 'running'] for j in video_jobs.JOBS.values())
        operations = dict(ACTIVE)
        return {'instance': INSTANCE, 'state': 'stopping' if STOPPING else 'running',
                'canExit': not STOPPING and not operations and not auditions and not deliveries and not videos,
                'auditions': auditions, 'deliveries': deliveries, 'videos': videos, 'operations': operations}


def request_exit(instance):
    global STOPPING
    with LOCK:
        result = status()
        if instance != INSTANCE:
            return {**result, 'error': '后台已重新启动，请刷新退出对话框后重试。'}, 409
        if STOPPING:
            return {**result, 'error': '工作台已经在退出。'}, 409
        if not result['canExit']:
            return {**result, 'error': '还有任务或请求正在处理，请完成后再退出。'}, 409
        STOPPING = True
        return {**result, 'state': 'stopping', 'canExit': False, 'ok': True}, 202
