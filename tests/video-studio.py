"""Synthetic video documents, bilingual timing, source protection and real optional FFmpeg renders."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import video_project as project
import video_jobs as jobs
import lifecycle
import video_workflow as workflow
import settings
from core import sha, read_json


def wait(j):
    until=time.monotonic()+90
    while jobs.job(j['id'])['status'] in ['queued','running']:
        assert time.monotonic()<until,'Job timeout'
        assert any(row['id']==j['id'] for row in jobs.history(j['project']))
        time.sleep(.1)
    result=jobs.job(j['id'])
    assert result['status']=='completed',result
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cw video ') as tmp:
        base=Path(tmp);project.BASE=base/'projects'
        doc=project.create({'name':'My Cover Video'})
        assert doc['id']=='My Cover Video'
        assert project.create({'name':'My Cover Video'})['id']=='My Cover Video_v2'
        for name in ['../escape','CON','bad:name','trailing.','trailing ']:
            try:project.create({'name':name})
            except ValueError:pass
            else:raise AssertionError('Unsafe project name accepted')
        original=base/'original.lrc';translation=base/'translation.srt'
        original.write_text('[offset:100]\n[00:01.000]Hello\n[00:03.000]World\n[00:04.000]\n',encoding='utf-8')
        translation.write_text('1\n00:00:01,500 --> 00:00:03,500\nTest translation\n',encoding='utf-8')
        before={str(p):sha(p) for p in [original,translation]}
        doc=project.import_captions(doc['id'],{'original':str(original),'translation':str(translation),'clock':'video'})
        assert doc['cues'][0]['start']==1.1
        assert any(r['original']=='Hello' and not r['translation'] for r in doc['cues'])
        assert any(r['original']=='World' and r['translation']=='Test translation' for r in doc['cues'])
        doc['cues'][0]['original']=r'{\p1} literal text'
        subdir=base/'subs';subdir.mkdir();project.write_subtitles(doc,subdir,10)
        text=(subdir/'captions.ass').read_text(encoding='utf-8-sig')
        assert '｛＼p1｝ literal text' in text and r'{\p1}' not in text
        doc=project.save(doc['id'],doc)
        old={**doc,'revision':doc['revision']-1}
        try:project.save(doc['id'],old)
        except ValueError:pass
        else:raise AssertionError('Stale revision overwrote a document')
        svp=base/'synthetic.svp';svp.write_text(json.dumps({'time':{'tempo':[{'position':0,'bpm':120}]},'tracks':[{'name':'Lead','mainGroup':{'notes':[{'onset':0,'duration':705600000,'pitch':60,'lyrics':'Hello'},{'onset':705600000,'duration':705600000,'pitch':62,'lyrics':'world'}]}}]}))
        sv_hash=sha(svp)
        anchors=project.sv_anchors({'path':str(svp),'track':0,'cues':[{'id':'A','original':'Hello world'},{'id':'B','original':'Missing'}],'offset':2})
        assert anchors['rows'][0]['start']==2 and anchors['rows'][0]['end']==3
        assert not anchors['rows'][1]['matched'] and sha(svp)==sv_hash
        assert all(sha(p)==h for p,h in before.items())
        # Queue protection and cancellation include the actual owned child process.
        old_render=jobs.render
        old_executable=settings.executable
        settings.executable=lambda name,required=True:sys.executable
        def sleeping(j):jobs.command(j,[sys.executable,'-c','import time;time.sleep(30)'],stage='cancel-test')
        jobs.render=sleeping
        media=base/'input.wav';media.write_bytes(b'synthetic placeholder')
        doc.update(video=str(media),audio=str(media));doc=project.save(doc['id'],doc)
        doc=workflow.review(doc['id'],{'revision':doc['revision'],'action':'video-clock'})
        task=jobs.submit(doc['id'],{'kind':'export'})
        assert lifecycle.status()['videos']==1 and not lifecycle.status()['canExit']
        until=time.monotonic()+5
        while 'process' not in jobs.JOBS[task['id']]:
            assert time.monotonic()<until;time.sleep(.02)
        child=jobs.JOBS[task['id']]['process'];jobs.cancel(task['id'])
        until=time.monotonic()+10
        while jobs.job(task['id'])['status'] in ['queued','running']:
            assert time.monotonic()<until;time.sleep(.05)
        assert jobs.job(task['id'])['status']=='cancelled' and child.poll() is not None
        jobs.render=old_render
        settings.executable=old_executable
        if args.installed:
            ff=settings.executable('ffmpeg')
            video=base/'source.mp4';audio=base/'cover.wav'
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=c=0x393451:s=640x360:r=25:d=6','-f','lavfi','-i','sine=frequency=300:sample_rate=48000:duration=6','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(video)],check=True)
            subprocess.run([ff,'-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=6','-c:a','pcm_s24le',str(audio)],check=True)
            original_hashes={str(p):sha(p) for p in [video,audio]}
            doc.update(video=str(video),audio=str(audio),audioOffset=.5,cues=[dict(id='A',start=1,end=5,original='Synthetic subtitle',translation='Test translation')],audioMode='normalize',targetLufs=-16)
            doc=project.save(doc['id'],doc)
            doc=workflow.review(doc['id'],{'revision':doc['revision'],'action':'video-clock'})
            preview=wait(jobs.submit(doc['id'],{'kind':'preview','start':1,'end':3}))
            assert Path(preview['folder']).name=='Preview 001'
            assert jobs.media(doc['id'],preview['id'],'preview.mp4').name=='My Cover Video - Preview 001.mp4'
            assert preview['result']['sourceUnchanged'] and abs(preview['result']['output']['duration']-2)<.1
            assert workflow.checks(doc,[preview])['previewReady']
            exported=wait(jobs.submit(doc['id'],{'kind':'export'}))
            assert Path(exported['folder']).name=='Export 002'  # Cancelled version 001 remains reserved.
            assert jobs.media(doc['id'],exported['id'],'video.mp4').name=='My Cover Video - v002.mp4'
            assert exported['result']['loudness']['input_tp']<0
            doc.update(audioMode='gain',audioOffset=4)
            doc=project.save(doc['id'],doc)
            silent=wait(jobs.submit(doc['id'],{'kind':'preview','start':0,'end':1}))
            assert silent['result']['loudness']['input_i'] is None
            assert jobs.media(doc['id'],exported['id'],'video.mp4').is_file()
            assert all(sha(p)==h for p,h in original_hashes.items())
            try:jobs.media(doc['id'],exported['id'],'../snapshot.json')
            except ValueError:pass
            else:raise AssertionError('Traversal accepted')
            print('PASS: real two-pass FFmpeg preview/export, decode, duration, loudness and original hashes')
        assert lifecycle.status()['canExit']
    jobs.POOL.shutdown(wait=True)
    print('PASS: private versions, bilingual interval joins, LRC offsets, ASS text safety, stale revisions, SV anchors, cancellation and shutdown guards')


if __name__=='__main__':main()
