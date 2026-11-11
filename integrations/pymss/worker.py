"""Finite, local-only PyMSS separation; outputs use the shared job contract."""
from pathlib import Path
import hashlib,inspect,json,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'app'));sys.path.insert(0,str(ROOT/'integrations/msst'))
from separation_metrics import StageMeter
from separation_options import batch_size,tta as validate_tta
from separation_progress import Progress
from worker import watch_parent,watch_cancel

def run(request):
    selected_batch=batch_size(request.get('inferenceParams',{}).get('batch_size',1));use_tta=validate_tta(request.get('tta',False))
    source_root=Path(request.get('sourceRoot') or '.')
    if (source_root/'pymss/__init__.py').is_file():sys.path.insert(0,str(source_root))
    if request.get('overlay'):sys.path.insert(0,request['overlay'])
    from pymss import MSSeparator
    import torch,yaml
    class Loader(yaml.SafeLoader):pass
    Loader.add_constructor('tag:yaml.org,2002:python/tuple',lambda loader,node:tuple(loader.construct_sequence(node)))
    folder=Path(request['result']).parent;results=dict(request.get('initialResults',{}));progress=Progress(folder,len(request['steps']))
    for index,step in enumerate(request['steps']):
        if index<request.get('completedSteps',0):continue
        progress.begin(index,step.get('name','加载模型'))
        config=yaml.load(Path(step['config']).read_text(encoding='utf8'),Loader=Loader)
        if set(config['training']['instruments'])!=set(step['stems']):raise ValueError('Model stem configuration differs from workflow')
        source=Path(results['vocals']) if step['input']=='@vocals' else Path(step['input'])
        with StageMeter(torch,step.get('name',Path(step['model']).stem),source,folder/'Metrics.json') as meter:
            progress.device=lambda:{'deviceMemoryMiB':meter.samples[-1][1],'gpuUtilization':meter.samples[-1][2]} if meter.samples else {}
            import importlib.metadata
            params={'batch_size':1,**request.get('inferenceParams',{})}
            if request.get('overlapFraction') is not None:
                chunk=int(config['audio']['chunk_size']);params.update(chunk_size=chunk,overlap_size=int(chunk*float(request['overlapFraction'])))
            meter.row.update(pymssVersion=importlib.metadata.version('pymss'),torchVersion=torch.__version__,batchSize=selected_batch,tta=use_tta,modelConfig=config.get('inference',{}),inferenceOverrides=params)
            options=dict(model_type=step['modelType'],model_path=step['model'],config_path=step['config'],device='cuda' if torch.cuda.is_available() else 'cpu',device_ids=[0],use_tta=use_tta,output_format='wav',store_dirs={stem:step['folders'][role] for stem,role in step['stems'].items()},audio_params={'wav_bit_depth':'FLOAT'},inference_params=params)
            signature=inspect.signature(MSSeparator).parameters
            if 'progress_callback' in signature or any(p.kind==inspect.Parameter.VAR_KEYWORD for p in signature.values()):options['progress_callback']=progress.callback
            separator=MSSeparator(**options)
            try:
                meter.loaded();progress.write('inference','分离中',force=True);success=separator.process_folder(str(source))
                if not success:raise RuntimeError('PyMSS did not process the input')
                progress.write('writing','整理并校验输出',force=True)
                for stem,role in step['stems'].items():
                    files=list(Path(step['folders'][role]).glob('*.wav'))
                    if len(files)!=1:raise RuntimeError('Missing or ambiguous stem: '+role)
                    target=files[0].with_name({'vocals':'Vocals','accompaniment':'Instrumental','lead':'Lead','harmony':'Harmony'}[role]+'.wav')
                    if files[0]!=target:files[0].rename(target)
                    results[role]=str(target)
                def digest(value):
                    h=hashlib.sha256()
                    with Path(value).open('rb') as stream:
                        while chunk:=stream.read(1048576):h.update(chunk)
                    return h.hexdigest()
                checkpoint={'engine':'pymss','batchSize':selected_batch,'tta':use_tta,'overlapFraction':request.get('overlapFraction'),'completedSteps':index+1,'inputSHA256':request.get('inputSHA256'),'models':request.get('modelStamps'),'outputs':{k:{'path':v,'sha256':digest(v)} for k,v in results.items()}}
                temp=folder/'Checkpoint.tmp';temp.write_text(json.dumps(checkpoint),encoding='utf8');os.replace(temp,folder/'Checkpoint.json')
                progress.complete()
            finally:separator.close()
    temp=Path(request['result']).with_suffix('.tmp');temp.write_text(json.dumps(results),encoding='utf8');os.replace(temp,request['result'])

if __name__=='__main__':
    spec=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'));watch_parent(spec['parentPid']);watch_cancel(spec.get('cancelFile'));run(spec)
