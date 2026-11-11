"""Real controller/worker protocol with a synthetic engine, no GPU or private files."""
from pathlib import Path
from unittest.mock import patch
import json,shutil,sys,tempfile,time,wave
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'app'))
from core import read_json,save_json,sha
import settings,pymss_backend as backend,separation_jobs as jobs,project_assets as assets,projects,workspaces,separation_compare

def info(path):
    with wave.open(str(path),'rb') as f:return {'duration':f.getnframes()/f.getframerate(),'rate':f.getframerate(),'frames':f.getnframes(),'channels':1,'bits':16}

def main():
    with tempfile.TemporaryDirectory(prefix='pymss adapter ') as td:
        root=Path(td);install=root/'Source Checkout';models=root/'Shared App Models';install.mkdir();models.mkdir()
        for m in [backend,jobs,assets,projects,workspaces,separation_compare]:m.ROOT=root
        settings.FILE=root/'config/settings.local.json';assets.STORE=root/'config/project-assets.local.json'
        save_json(settings.FILE,{'pymssDirectory':str(install),'pymssPython':sys.executable,'pymssModels':str(models),'separationEngine':'pymss'})
        (install/'pymss').mkdir();(install/'pymss/__init__.py').write_text('''from pathlib import Path
import shutil,json
class MSSeparator:
 def __init__(self,**kw):
  self.kw=kw
  folder=Path(next(iter(kw['store_dirs'].values()))).parent
  folder.mkdir(parents=True,exist_ok=True)
  observed=folder/'Observed Params.json'
  rows=json.loads(observed.read_text()) if observed.exists() else []
  observed.write_text(json.dumps(rows+[{'batch':kw['inference_params']['batch_size'],'tta':kw['use_tta']}]))
 def process_folder(self,source):
  if self.kw['inference_params']['batch_size']==16:raise RuntimeError('CUDA out of memory: synthetic capacity failure')
  for stem,folder in self.kw['store_dirs'].items():
   Path(folder).mkdir(parents=True,exist_ok=True);shutil.copyfile(source,Path(folder)/(Path(source).stem+'_'+stem+'.wav'))
  return [Path(source).name]
 def close(self):pass
''')
        (install/'pymss-2.3.4.dist-info').mkdir();(install/'pymss-2.3.4.dist-info/METADATA').write_text('Name: pymss\nVersion: 2.3.4\n')
        (install/'yaml.py').write_text('import json\nclass SafeLoader:\n @classmethod\n def add_constructor(cls,*a):pass\ndef load(s,**kw):return json.loads(s)\n')
        (install/'torch.py').write_text("__version__='fixture'\nclass cuda:\n @staticmethod\n def is_available():return False\n")
        for relative in ['integrations/pymss/worker.py','integrations/msst/worker.py','app/separation_metrics.py','app/separation_options.py','app/separation_progress.py']:
            dest=root/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(REPO/relative,dest)
        registry={}
        for key,stems in [('big7',['vocals','other']),('deux',['Vocals','Instrumental']),('bs-frazer',['Vocals','Instrumental'])]:
            weight=models/(key+'.ckpt');weight.write_bytes(b'synthetic');config=models/(key+'.yaml');save_json(config,{'training':{'instruments':stems},'audio':{'chunk_size':1024},'inference':{}})
            registry[key]={'model':str(weight),'config':str(config),'stems':stems,'modelType':'bs_roformer'}
        save_json(root/'runtime/pymss/Model Registry.json',registry);save_json(root/'config/projects.json',[])
        source=root/'Original.wav'
        with wave.open(str(source),'wb') as f:f.setparams((1,2,44100,4410,'NONE','not compressed'));f.writeframes(b'\0\0'*4410)
        before=sha(source)
        with patch.object(projects,'media_info',side_effect=info),patch.object(jobs.daw,'media_info',side_effect=info):
            p=projects.create({'source':str(source),'title':'Fixture'});cap=jobs.capabilities();assert cap['engine']=='pymss' and cap['engines']['pymss']['available']
            assert cap['defaults']=={'songModel':'deux','harmonyModel':'bs-frazer','quality':'high','batchSize':4,'tta':False}
            job=jobs.submit(p['id'],{'engine':'pymss','mode':'pipeline','songModel':'deux','harmonyModel':'bs-frazer','quality':'high','batchSize':4,'tta':True})
            deadline=time.monotonic()+15
            while jobs.JOBS[job['id']]['status'] in ('running','queued') and time.monotonic()<deadline:time.sleep(.05)
            result=jobs.public(jobs.JOBS[job['id']]);assert result['status']=='completed',result
            assert set(result['outputs'])=={'vocals','accompaniment','lead','harmony'} and len(result['metrics'])==2
            assert read_json(Path(result['folder'])/'request.json')['overlapFraction']==.875
            assert read_json(Path(result['folder'])/'Checkpoint.json')['engine']=='pymss'
            assert read_json(Path(result['folder'])/'Observed Params.json')==[{'batch':4,'tta':True}]*2
            assert all(m['batchSize']==4 and m['tta'] is True for m in result['metrics'])
            for role,path in result['outputs'].items():assert Path(path).is_file() and assets.status(p['id'])['assets'][role]['path']==path
            assert sha(source)==before
            count=len(list(Path(result['folder']).parent.iterdir()))
            for bad in [{'batchSize':True},{'batchSize':'4'},{'batchSize':3},{'batchSize':8.0},{'batchSize':0},{'tta':'on'},{'tta':1}]:
                try:jobs.submit(p['id'],{'engine':'pymss','mode':'pipeline',**bad})
                except ValueError:pass
                else:raise AssertionError('Invalid inference option accepted: '+str(bad))
            assert len(list(Path(result['folder']).parent.iterdir()))==count,'Invalid options created run directories'
            jobs.update(jobs.JOBS[job['id']],status='cancelled')
            for batch,tta,resume in [(8,True,False),(4,False,False),(4,True,True)]:
                retried=jobs.submit(p['id'],{'engine':'pymss','mode':'pipeline','songModel':'deux','harmonyModel':'bs-frazer','quality':'high','batchSize':batch,'tta':tta,'resumeFrom':job['id']})
                assert bool(retried.get('resumedFrom'))==resume
                deadline=time.monotonic()+15
                while jobs.JOBS[retried['id']]['status'] in ('running','queued') and time.monotonic()<deadline:time.sleep(.05)
                finished=jobs.public(jobs.JOBS[retried['id']]);assert finished['status']=='completed',finished
                assert len(finished['metrics'])==(1 if resume else 2)
            registered={k:v['path'] for k,v in assets.status(p['id'])['assets'].items()}
            failed=jobs.submit(p['id'],{'engine':'pymss','mode':'pipeline','batchSize':16,'tta':False})
            deadline=time.monotonic()+15
            while jobs.JOBS[failed['id']]['status'] in ('running','queued') and time.monotonic()<deadline:time.sleep(.05)
            failure=jobs.public(jobs.JOBS[failed['id']]);assert failure['status']=='failed' and failure['failureCategory']=='capacity'
            assert '显存不足' in failure['message'] and failure['metrics'][0]['status']=='failed'
            assert {k:v['path'] for k,v in assets.status(p['id'])['assets'].items()}==registered,'Capacity failure changed registered stems'
            settings.save({'separationSongModel':'deux','separationHarmonyModel':'bs-frazer','separationQuality':'balanced','separationBatchSize':'8','separationTta':'on'})
            assert jobs.capabilities()['defaults']=={'songModel':'deux','harmonyModel':'bs-frazer','quality':'balanced','batchSize':8,'tta':True}
            for bad in [{'separationSongModel':'bs-frazer'},{'separationBatchSize':'3'},{'separationTta':'true'}]:
                try:settings.save(bad)
                except ValueError:pass
                else:raise AssertionError('Invalid defaults accepted')
        # Installed-App layout: active runtime and modelDir win over bootstrap defaults.
        app=root/'Installed App';data=root/'App Data';app.mkdir();save_json(app/'python-runtime/runtime-envs/active-runtime.json',{'pythonPath':sys.executable,'overlayPath':'overlay'})
        save_json(data/'settings/app.json',{'modelDir':str(models)})
        save_json(settings.FILE,{'pymssDirectory':str(app),'pymssDataRoot':str(data)})
        env=backend.environment();assert env['python']==Path(sys.executable) and env['models']==models and Path(env['overlay']).is_absolute()
        # A second selected cache must not silently reuse old shared-cache entries.
        other=root/'Other Models';other.mkdir();settings.save({'pymssDirectory':str(install),'pymssPython':sys.executable,'pymssModels':str(other)});assert not backend.installation()[2]
    print('PASS: source/App runtime discovery, shared model cache, actual two-stage worker protocol, high-overlap parameters, metrics, protected input and explicit cache switching')

if __name__=='__main__':main()
