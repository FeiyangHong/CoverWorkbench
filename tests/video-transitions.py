"""Fixed-cut transitions: schema, absolute frame envelopes and real render parity."""
from pathlib import Path
import argparse
import copy
import importlib.util
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import video_edit as edit
import video_project as project
import video_jobs as jobs
import video_workflow as workflow
import settings
from core import sha

spec = importlib.util.spec_from_file_location('picture_test', ROOT/'tests/video-edit.py')
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--installed', action='store_true'); args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cw transitions ') as temp:
        root = Path(temp); project.BASE = root/'projects'
        red = root/'Red.mp4'; blue = root/'Blue.png'; audio = root/'Mix.wav'
        assets = [{'id': char*32, 'kind': kind, 'duration': 4, 'name': path.name, 'path': str(path)}
                  for char, kind, path in [('a', 'video', red), ('b', 'image', blue)]]
        comp = {'version': 1, 'fps': 25, 'duration': 4, 'assets': assets, 'clips': [
            {'id': 'A', 'asset': 'a'*32, 'start': 0, 'in': 0, 'duration': 2, 'fit': 'cover'},
            {'id': 'B', 'asset': 'b'*32, 'start': 2, 'in': 0, 'duration': 2, 'fit': 'contain',
             'transition': {'type': 'dissolve', 'duration': .8, 'from': 'A'}}]}
        valid = edit.validate(comp); effect = edit.transitions(valid)[0]
        assert (effect['start'], effect['end']) == (40, 60)
        assert [(a,b) for a,b,_,_ in edit.picture_segments(valid,45,55)] == [(45,50),(50,55)]
        assert edit.gaps(valid) == []
        for case in ['gap', 'first', 'long', 'wrongpair', 'nan', 'type']:
            bad = copy.deepcopy(comp); tr = bad['clips'][1]['transition']
            if case == 'gap': bad['clips'][0]['duration'] = 1.5
            if case == 'first': bad['clips'][0]['transition'] = tr
            if case == 'long': tr['duration'] = 3
            if case == 'wrongpair': tr['from'] = 'missing'
            if case == 'nan': tr['duration'] = float('nan')
            if case == 'type': tr['type'] = 'unknown'
            try: edit.validate(bad)
            except ValueError: pass
            else: raise AssertionError(case)
        if args.installed:
            ff = settings.executable('ffmpeg')
            # Green is trimmed away. A transition must hold the last red frame, never reveal green.
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=red:s=320x180:r=25:d=2',
                            '-f','lavfi','-i','color=green:s=320x180:r=25:d=2','-filter_complex',
                            '[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-c:v','libx264','-pix_fmt','yuv420p',str(red)],check=True)
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=blue:s=180x320','-frames:v','1',str(blue)],check=True)
            subprocess.run([ff,'-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4',str(audio)],check=True)
            original = {str(p): sha(p) for p in [red,blue,audio]}
            doc = project.create({'name': 'Transition QA', 'mode': 'edit'})
            doc.update(audio=str(audio), resolution='720', burn=True, composition=comp,
                       cues=[{'id':'L1','start':1.8,'end':2.3,'original':'Fixed captions','translation':'字幕不移动'}])
            doc = project.save(doc['id'],doc)
            doc = workflow.review(doc['id'],{'revision':doc['revision'],'action':'video-clock'})
            fixed = {k:copy.deepcopy(doc[k]) for k in ['cues','styles','audioOffset','subtitleShift','audio']}
            paths = []
            def rgb(path, t, x=638):
                raw = edit.command([ff,'-v','error','-i',path,'-vf',f"select='eq(n,{round(t*25)})',crop=2:2:{x}:358",
                                    '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
                assert len(raw)>=3
                return list(raw[:3])
            for kind in ['dissolve','fade']:
                doc['composition']['clips'][1]['transition']['type'] = kind
                doc = project.save(doc['id'],doc)
                assert all(doc[k]==v for k,v in fixed.items())
                full = support.wait(jobs.submit(doc['id'],{'kind':'export'}))
                # Begin inside the effect: its phase must not restart at zero.
                preview = support.wait(jobs.submit(doc['id'],{'kind':'preview','start':1.8,'end':2.4}))
                fullpath = jobs.media(doc['id'],full['id'],'video.mp4')
                previewpath = jobs.media(doc['id'],preview['id'],'preview.mp4')
                paths.append(fullpath)
                assert abs(full['result']['output']['duration']-4)<.05
                assert abs(preview['result']['output']['duration']-.6)<.05
                for t in [1.84,2,2.16]:
                    a,b = rgb(fullpath,t),rgb(previewpath,round(t-1.8,3))
                    assert max(abs(x-y) for x,y in zip(a,b))<14,(kind,t,a,b)
                    phase=(t-1.6)/.8
                    expected=[253*(1-phase),0,254*phase] if kind=='dissolve' else [253*max(0,1-2*phase),0,254*max(0,2*phase-1)]
                    assert max(abs(x-y) for x,y in zip(a,expected))<12,(kind,t,a,expected)
                middle = rgb(fullpath,2)
                if kind=='dissolve': assert middle[0]>95 and middle[2]>95 and middle[1]<15,middle
                else: assert max(middle)<15,middle
                # Letterbox regions must also transition to black, rather than expose the other layer.
                edge = rgb(fullpath,2,10)
                assert edge[2]<20 and edge[0] < 150,edge
                for t in [2.04,2.12,2.2]: assert rgb(fullpath,t)[1]<20,'Trimmed green material leaked'
                assert all(doc[k]==v for k,v in fixed.items())
            # Picture effects must not alter the rendered music stream.
            music = [edit.command([ff,'-v','error','-i',p,'-vn','-f','s16le','-acodec','pcm_s16le','-']) for p in paths]
            assert music[0]==music[1]
            assert all(sha(p)==h for p,h in original.items())
            print('PASS: real dissolve/fade, held trim edges, letterboxing, partial/full phase and duration parity, identical audio and fixed captions')
    print('PASS: fixed-cut transition schema, adjacent-pair validation and absolute frame intervals')


if __name__ == '__main__': main()
