"""Validate actual concatenated/RMS-matched media and SV1 references on tiny fixtures."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    import numpy as np,soundfile as sf
    with tempfile.TemporaryDirectory(prefix='Audition Build ',dir=ROOT/'work') as td:
        repo=Path(td)
        for source in (ROOT/'app').glob('*.py'):
            target=repo/'app'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
        tool=repo/'tools/BuildSeparationAuditions.py';tool.parent.mkdir();shutil.copy2(ROOT/'tools/BuildSeparationAuditions.py',tool)
        base=repo/'projects/Fixture';(base/'analysis').mkdir(parents=True);(base/'exports/reports').mkdir(parents=True)
        waveform=np.repeat((np.sin(np.arange(4410)/44100*440*2*np.pi)*.1)[:,None],2,axis=1).astype('float32');songs=[];rows=[]
        for song in ['one','two']:
            original=base/(song+'.wav');sf.write(original,waveform,44100,subtype='FLOAT');songs.append({'id':song,'label':song,'duration':.1,'bpm':120,'original':original.name})
            for index,model in enumerate(['big7','deux']):
                outputs={}
                for role in ['vocals','accompaniment']:
                    path=base/(song+'-'+model+'-'+role+'.wav');sf.write(path,waveform*(index+1),44100,subtype='FLOAT');outputs[role]=path.name
                rows.append({'song':song,'modelId':model,'name':model,'engine':'fixture','kind':'song','outputs':outputs,'metrics':{},'wallSeconds':1.,'audioSeconds':.1,'inputRole':'Original','modelSHA256':'fixture'})
        protected={str(base/'one.wav'):hashlib.sha256((base/'one.wav').read_bytes()).hexdigest()}
        (base/'analysis/Protected Sources.json').write_text(json.dumps(protected));(base/'analysis/Benchmark.json').write_text(json.dumps({'songs':songs,'results':rows,'failures':[]}))
        subprocess.run([sys.executable,str(tool),'--folder',str(base)],check=True)
        doc=json.loads((base/'analysis/Benchmark.json').read_text(encoding='utf-8'));svp=json.loads(Path(doc['svp']).read_text(encoding='utf-8'));assert svp['version']==153 and len(svp['tracks'])==5
        assert doc['timeline'][1]['start']==6.1 and doc['verified']['changed']==0
        for track in svp['tracks']:
            path=Path(track['mainRef']['audio']['filename']);assert path.is_relative_to(base);info=sf.info(path);assert info.frames==273420 and info.samplerate==44100
            audio,_=sf.read(path);assert np.max(np.abs(audio[4410:269010]))==0
        for song in ['one','two']:
            selected=[r for r in doc['results'] if r['song']==song]
            first,_=sf.read(base/selected[0]['matched']['vocals']);second,_=sf.read(base/selected[1]['matched']['vocals']);assert np.max(np.abs(first-second))<1e-6 and np.max(np.abs(first))<.709
        assert hashlib.sha256((base/'one.wav').read_bytes()).hexdigest()==protected[str(base/'one.wav')]
        refused=subprocess.run([sys.executable,str(tool),'--folder',str(base)],capture_output=True);assert refused.returncode!=0,'Existing SVPs were overwritten'
    print('PASS: genuine matched PCM audio, shared peak ceiling, silent song gaps, aligned SV1 references, source hashes and refusal to overwrite auditions')

if __name__=='__main__':main()
