"""Composition validation, original-project preservation and optional real media renders."""
from pathlib import Path
from unittest.mock import patch
import argparse
import copy
import json
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import video_edit as edit
import video_project as project
import video_workflow as workflow
import video_jobs as jobs
import settings
from core import sha,save_json,read_json


def wait(task):
    until=time.monotonic()+180
    while jobs.job(task['id'])['status'] in ['queued','running']:
        assert time.monotonic()<until,'render timed out'
        time.sleep(.15)
    value=jobs.job(task['id']);assert value['status']=='completed',value
    return value


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cw picture edit ') as td:
        root=Path(td);project.BASE=root/'projects'
        source=root/'Source.mp4';source.write_bytes(b'fixture')
        a={'id':'a'*32,'kind':'video','duration':10,'name':'Source.mp4','path':str(source)}
        c={'version':1,'duration':10,'fps':25,'allowGaps':False,'assets':[a],
           'clips':[{'id':'A','asset':a['id'],'start':0,'duration':5,'in':2,'fit':'cover','x':0,'y':0},
                    {'id':'B','asset':a['id'],'start':5,'duration':5,'in':0,'fit':'contain','x':0,'y':0}]}
        assert edit.gaps(edit.validate(c))==[]
        for mutation in ['overlap','outofsource','missingasset','nan']:
            bad=copy.deepcopy(c)
            if mutation=='overlap':bad['clips'][1]['start']=4
            if mutation=='outofsource':bad['clips'][0]['in']=8
            if mutation=='missingasset':bad['clips'][0]['asset']='none'
            if mutation=='nan':bad['clips'][0]['duration']=float('nan')
            try:edit.validate(bad)
            except ValueError:pass
            else:raise AssertionError(mutation)
        doc=project.create({'name':'Original Movie'})
        doc.update(video=str(source),audio=str(source),audioOffset=.4,subtitleShift=.1,cues=[{'id':'L1','start':1,'end':2,'original':'Hello','translation':'你好'}])
        doc=project.save(doc['id'],doc);doc=workflow.review(doc['id'],{'revision':doc['revision'],'action':'video-clock'})
        original=sha(project.folder(doc['id'])/'project.json')
        with patch.object(edit,'inspect',return_value={'kind':'video','duration':10,'width':640,'height':360}),patch.object(edit,'command',return_value=b''):
            clone=edit.edit_copy(doc['id'],{'revision':doc['revision'],'name':'Picture Edit'})
        assert clone['cues']==doc['cues'] and clone['styles']==doc['styles']
        assert (clone['audioOffset'],clone['subtitleShift'])==(.4,.1)
        assert sha(project.folder(doc['id'])/'project.json')==original
        base=copy.deepcopy(clone);clone['composition']['clips'][0]['fit']='cover'
        clone=project.save(clone['id'],clone)
        assert clone['cues']==doc['cues'] and not workflow.blockers(clone)
        assert workflow.signature(clone)!=workflow.signature(base)
        assert edit.import_media(clone['id'],{'path':str(source)})['id']==clone['composition']['assets'][0]['id']
        with patch.object(edit,'inspect',return_value={'kind':'video','duration':10,'width':640,'height':360}),patch.object(edit,'command',return_value=b''):
            another=edit.edit_copy(clone['id'],{'revision':clone['revision'],'name':'Picture Edit Copy'})
        assert len(another['composition']['clips'])==1 and another['composition']['clips'][0]['fit']=='cover'
        assert another['composition']['duration']==clone['composition']['duration']
        assert Path(another['composition']['assets'][0]['path']).parent.is_relative_to(project.folder(another['id']))
        if args.installed:
            ff=settings.executable('ffmpeg');audio=root/'Mix.wav';video=root/'Red.mp4';still=root/'Blue.png'
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=c=red:s=320x180:r=25:d=3','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=c=blue:s=180x320','-frames:v','1',str(still)],check=True)
            subprocess.run([ff,'-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4','-c:a','pcm_s16le',str(audio)],check=True)
            protected={str(p):sha(p) for p in [video,still,audio]}
            fresh=project.create({'name':'Real Edit','mode':'edit'});v=edit.import_media(fresh['id'],{'path':str(video)});im=edit.import_media(fresh['id'],{'path':str(still)})
            assert Path(v['thumbnail']).is_file() and Path(im['thumbnail']).is_file()
            proxied=edit.proxy(fresh['id'],{'asset':v['id']});assert Path(proxied['proxy']).is_file()
            fresh.update(audio=str(audio),resolution='720',burn=True)
            fresh['cues']=[{'id':'A','start':.4,'end':2.5,'original':'Music stays here','translation':'字幕保持原位'}]
            fresh['composition'].update(duration=4,assets=[v,im],clips=[
                {'id':'Red','asset':v['id'],'start':0,'duration':2,'in':.4,'fit':'cover','x':0,'y':0},
                {'id':'Blue','asset':im['id'],'start':2,'duration':2,'in':0,'fit':'contain','x':0,'y':0}])
            fresh=project.save(fresh['id'],fresh);fresh=workflow.review(fresh['id'],{'revision':fresh['revision'],'action':'video-clock'})
            preview=wait(jobs.submit(fresh['id'],{'kind':'preview','start':1,'end':3}))
            exported=wait(jobs.submit(fresh['id'],{'kind':'export'}))
            assert abs(preview['result']['output']['duration']-2)<.1 and abs(exported['result']['output']['duration']-4)<.1
            for task,ts,want in [(preview,.3,'red'),(preview,1.3,'blue'),(exported,.3,'red'),(exported,3.3,'blue')]:
                path=jobs.media(fresh['id'],task['id'],'preview.mp4' if task['kind']=='preview' else 'video.mp4')
                raw=edit.command([ff,'-v','error','-ss',str(ts),'-i',path,'-vf','crop=2:2:638:358','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
                rgb=list(raw[:3]);assert (rgb[0]>rgb[2]+70 if want=='red' else rgb[2]>rgb[0]+70),(want,rgb)
            assert all(sha(p)==h for p,h in protected.items())
            assert sha(project.folder(doc['id'])/'project.json')==original
            # Picture edits never change caption clocks, offsets or style values.
            old=copy.deepcopy(fresh);fresh['composition']['clips'][0]['in']=.8;fresh=project.save(fresh['id'],fresh)
            assert fresh['cues']==old['cues'] and fresh['audioOffset']==old['audioOffset'] and fresh['styles']==old['styles']
            print('PASS: real import/thumbnail/proxy, mixed video/image cuts, interval and full renders, decoded frame colors, durations and original hashes')
    print('PASS: composition validation, frame grid, non-overlap, source bounds, immutable originals and independent music/subtitle timing')


if __name__=='__main__':main()
