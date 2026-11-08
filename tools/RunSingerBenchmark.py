"""Optional UNMIXX comparison; never registers unsupported research weights in Studio."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from core import read_json,save_json,sha
import pymss_backend

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);args=parser.parse_args();plan=read_json(Path(args.plan));base=Path(plan['folder']).resolve();report=base/'analysis/Benchmark.json'
    if not base.is_relative_to((ROOT/'projects').resolve()):raise ValueError('Comparison must be owned by the workbench')
    doc=read_json(report);checkout=ROOT/'runtime/pymss/experiments/unmixx';deps=ROOT/'runtime/pymss/experiments/deps';python=pymss_backend.paths()[0]
    for song in doc['songs']:
        if any(r['song']==song['id'] and r['modelId']=='unmixx' for r in doc['results']):continue
        baseline=next(r for r in doc['results'] if r['song']==song['id'] and r['modelId']=='big7');source=base/baseline['outputs']['vocals'];folder=base/'separation'/song['label']/'unmixx/Experimental';folder.mkdir(parents=True,exist_ok=True)
        spec={'parentPid':os.getpid(),'folder':str(folder),'input':str(source),'checkout':str(checkout),'dependencies':str(deps),'device':'cuda'};save_json(folder/'Request.json',spec)
        doc.update(status='running',current=song['label']+' · UNMIXX experimental singers');save_json(report,doc);started=time.monotonic()
        with (folder/'Inference.log').open('wb') as log:child=subprocess.run([str(python),str(ROOT/'integrations/unmixx/worker.py'),str(folder/'Request.json')],stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUTF8':'1'})
        if child.returncode:
            doc['failures'].append({'song':song['id'],'modelId':'unmixx','error':'See '+str((folder/'Inference.log').relative_to(base))});save_json(report,doc);continue
        row={'song':song['id'],'modelId':'unmixx','name':'UNMIXX · Experimental Singers','kind':'singers','engine':'unmixx-experimental','outputs':{k:str(Path(v).relative_to(base)) for k,v in read_json(folder/'Result.json').items()},'metrics':read_json(folder/'Metrics.json')[-1],'wallSeconds':time.monotonic()-started,'audioSeconds':song['duration'],'inputRole':'Big Beta 7 Vocals → mono 24000 Hz','inputAudio':str(source.relative_to(base)),'modelSHA256':sha(checkout/'ckpt/best.ckpt'),'sourceCommit':subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD']).decode().strip(),'limitations':'Two output streams, not fixed singer identities; training-window overlap/permutation alignment is an adapter, not a native PyMSS model.'}
        doc['results'].append(row);save_json(report,doc);print('DONE',song['label'],'UNMIXX',round(row['wallSeconds'],2),flush=True)
    doc.update(status='measured',current='Preparing SV1 audition projects');save_json(report,doc)

if __name__=='__main__':main()
