"""Per-stage measured wall time, CUDA allocator peaks and sampled device memory."""
from pathlib import Path
import json,os,subprocess,threading,time

class StageMeter:
    def __init__(self,torch,label,source,output):
        self.torch=torch;self.output=Path(output);self.stop=threading.Event();self.samples=[];self.process=None
        self.row={'model':label,'input':str(source),'startedAt':time.time(),'deviceMemoryScope':'whole GPU, sampled every 250 ms; includes other applications'}
    def sync(self):
        if self.torch.cuda.is_available():self.torch.cuda.synchronize()
    def __enter__(self):
        self.sync()
        if self.torch.cuda.is_available():
            self.row['gpu']=self.torch.cuda.get_device_name(0);self.torch.cuda.reset_peak_memory_stats()
        try:
            self.process=subprocess.Popen(['nvidia-smi','--id=0','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits','--loop-ms=250'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            def sample():
                for line in self.process.stdout:
                    try:self.samples.append([time.monotonic(),*[float(x.strip()) for x in line.split(',')]])
                    except ValueError:continue
            self.reader=threading.Thread(target=sample,daemon=True);self.reader.start()
        except OSError:self.row['deviceMemoryUnavailable']=True
        self.start=time.monotonic();return self
    def loaded(self):self.sync();self.inference=time.monotonic();self.row['modelLoadSeconds']=self.inference-self.start
    def __exit__(self,kind,error,trace):
        self.sync();finished=time.monotonic();self.row['totalSeconds']=finished-self.start
        self.row['inferenceAndWriteSeconds']=finished-getattr(self,'inference',self.start);self.row['status']='failed' if kind else 'completed'
        if error:self.row['error']=str(error)
        if self.torch.cuda.is_available():
            self.row['cudaPeakAllocatedMiB']=self.torch.cuda.max_memory_allocated()/1048576
            self.row['cudaPeakReservedMiB']=self.torch.cuda.max_memory_reserved()/1048576
        if self.process:
            self.process.terminate();self.process.wait(timeout=5);self.reader.join(timeout=2);self.process.stdout.close()
        if self.samples:
            self.row.update(deviceMemoryStartMiB=self.samples[0][1],devicePeakMemoryMiB=max(x[1] for x in self.samples),gpuUtilizationPeak=max(x[2] for x in self.samples),deviceSamples=len(self.samples))
        previous=json.loads(self.output.read_text(encoding='utf8')) if self.output.is_file() else []
        temporary=self.output.with_suffix('.tmp');temporary.write_text(json.dumps([*previous,self.row],ensure_ascii=False,indent=2),encoding='utf8');os.replace(temporary,self.output)
