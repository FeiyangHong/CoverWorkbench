"""Shutdown guards: active requests, both queues, and concurrent submissions."""
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import lifecycle
import native_audio
import workflow
import video_jobs
import separation_jobs


def main():
    assert lifecycle.status()['canExit']
    with lifecycle.operation('Test write'):
        result, code = lifecycle.request_exit(lifecycle.INSTANCE)
        assert code == 409 and result['operations']['Test write'] == 1
        assert not lifecycle.STOPPING
    for jobs, kind in [(native_audio.JOBS, 'auditions'), (workflow.JOBS, 'deliveries'), (video_jobs.JOBS, 'videos'), (separation_jobs.JOBS, 'separations')]:
        for state in ['queued', 'running']:
            jobs['test'] = {'status': state}
            result, code = lifecycle.request_exit(lifecycle.INSTANCE)
            assert code == 409 and result[kind] == 1 and not lifecycle.STOPPING
        jobs.clear()
    result, code = lifecycle.request_exit('old-instance')
    assert code == 409 and not lifecycle.STOPPING
    entered, release = threading.Event(), threading.Event()
    def request():
        with lifecycle.operation('Concurrent write'):
            entered.set(); assert release.wait(5)
    worker = threading.Thread(target=request); worker.start(); assert entered.wait(5)
    assert lifecycle.request_exit(lifecycle.INSTANCE)[1] == 409
    release.set(); worker.join(5); assert not worker.is_alive()
    result, code = lifecycle.request_exit(lifecycle.INSTANCE)
    assert code == 202 and result['state'] == 'stopping'
    for action in [lambda: workflow.enqueue('unused', {}), lambda: native_audio.submit({}), lambda: video_jobs.submit('unused', {}), lambda: separation_jobs.submit('unused', {})]:
        try: action()
        except lifecycle.Stopping: pass
        else: raise AssertionError('A background submission bypassed the shutdown gate')
    assert not lifecycle.status()['canExit']
    print('PASS: active-request/queue protection, stale-instance rejection, concurrent-write exclusion and blocked background submissions after shutdown')


if __name__ == '__main__':
    main()
