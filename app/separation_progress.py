"""Throttled, atomic worker progress without importing the web application."""
from pathlib import Path
import json,os,threading,time,uuid

class Progress:
    def __init__(self,folder,stages):
        self.file=Path(folder)/'Progress.json';self.stages=stages;self.lock=threading.Lock();self.last=0.;self.stage=0;self.began=time.monotonic();self.fraction=0.;self.device=lambda:{}
    def begin(self,index,name):
        self.stage=index;self.began=time.monotonic();self.fraction=0.;self.write('loading',name,force=True)
    def write(self,phase,message,done=None,total=None,force=False):
        with self.lock:
            now=time.monotonic()
            if not force and now-self.last<.5:return
            self.last=now
            if total and done is not None:self.fraction=max(self.fraction,min(.995,max(0.,float(done)/float(total))))
            elapsed=now-self.began
            eta=elapsed*(1-self.fraction)/self.fraction if .02<self.fraction<1 and elapsed>2 else None
            row={'stageIndex':self.stage,'stageCount':self.stages,'phase':phase,'message':str(message),'stageProgress':round(self.fraction*100,1),'progress':round((self.stage+self.fraction)/self.stages*100,1),'elapsedSeconds':round(elapsed,1),'stageEtaSeconds':round(eta) if eta is not None else None,'updatedAt':time.time()}
            row.update(self.device())
            temp=self.file.with_name('Progress '+uuid.uuid4().hex+'.tmp')
            try:
                temp.write_text(json.dumps(row,ensure_ascii=False),encoding='utf8')
                deadline=time.monotonic()+.8;delay=.02
                while True:
                    try:os.replace(temp,self.file);break
                    except OSError as error:
                        if getattr(error,'winerror',None) not in (5,32,33) or time.monotonic()>=deadline:raise
                        time.sleep(delay);delay=min(.16,delay*2)
            except OSError:
                # Telemetry is best effort; it must never abort expensive inference.
                if not getattr(self,'warned',False):print('Progress update temporarily unavailable; separation continues.',flush=True);self.warned=True
            finally:
                try:temp.unlink(missing_ok=True)
                except OSError:pass
    def callback(self,done,total,message='推理中'):self.write('inference',message,done,total)
    def complete(self):
        self.fraction=1.;self.write('stage-completed','阶段完成',force=True)

def read(folder):
    try:return json.loads((Path(folder)/'Progress.json').read_text(encoding='utf8'))
    except (OSError,ValueError):return None
