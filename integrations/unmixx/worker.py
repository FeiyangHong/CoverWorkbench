"""Optional research adapter: unchanged upstream network/weights, inference-only imports."""
from pathlib import Path
import json,os,sys,types,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'app'));sys.path.insert(0,str(ROOT/'integrations/msst'))
from worker import watch_parent,watch_cancel
from separation_metrics import StageMeter

def load_network(checkout,deps):
    # Avoid eager training/visualization imports in package __init__ files. All
    # network layers and Asteroid's pad_x_to_y execute their upstream source.
    sys.path.insert(0,str(deps))
    for name,path in [('look2hear',checkout/'look2hear'),('look2hear.models',checkout/'look2hear/models'),('look2hear.models.layers',checkout/'look2hear/models/layers'),('asteroid',deps/'asteroid'),('asteroid.utils',deps/'asteroid/utils')]:
        package=types.ModuleType(name);package.__path__=[str(path)];sys.modules[name]=package
    from look2hear.models.unmixx_model import UNMIXX
    import torch,yaml
    config=yaml.safe_load((checkout/'ckpt/conf.yml').read_text(encoding='utf8'))
    model=UNMIXX(sample_rate=int(config['datamodule']['data_config']['sample_rate']),**config['audionet']['audionet_config'])
    state=torch.load(checkout/'ckpt/best.ckpt',map_location='cpu',weights_only=True);state=state.get('state_dict',state)
    state={k.removeprefix('audio_model.'):v for k,v in state.items()};model.load_state_dict(state,strict=True)
    return model,config

def run(spec):
    import torch,numpy as np,soundfile as sf
    from scipy.signal import resample_poly
    from math import gcd
    folder=Path(spec['folder']);folder.mkdir(parents=True,exist_ok=True);checkout=Path(spec['checkout']);deps=Path(spec['dependencies']);device=spec.get('device','cuda')
    if spec.get('probe'):
        torch.set_num_threads(2);model,config=load_network(checkout,deps)
        with torch.inference_mode():result=model(torch.zeros(1,1,24000),istest=True)[0]
        if tuple(result.shape)!=(1,2,24000):raise ValueError('Unexpected UNMIXX waveform shape: '+str(result.shape))
        if not torch.isfinite(result).all():raise ValueError('UNMIXX probe produced non-finite output')
        print('PASS: strict checkpoint and unmodified upstream waveform forward',result.shape);return
    source=Path(spec['input']);raw,rate=sf.read(source,dtype='float32',always_2d=True);mono=raw.mean(axis=1);g=gcd(rate,24000);mono=resample_poly(mono,24000//g,rate//g)
    with StageMeter(torch,'UNMIXX · experimental singers',source,folder/'Metrics.json') as meter:
        model,config=load_network(checkout,deps);model.to(device).eval();meter.loaded()
        size=int(config['datamodule']['data_config']['segment_seconds']*24000);hop=size//8
        meter.row.update(inferenceMode='Unmodified upstream network, training-length mono 24000 Hz windows; 87.5% overlap with waveform-correlation permutation alignment. Output identities are not guaranteed.',torchVersion=torch.__version__,overlapFraction=.875,chunkSamples=size,batchSize=1,tta=False)
        accumulated=np.zeros((2,len(mono)+size),dtype='float32');weights=np.zeros(len(mono)+size,dtype='float32');window=np.maximum(np.hanning(size).astype('float32'),.001);swaps=0;uncertain=[]
        def correlation(a,b):
            denom=float(np.linalg.norm(a)*np.linalg.norm(b));return float(np.sum(a*b)/denom) if denom>1e-9 else 0.
        with torch.inference_mode():
            for start in range(0,len(mono),hop):
                chunk=mono[start:start+size];chunk=np.pad(chunk,(0,size-len(chunk)))
                current=model(torch.from_numpy(chunk)[None,None].to(device),istest=True)[0][0].cpu().numpy()
                overlap=min(size-hop,len(mono)-start)
                if start and overlap>0:
                    prior=accumulated[:,start:start+overlap]/np.maximum(weights[start:start+overlap],1e-9)
                    straight=correlation(prior[0],current[0,:overlap])+correlation(prior[1],current[1,:overlap]);flipped=correlation(prior[0],current[1,:overlap])+correlation(prior[1],current[0,:overlap])
                    if abs(straight-flipped)<.05:uncertain.append(round(start/24000,3))
                    if flipped>straight+.01:current=current[::-1];swaps+=1
                accumulated[:,start:start+size]+=current*window;weights[start:start+size]+=window
                if start%(hop*20)==0:print('UNMIXX',round(start/24000,1),'/',round(len(mono)/24000,1),'s',flush=True)
        outputs=accumulated[:,:len(mono)]/np.maximum(weights[:len(mono)],1e-9);meter.row.update(permutationSwaps=swaps,uncertainBoundaries=uncertain)
        if outputs.shape!=(2,len(mono)) or not np.isfinite(outputs).all():raise ValueError('Invalid UNMIXX output')
        result={};g=gcd(24000,44100)
        for index,label in enumerate(['singer1','singer2']):
            audio=resample_poly(outputs[index],44100//g,24000//g);audio=audio[:len(raw)]
            if len(audio)<len(raw):audio=np.pad(audio,(0,len(raw)-len(audio)))
            target=folder/(label+'.wav');sf.write(target,np.repeat(audio[:,None],2,axis=1),44100,subtype='FLOAT');result[label]=str(target)
    (folder/'Result.json').write_text(json.dumps(result),encoding='utf8')

if __name__=='__main__':
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'));watch_parent(request.get('parentPid',os.getppid()));watch_cancel(request.get('cancelFile'));run(request)
