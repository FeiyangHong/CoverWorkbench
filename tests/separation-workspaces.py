"""Run the real job controller/adapter against an isolated fake MSST Python API."""
from pathlib import Path
from unittest.mock import patch
import json
import shutil
import sys
import tempfile
import time
import wave

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
from core import save_json, read_json, sha
import project_assets as assets
import separation_jobs as jobs
import workspaces
import settings
import projects
import video_project as video
import video_links as links
import video_jobs
import lifecycle
import sv_starter


def audio(path):
    with wave.open(str(path), 'wb') as file:
        file.setparams((1, 2, 44100, 4410, 'NONE', 'not compressed'))
        file.writeframes(b'\0\0' * 4410)


def info(path):
    with wave.open(str(path), 'rb') as file:
        return dict(duration=file.getnframes()/file.getframerate(), rate=file.getframerate(), frames=file.getnframes(), channels=file.getnchannels(), bits=16)


def wait(job):
    until = time.monotonic() + 15
    while time.monotonic() < until:
        with jobs.LOCK:
            result = jobs.public(jobs.JOBS[job['id']])
        if result['status'] not in ['queued', 'running']:
            return result
        time.sleep(.05)
    raise AssertionError('Synthetic worker timed out')


def main():
    with tempfile.TemporaryDirectory(prefix='song workspaces ') as td:
        root = Path(td)
        assets.ROOT = jobs.ROOT = workspaces.ROOT = projects.ROOT = links.ROOT = root
        assets.STORE = root / 'config/project-assets.local.json'
        settings.FILE = root / 'config/settings.local.json'
        links.STORE = root / 'config/video-links.local.json'
        video.BASE = root / 'projects/video'
        install = root / 'MSST local'
        (install / 'inference').mkdir(parents=True)
        (install / 'inference/__init__.py').write_text('')
        (install / 'yaml.py').write_text('import json\nclass SafeLoader:\n @classmethod\n def add_constructor(cls,*args): pass\ndef load(stream,**kwargs): return json.load(stream)\n')
        (install / 'inference/msst_infer.py').write_text('''
from pathlib import Path
import shutil,time
class MSSeparator:
 def __init__(self,**kw):
  self.kw=kw
  text=Path(kw['model_path']).read_text()
  if text=='fail': raise RuntimeError('Synthetic stage failed')
  if text=='wait': time.sleep(2)
 def process_folder(self,folder):
  source=next(Path(folder).glob('*.wav'))
  for stem,dest in self.kw['store_dirs'].items():
   Path(dest).mkdir(parents=True,exist_ok=True)
   shutil.copyfile(source,Path(dest)/(source.stem+'_'+stem+'.wav'))
  return [source.name]
 def del_cache(self): pass
''')
        catalog = []
        weights = {}
        for stage, (model, stems) in jobs.PROFILES.items():
            config = install / 'configs' / (stage + '.yaml')
            save_json(config, {'training': {'instruments': list(stems)}})
            weight = install / 'pretrain/vocal_models' / model
            weight.parent.mkdir(parents=True, exist_ok=True)
            weight.write_text('ok')
            weights[stage] = weight
            catalog.append(dict(name=model, model_type='mel_band_roformer', config_path=str(config.relative_to(install))))
        save_json(install / 'data_backup/msst_model_map.json', {'vocal_models': catalog})
        worker = root / 'integrations/msst/worker.py'
        worker.parent.mkdir(parents=True)
        shutil.copy2(REPO / 'integrations/msst/worker.py', worker)
        save_json(settings.FILE, {'msstDirectory': str(install), 'msstPython': sys.executable})
        assert jobs.capabilities()['models']['song']['available']
        source = root / 'original.wav'
        audio(source)
        before = sha(source)
        save_json(root / 'config/projects.json', [])
        with patch.object(projects, 'media_info', side_effect=info), patch.object(jobs.daw, 'media_info', side_effect=info):
            empty = projects.create({'title': 'Empty Session', 'folderName': 'Empty Session'})
            assert not empty['audio'] and Path(empty['working']).is_file()
            p = projects.create({'source': str(source), 'title': 'Demo Song', 'artist': 'Artist', 'language': 'en'})
            ident = p['id']
            dest = Path(p['pilot'])
            assert dest == root / 'projects/Artist - Demo Song', dest
            assert (dest / 'source/Original.wav').is_file()
            assert not (root / 'projects/songs').exists()
            other = projects.create({'source': str(source), 'title': 'Demo Song', 'artist': 'Artist'})
            assert Path(other['pilot']).name == 'Artist - Demo Song_v2'
            first = jobs.submit(ident, {'mode': 'pipeline'})
            assert not lifecycle.status()['canExit'] and lifecycle.status()['separations'] == 1
            try:
                jobs.submit(other['id'], {'mode': 'song'})
            except ValueError as exc:
                assert '已有' in str(exc)
            else:
                raise AssertionError('Concurrent GPU task accepted')
            complete = wait(first)
            assert complete['status'] == 'completed', complete
            state = assets.status(ident)
            for role in ['vocals', 'accompaniment', 'lead', 'harmony']:
                assert state['assets'][role]['exists']
                assert Path(state['assets'][role]['path']).parent == Path(first['folder']) / role
                assert Path(state['assets'][role]['path']).name == {'vocals': 'Vocals', 'accompaniment': 'Instrumental', 'lead': 'Lead', 'harmony': 'Harmony'}[role] + '.wav'
            # The source-vs-vocals choice changes actual karaoke input and registry semantics.
            prior_vocals = state['assets']['vocals']['path']
            original_karaoke = wait(jobs.submit(ident, {'mode': 'harmony', 'harmonyInput': 'source'}))
            assert original_karaoke['status'] == 'completed', original_karaoke
            assert original_karaoke['inputRole'] == 'source'
            assert assets.status(ident)['assets']['vocals']['path'] == prior_vocals
            original_pipeline = wait(jobs.submit(ident, {'mode': 'pipeline', 'harmonyInput': 'source'}))
            spec = read_json(Path(original_pipeline['folder']) / 'request.json')
            assert original_pipeline['status'] == 'completed' and spec['steps'][1]['input'] == spec['steps'][0]['input']
            for engine, version in [('sv1', 153), ('sv2', 196)]:
                before_svp = assets.status(ident)['assets']['svp']['path']
                starter = sv_starter.create(ident, {'engine': engine, 'roles': ['lead', 'accompaniment'], 'bpm': 130})
                document = read_json(Path(starter['svp']))
                assert document['version'] == version and document['time']['tempo'][0]['bpm'] == 130
                assert document['tracks'][-1]['mainRef']['isInstrumental'] is False
                assert len(document['tracks']) == 3
                for tr in document['tracks'][:-1]:
                    assert tr['mixer']['mute'] and tr['mainGroup']['uuid'] == tr['mainRef']['groupID']
                    assert Path(tr['mainRef']['audio']['filename']).is_relative_to(Path(starter['folder']))
                    assert tr['mainRef']['audio']['duration'] == .1
                assert assets.status(ident)['assets']['svp']['path'] == before_svp
                registered = sv_starter.create(ident, {'engine': engine, 'roles': ['vocals'], 'register': True})
                assert assets.status(ident)['assets']['svp']['path'] == registered['svp']
                assert Path(registered['folder']).name == 'Session 02' and Path(starter['svp']).is_file()
            assert not assets.status(other['id'])['assets']['lead']['exists']
            assert not jobs.history(ident)[0].get('skipped')
            baseline = assets.overrides(ident).copy()
            weights['harmony'].write_text('fail')
            failed = wait(jobs.submit(ident, {'mode': 'pipeline'}))
            assert failed['status'] == 'failed', failed
            assert assets.overrides(ident) == baseline, 'Partial stage-one result was registered'
            weights['harmony'].write_text('ok')
            weights['song'].write_text('wait')
            conflict = jobs.submit(ident, {'mode': 'song'})
            edited = assets.status(ident)
            assets.save(ident, {'revision': edited['revision'], 'storageMode': 'reference', 'assets': {'vocals': str(source)}})
            completed = wait(conflict)
            assert completed['status'] == 'completed' and 'vocals' in completed['skipped'], completed
            assert assets.status(ident)['assets']['vocals']['path'] == str(source)
            cancelled = jobs.submit(ident, {'mode': 'song'})
            prior = assets.overrides(ident).copy()
            jobs.cancel(ident, {'id': cancelled['id']})
            assert wait(cancelled)['status'] == 'cancelled'
            assert assets.overrides(ident) == prior
            assert sha(source) == before
            assert lifecycle.status()['canExit']
            # Existing edited video documents stay byte-for-byte intact; future jobs use the song root.
            doc = video.create({'name': 'Existing Video'})
            original = sha(video.folder(doc['id']) / 'project.json')
            save_json(links.STORE, {'version': 1, 'links': {ident: {'videoId': doc['id']}}})
            assert video.output_folder(doc['id'], True) == dest / 'video/Existing Video'
            assert sha(video.folder(doc['id']) / 'project.json') == original
            assert video.folder(doc['id']) in video.output_locations(doc['id'])
            new = video.create({'name': 'New Video'}, directory=dest / 'video')
            assert video.folder(new['id']) == dest / 'video/New Video'
            assert {d['id'] for d in video.listing()} == {'New Video', 'Existing Video'}
            fake = dest / 'separation/Run 99/job.json'
            save_json(fake, {'id': 'old', 'musicId': ident, 'status': 'running', 'created': 0})
            assert next(j for j in jobs.history(ident) if j['id'] == 'old')['status'] == 'interrupted'
    print('PASS: readable per-song roots, source-first creation, real adapter process, exact two-stage roles, atomic registration, manual-path conflict, cancellation, lifecycle and legacy video preservation')


if __name__ == '__main__':
    main()
