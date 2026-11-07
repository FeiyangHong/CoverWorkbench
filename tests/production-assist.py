"""Source-impact, real caption QC, task cancellation, redaction and update rollback."""
from pathlib import Path
from unittest.mock import patch
import argparse,copy,json,subprocess,sys,tempfile,time,zipfile
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'app'))
import core,settings,video_project as video,asset_impact as impact,publish_checks as qc,task_center as tasks,task_resources,project_assets,projects,workspaces,video_links,deployment_tools as deployment,video_edit

def wait(job):
    deadline=time.monotonic()+120
    while tasks.own(job['id'])['status'] in ('queued','running'):
        assert time.monotonic()<deadline;time.sleep(.03)
    return tasks.own(job['id'])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');args=parser.parse_args();ff=settings.executable('ffmpeg',False);probe=settings.executable('ffprobe',False)
    with tempfile.TemporaryDirectory(prefix='cw production tools ') as td:
        root=Path(td)
        for m in [core,settings,tasks,project_assets,projects,workspaces,video_links,deployment]:m.ROOT=root
        tasks.BASE=root/'runtime/studio-tasks';settings.FILE=root/'config/settings.local.json';project_assets.STORE=root/'config/project-assets.local.json';video_links.STORE=root/'config/video-links.local.json';video.BASE=root/'projects/video'
        core.save_json(root/'config/projects.json',[]);core.save_json(settings.FILE,{'ffmpeg':ff,'ffprobe':probe} if ff else {})
        p=projects.create({'title':'Fixture Song','artist':'Artist'});audio=root/'Mix.wav';audio.write_bytes(b'initial audio')
        assets=project_assets.status(p['id']);project_assets.save(p['id'],{'revision':assets['revision'],'assets':{'mix':str(audio)},'storageMode':'reference'})
        baseline=impact.scan_music(p['id']);assert baseline['baselineAt'] is None
        impact.scan_music(p['id'],True,baseline['current']);audio.write_bytes(b'new exported audio content')
        changed=impact.scan_music(p['id']);assert any(c['role']=='mix' for c in changed['changes'])
        doc=video.create({'name':'Check Fixture'});movie=root/'Movie.mp4';movie.write_bytes(b'fake video')
        doc.update(video=str(movie),audio=str(audio),cues=[{'id':'A','start':1,'end':2,'original':'A long sentence that takes time to read'*4,'translation':'译文'},{'id':'B','start':1.7,'end':5,'original':'Second','translation':''}]);doc=video.save(doc['id'],doc)
        original=core.sha(video.folder(doc['id'])/'project.json');issues=qc.structural(doc,4,[])
        assert {'reading','tail','overlap','translation','font'}<={i['code'] for i in issues}
        audio.write_bytes(b'replaced mix again');assert any(c['role']=='audio' for c in impact.scan_video(doc['id'])['changes']);assert core.sha(video.folder(doc['id'])/'project.json')==original
        task_resources.HEAVY.acquire()
        try:
            job=tasks.submit({'kind':'diagnostic'});tasks.JOBS[job['id']]['cancel'].set()
            assert wait(job)['status']=='cancelled'
        finally:task_resources.HEAVY.release()
        result=wait(tasks.submit({'kind':'diagnostic'}));assert result['status']=='completed',result
        report=(Path(result['folder'])/'Diagnostic Report.zip').read_bytes();assert str(root).encode() not in report
        text=json.dumps(result['result'],ensure_ascii=False);assert str(root) not in text and 'Fixture Song' not in text
        # Updating source cannot overwrite config/media, and rollback refuses later edits.
        (root/'app').mkdir();(root/'app/server.py').write_text('old source');private=root/'config/settings.local.json';protected=core.sha(private);package=root/'Update.zip'
        with zipfile.ZipFile(package,'w') as z:
            z.writestr('CoverWorkbench-main/app/server.py','new source');z.writestr('CoverWorkbench-main/LICENSE','MIT');z.writestr('CoverWorkbench-main/config/settings.local.json','unwanted');z.writestr('CoverWorkbench-main/projects/Bad/project.json','unwanted')
        updated=deployment.apply({'path':str(package),'confirm':True});assert (root/'app/server.py').read_text()=='new source' and core.sha(private)==protected and not (root/'projects/Bad').exists()
        deployment.rollback({'name':updated['name'],'confirm':True});assert (root/'app/server.py').read_text()=='old source' and core.sha(private)==protected
        updated=deployment.apply({'path':str(package),'confirm':True});(root/'app/server.py').write_text('manual edit')
        try:deployment.rollback({'name':updated['name'],'confirm':True})
        except ValueError:pass
        else:raise AssertionError('Rollback overwrote newer manual edits')
        if args.installed:
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=c=0x776090:s=640x360:r=25:d=6','-f','lavfi','-i','sine=frequency=300:duration=6','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-y',str(movie)],check=True)
            subprocess.run([ff,'-v','error','-f','lavfi','-i','sine=frequency=440:duration=8','-y',str(audio)],check=True)
            doc.update(styles={'original':{**video.STYLE,'x':10,'size':150},'translation':video.STYLE},cues=[{'id':'A','start':1,'end':4,'original':'This subtitle is deliberately beyond the left edge','translation':'检查字幕'}]);doc=video.save(doc['id'],doc)
            before={p:core.sha(p) for p in [movie,audio]};job=wait(tasks.submit({'kind':'preflight','project':doc['id'],'revision':doc['revision']}));assert job['status']=='completed',job
            assert {'audio-tail','edge'}<={i['code'] for i in job['result']['issues']},job['result']
            assert qc.latest(doc['id'])['stale'] is False
            asset=video_edit.import_media(doc['id'],{'path':str(movie)});proxy=wait(tasks.submit({'kind':'proxy','project':doc['id'],'revision':doc['revision'],'asset':asset['id']}));assert proxy['status']=='completed' and Path(proxy['result']['proxy']).is_file(),proxy
            assert video.load(doc['id'])['cues']==doc['cues'] and core.sha(movie)==before[movie]
            audio.write_bytes(audio.read_bytes()+b'changed');assert qc.latest(doc['id'])['stale'] is True and core.sha(movie)==before[movie]
            print('PASS: real libass edge sampling, mixed-audio truncation checks, and stale-report invalidation')
        assert core.sha(private)==protected
    print('PASS: explicit source baselines/impact, caption issue locations, cancellable compute waits, redacted diagnosis, source-only updates and protected rollback')

if __name__=='__main__':main()
