"""Selected video audio: immutable clocks, native trims/layers/silence and interval parity."""
from pathlib import Path
from array import array
import argparse
import copy
import math
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import video_audio as audio
import video_project as project
import video_workflow as workflow
import video_edit as edit
import video_jobs as jobs
import settings
from core import sha


def wait(task,success=True):
    deadline=time.monotonic()+180
    while jobs.job(task['id'])['status'] in ('queued','running'):
        assert time.monotonic()<deadline,'render timed out';time.sleep(.12)
    result=jobs.job(task['id']);assert (result['status']=='completed')==success,result
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cw output audio ') as td:
        root=Path(td);project.BASE=root/'projects';video=root/'Red.mp4';video.write_bytes(b'synthetic source')
        doc=project.create({'name':'Video Audio Fixture'});doc.update(video=str(video),audioSource='video',audio=str(root/'Missing Mix.wav'),audioOffset=2.3,gainDb=12,audioMode='normalize',targetLufs=-10,cues=[dict(id='A',start=.2,end=1,original='Keep',translation='保留')])
        doc=project.save(doc['id'],doc);doc=workflow.review(doc['id'],{'revision':doc['revision'],'action':'video-clock'});original=copy.deepcopy(doc)
        sig=workflow.signature(doc);doc['audioOffset']=5;doc['gainDb']=-8;doc=project.save(doc['id'],doc)
        assert doc['cues']==original['cues'] and workflow.signature(doc)==sig and workflow.checks(doc,[])['pendingDelta']==0
        assert audio.available(doc) and not workflow.blockers(doc)
        assets=[dict(id=c*32,path=str(root/f'{c}.mp4'),duration=4,kind='video',hasAudio=True) for c in 'ab']
        comp=dict(version=1,fps=25,duration=4,assets=assets,tracks=[dict(id='V1',name='Lower'),dict(id='V2',name='Upper')],clips=[dict(id='A',asset='a'*32,start=0,duration=4,**{'in':0}),dict(id='B',asset='b'*32,track='V2',start=1,duration=2,**{'in':.4})])
        assert [(r['start'],r['end'],r['in']) for r in audio.segments({'composition':comp})]==[(0,1,0),(1,3,.4),(3,4,3)]
        comp['tracks'][1]['hidden']=True;assert all(r['path']==assets[0]['path'] for r in audio.segments({'composition':comp}))
        if args.installed:
            video.unlink()
            def create(path,color,freq=None):
                cmd=[settings.executable('ffmpeg'),'-v','error','-nostdin','-f','lavfi','-i',f'color=c={color}:s=160x90:r=25:d=4']
                if freq:cmd+=['-f','lavfi','-i',f'sine=frequency={freq}:sample_rate=48000:duration=4','-c:a','aac','-b:a','320k']
                else:cmd+=['-an']
                edit.command(cmd+['-c:v','libx264','-threads','1',path])
            create(video,'red',440);blue=root/'Blue.mp4';silent=root/'Silent.mp4';create(blue,'blue',880);create(silent,'green')
            image=root/'Image.png';edit.command([settings.executable('ffmpeg'),'-v','error','-f','lavfi','-i','color=white:s=160x90','-frames:v','1','-threads','1',image])
            inputs={p:sha(p) for p in (video,blue,silent,image)}
            def samples(result):
                path=jobs.media(result['project'],result['id'],result['files'][0]);data=edit.command([settings.executable('ffmpeg'),'-v','error','-i',path,'-map','0:a:0','-ac','1','-ar','48000','-f','f32le','pipe:1']);values=array('f');values.frombytes(data);return values
            def check(values,time,freq):
                window=values[round((time-.08)*48000):round((time+.08)*48000)];rms=math.sqrt(sum(x*x for x in window)/len(window))
                if freq is None:assert rms<.002,('expected silence',time,rms);return
                score=lambda f:math.hypot(sum(x*math.cos(2*math.pi*f*i/48000) for i,x in enumerate(window)),sum(x*math.sin(2*math.pi*f*i/48000) for i,x in enumerate(window)))
                assert score(freq)>score(880 if freq==440 else 440)*8,(time,freq,rms)
                assert .06<rms<.11,('original level changed by inactive external gain/normalize',rms)
            doc=project.load(doc['id']);doc['burn']=False;doc=project.save(doc['id'],doc);doc=workflow.review(doc['id'],{'revision':doc['revision'],'action':'video-clock'})
            raw=wait(jobs.submit(doc['id'],{'kind':'export'}));check(samples(raw),1,440);assert raw['result']['audioSource']=='video' and raw['result']['audioOffset']==0
            assert str(root/'Missing Mix.wav') not in raw['result']['inputs']
            a=edit.import_media(doc['id'],{'path':str(video)});b=edit.import_media(doc['id'],{'path':str(blue)});n=edit.import_media(doc['id'],{'path':str(silent)});im=edit.import_media(doc['id'],{'path':str(image)})
            track=lambda ident:dict(id=ident,name=ident,hidden=False)
            clip=lambda ident,asset,start,length,track_id,begin=0:dict(id=ident,asset=asset['id'],start=start,duration=length,track=track_id,**{'in':begin},fit='contain',x=0,y=0)
            doc['composition']=dict(version=1,fps=25,duration=4,allowGaps=False,tracks=[track('V1'),track('V2'),track('V3'),track('V4')],assets=[a,b,n,im],clips=[clip('Lower',a,0,4,'V1'),clip('Upper',b,1,2,'V2',.4),clip('Image',im,2,.4,'V3'),clip('NoAudio',n,2.8,.4,'V4')]);doc=project.save(doc['id'],doc)
            full=wait(jobs.submit(doc['id'],{'kind':'export'}));values=samples(full)
            for t,f in [(.5,440),(1.5,880),(2.2,None),(2.5,880),(3,None),(3.5,440)]:check(values,t,f)
            preview=wait(jobs.submit(doc['id'],{'kind':'preview','start':1.2,'end':3.8}));values=samples(preview)
            for t,f in [(.3,880),(1,None),(1.3,880),(1.8,None),(2.3,440)]:check(values,t,f)
            doc['composition']['tracks'][1]['hidden']=True;doc=project.save(doc['id'],doc);hidden=wait(jobs.submit(doc['id'],{'kind':'preview','start':1.1,'end':1.9}));check(samples(hidden),.4,440)
            # Container-delayed audio keeps its initial silence in both browser proxy and render.
            delayed=root/'Delayed.mp4';edit.command([settings.executable('ffmpeg'),'-v','error','-nostdin','-f','lavfi','-i','color=red:s=160x90:r=25:d=4','-itsoffset','1','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=3','-t','4','-c:v','libx264','-threads','1','-c:a','aac','-b:a','320k',delayed])
            doc['composition']=None;doc['video']=str(delayed);doc=project.save(doc['id'],doc);doc=workflow.review(doc['id'],{'revision':doc['revision'],'action':'video-clock'})
            delayed_preview=wait(jobs.submit(doc['id'],{'kind':'preview','start':.2,'end':2}));check(samples(delayed_preview),.2,None);check(samples(delayed_preview),1.3,440)
            import video_preview
            video_preview.CACHE=root/'audio-preview-cache'
            cached=video_preview.prepare(doc['id'],dict(kind='audio',role='video',revision=doc['revision'],expectedPath=str(delayed)))
            url=cached['url'].split('/');proxy=video_preview.media(url[-2],url[-1]);raw=edit.command([settings.executable('ffmpeg'),'-v','error','-i',proxy,'-ac','1','-ar','48000','-f','f32le','pipe:1']);proxy_samples=array('f');proxy_samples.frombytes(raw);check(proxy_samples,.4,None);check(proxy_samples,1.5,440)
            waveform=video_preview.prepare(doc['id'],dict(kind='waveform',role='video',revision=doc['revision'],expectedPath=str(delayed)))
            assert waveform['peaks'][round(.4/waveform['step'])]<.002 and waveform['peaks'][round(1.5/waveform['step'])]>.05
            doc['composition']=None;doc['video']=str(silent);doc=project.save(doc['id'],doc);doc=workflow.review(doc['id'],{'revision':doc['revision'],'action':'video-clock'});failed=wait(jobs.submit(doc['id'],{'kind':'preview','start':0,'end':1}),False);assert '没有音轨' in failed['message'],failed
            assert all(sha(p)==h for p,h in inputs.items());assert not list(Path(full['folder']).glob('Original Audio *.wav'))
            print('PASS: native embedded audio without external mix, preserved level, visible-layer cuts/in-points, silent images/clips, hidden tracks, partial/full tone parity, clear no-audio errors and unchanged sources')
    print('PASS: video/mix source schema, inactive missing mix/offset/gain, preserved caption clocks, source signatures and visible-track segmentation')


if __name__=='__main__':main()
