"""Guard the native close callback against GUI-thread script deadlocks."""
from pathlib import Path
import sys,threading,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from desktop_main import Bridge


class Window:
    def __init__(self,ready=True):
        self.ready=ready;self.entered=threading.Event();self.release=threading.Event();self.destroyed=threading.Event();self.threads=[]
    def evaluate_js(self,script):
        self.threads.append(threading.get_ident());self.entered.set()
        assert self.release.wait(2),'Test script was never released'
        return self.ready
    def destroy(self):self.destroyed.set()


def main():
    bridge=Bridge('http://127.0.0.1:1','fixture',False);window=Window();bridge._window=window
    started=time.monotonic();caller=threading.get_ident()
    assert bridge.closing() is False
    assert time.monotonic()-started<.5,'Close callback waited for the renderer'
    assert window.entered.wait(1) and len(window.threads)==1 and caller not in window.threads
    # Repeated X / Alt+F4 must not launch more blocked renderer requests.
    for _ in range(20):assert bridge.closing() is False
    assert len(window.threads)==1 and not window.destroyed.is_set()
    window.release.set()
    deadline=time.monotonic()+1
    while bridge._close_pending.locked() and time.monotonic()<deadline:time.sleep(.005)
    assert not bridge._close_pending.locked() and not bridge._allow_close
    assert bridge.close_window() is True and window.destroyed.wait(1)
    assert bridge.closing() is True
    # Closing a document that never loaded still disposes its own window.
    bridge=Bridge('http://127.0.0.1:1','fixture',False);window=Window(False);bridge._window=window;window.release.set()
    assert bridge.closing() is False and window.destroyed.wait(1)
    assert bridge.closing() is True
    print('PASS: native close returns immediately, renderer work stays off GUI thread, repeated close is bounded, confirmed/unloaded close completes')


if __name__=='__main__':main()
