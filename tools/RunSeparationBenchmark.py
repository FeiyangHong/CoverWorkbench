"""Run cold-process comparisons on protected copies; no production asset registration."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from core import sha,save_json,read_json
import pymss_backend,separation_jobs,separation_compare

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--legacy-only',action='store_true');args=parser.parse_args();plan=read_json(Path(args.plan));base=Path(plan['folder']).resolve()
    if args.legacy_only:plan['models']=['msst-big7','msst-mel-karaoke']
    if not base.is_relative_to((ROOT/'projects').resolve()):raise ValueError('Benchmark must use a new workbench project folder')
    report=base/'analysis/Benchmark.json'
    doc=read_json(report) if report.is_file() else {'version':1,'title':plan.get('title','Separation Model Comparison'),'songs':[],'results':[],'failures':[],'status':'running','method':'Full songs, one cold subprocess per model/song, batch_size=1, no TTA; no ground-truth quality scores. Inference settings follow each model config. CUDA allocator peaks and whole-device sampled memory are different measures.'}
    if doc.get('profile')!='high875':
        if doc['results']:save_json(base/('analysis/Profile - '+doc.get('profile','fast-default')+'.json'),doc)
        doc.update(profile='high875',results=[],failures=[],method='Full songs; one cold subprocess per model/song; batch 1, 87.5% overlap, no TTA. Model chunk lengths stay model-specific. Whole-process wall time includes Python/model startup; CUDA peaks are allocator measurements; sampled device peaks include other apps. No ground-truth quality score.')
    registry=separation_compare.listing();entry=next((x for x in registry if Path(x['folder'])==base),None)
    if not entry:
        entry={'id':'comparison-'+str(len(registry)+1).zfill(2),'name':doc['title'],'folder':str(base)};save_json(ROOT/'runtime/pymss/Comparisons.json',registry+[entry])
    doc['id']=entry['id'];save_json(report,doc)
    for song in plan['songs']:
        source=Path(song['source']);dest=base/'source'/song['label'];dest.mkdir(parents=True,exist_ok=True);before=sha(source)
        copy=dest/('Original'+source.suffix.lower());wav=dest/'Original.wav'
        if not copy.exists():shutil.copy2(source,copy)
        if sha(copy)!=before or sha(source)!=before:raise ValueError('Source changed: '+song['id'])
        if not wav.exists():subprocess.run([plan['ffmpeg'],'-nostdin','-v','error','-n','-i',str(copy),'-map','0:a:0','-ac','2','-ar','44100','-c:a','pcm_f32le',str(wav)],check=True)
        if not any(s['id']==song['id'] for s in doc['songs']):
            import wave
            probe=json.loads(subprocess.check_output([plan['ffprobe'],'-v','quiet','-show_format','-of','json',str(wav)]))
            doc['songs'].append({'id':song['id'],'label':song['label'],'bpm':song['bpm'],'duration':float(probe['format']['duration']),'original':str(wav.relative_to(base)),'sourceSHA256':before,'sourceName':source.name})
        save_json(report,doc)
        for model_id in plan['models']:
            if any(r['song']==song['id'] and r['modelId']==model_id for r in doc['results']):continue
            legacy=model_id.startswith('msst-');started_wait=time.monotonic();env=pymss_backend.environment()
            if legacy:
                install,python,models=separation_jobs.installation();kind='song' if model_id=='msst-big7' else 'harmony';filename,stems=separation_jobs.PROFILES[kind];model={**models[filename],'name':'MSST · '+filename};spec={'name':model['name'],'kind':kind}
            else:
                while True:
                    _,python,models=pymss_backend.installation()
                    if model_id in models:break
                    if time.monotonic()-started_wait>1800:raise RuntimeError('Model preparation did not complete: '+model_id)
                    time.sleep(2)
                spec=pymss_backend.PRESETS[model_id];kind=spec['kind'];model,stems=pymss_backend.step(model_id,kind,models)
            folder=base/'separation'/song['label']/model_id/'High';folder.mkdir(parents=True,exist_ok=True)
            if kind=='harmony':
                baseline=next(r for r in doc['results'] if r['song']==song['id'] and r['modelId']=='big7');input_file=base/baseline['outputs']['vocals']
            else:input_file=wav
            if legacy:
                owned=folder/'Input/Input.wav';owned.parent.mkdir(exist_ok=True);shutil.copy2(input_file,owned);input_file=owned
            # An immutable single-file input folder also keeps the old adapter safe.
            step={**model,'input':str(input_file),'stems':stems,'folders':{role:str(folder/role) for role in stems.values()}}
            request={'parentPid':os.getpid(),'sourceRoot':str(env['directory'] or ''),'overlay':env.get('overlay'),'result':str(folder/'Result.json'),'inputSHA256':sha(input_file),'modelStamps':[separation_jobs.model_stamp(step)],'steps':[step],'inferenceParams':{'batch_size':1},'overlapFraction':.875}
            if legacy:request.update(installation=str(install),measure=True,inferenceOverrides={'batch_size':1,'num_overlap':8})
            save_json(folder/'Request.json',request);doc.update(status='running',current=song['label']+' · '+spec['name']);save_json(report,doc);print('RUN',doc['current'],flush=True)
            t=time.monotonic()
            with (folder/'Inference.log').open('wb') as log:
                process=subprocess.run([str(python),str(ROOT/('integrations/msst/worker.py' if legacy else 'integrations/pymss/worker.py')),str(folder/'Request.json')],stdout=log,stderr=subprocess.STDOUT,cwd=install if legacy else folder,env={**os.environ,'PYTHONUTF8':'1','PATH':str(Path(plan['ffmpeg']).parent)+os.pathsep+os.environ.get('PATH','')})
            elapsed=time.monotonic()-t
            if process.returncode:
                failure={'song':song['id'],'modelId':model_id,'error':'See '+str((folder/'Inference.log').relative_to(base)),'wallSeconds':elapsed,'returnCode':process.returncode};doc['failures'].append(failure);save_json(report,doc);print('FAILED',failure,flush=True);continue
            outputs=read_json(folder/'Result.json');metric=read_json(folder/'Metrics.json')[-1]
            row={'song':song['id'],'modelId':model_id,'name':spec['name'],'kind':kind,'engine':'msst' if legacy else 'pymss','outputs':{k:str(Path(v).relative_to(base)) for k,v in outputs.items()},'metrics':metric,'wallSeconds':elapsed,'audioSeconds':next(s['duration'] for s in doc['songs'] if s['id']==song['id']),'inputRole':'Original' if kind=='song' else 'Big Beta 7 Vocals','modelSHA256':sha(Path(model['model'])),'modelConfigSHA256':sha(Path(model['config']))}
            prior=[x for x in doc['failures'] if x['song']==song['id'] and x['modelId']==model_id]
            if prior:doc.setdefault('attemptHistory',[]).extend(prior);doc['failures']=[x for x in doc['failures'] if x not in prior]
            doc['results'].append(row);save_json(report,doc);print('DONE',doc['current'],round(elapsed,2),'s',flush=True)
    doc.update(status='measured',current='Preparing audition projects');save_json(report,doc)
    print('MEASUREMENTS COMPLETE',report,flush=True)

if __name__=='__main__':main()
