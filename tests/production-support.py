"""Collected incremental backups, immutable recovery, stable handoffs and music QC."""
from pathlib import Path
from unittest.mock import patch
import argparse,copy,json,math,struct,sys,tempfile,threading,time,wave,zipfile
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'app'))
import core,settings,projects,project_assets,workspaces,project_context,project_packages,project_tasks,project_backup,production_support as support,handoff_watch,audio_qc,video_project,video_links,video_workflow,video_edit,daw,mix_sources,asset_impact,app_identity,separation_progress

def make_audio(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as f:
        f.setparams((2,2,16000,0,'NONE','not compressed'))
        data=b''.join(struct.pack('<hh',int(10000*math.sin(i*2*math.pi*440/16000)) if not 16000<i<28000 else 0,int(8000*math.sin(i*2*math.pi*440/16000)) if not 16000<i<28000 else 0) for i in range(64000));f.writeframes(data)

def info(path):
    with wave.open(str(path),'rb') as f:return dict(duration=f.getnframes()/f.getframerate(),rate=f.getframerate(),frames=f.getnframes(),channels=f.getnchannels(),bits=16)

def wait(j):
    deadline=time.monotonic()+90
    while support.own(j['id'])['status'] in ('queued','running'):
        assert time.monotonic()<deadline;time.sleep(.03)
    d=support.own(j['id']);assert d['status']=='completed',d;return d

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');args=parser.parse_args();ff=settings.executable('ffmpeg',False);probe=settings.executable('ffprobe',False)
    with tempfile.TemporaryDirectory(prefix='production support ') as td:
        home=Path(td);root=home/'Workspace';root.mkdir();backup=home/'Backups'
        for m in [core,settings,projects,project_assets,workspaces,project_context,project_packages,project_tasks,project_backup,support,handoff_watch,video_project,video_links,video_workflow,video_edit,daw,mix_sources,asset_impact]:m.ROOT=root
        project_assets.STORE=root/'config/project-assets.local.json';video_links.STORE=root/'config/video-links.local.json';video_project.BASE=root/'projects/video';project_tasks.BASE=root/'work/Project Packages';support.BASE=root/'runtime/Production Support';support.CONFIG=root/'config/production-support.local.json';settings.FILE=root/'config/settings.local.json';app_identity.PENDING=root/'runtime/Pending Update.json'
        core.save_json(root/'config/projects.json',[]);core.save_json(settings.FILE,{'ffmpeg':ff,'ffprobe':probe} if ff and probe else {})
        with patch.object(project_backup,'cross_disk',return_value=True),patch.object(projects,'media_info',side_effect=info),patch.object(daw,'media_info',side_effect=info),patch.object(video_links,'audio_info',side_effect=lambda p,label:None):
            source=home/'Original.wav';make_audio(source);source_hash=core.sha(source)
            p=projects.create({'title':'测试 Song','artist':'Artist','source':str(source)});ident=p['id'];workspace=workspaces.root(p)
            preset=home/'External Effect.preset';preset.write_bytes(b'synthetic native plugin state')
            song=home/'External Song.song'
            with zipfile.ZipFile(song,'w') as z:z.writestr('song.xml','<Song><Effect url="'+preset.as_uri()+'"/><Audio url="'+source.as_uri()+'"/></Song>')
            selected=project_assets.status(ident);project_assets.save(ident,{'revision':selected['revision'],'assets':{'song':str(song)},'storageMode':'reference'})
            support.configure({'backupDirectory':str(backup),'backupProjects':[ident],'backupEnabled':False})
            # Stable saves are proposals, not implicit edits or new timing offsets.
            svp=Path(p['working']);now=time.time()
            with patch.object(handoff_watch.time,'time',return_value=now):assert not handoff_watch.scan(ident)['changes']
            doc=core.read_json(svp);doc['testRevision']=2;core.save_json(svp,doc)
            with patch.object(handoff_watch.time,'time',return_value=now+1):assert not handoff_watch.scan(ident)['changes']
            with patch.object(handoff_watch.time,'time',return_value=now+5):
                changes=handoff_watch.scan(ident)['changes'];assert len(changes)==1 and changes[0]['role']=='svp'
                handoff_watch.accept(ident,changes[0]);assert not handoff_watch.scan(ident)['changes']
            with patch.object(video_links,'audio_info',side_effect=mix_sources.audio_info):
                asset=project_assets.status(ident);project_assets.save(ident,{'revision':asset['revision'],'assets':{'mix':str(source)},'storageMode':'reference'})
                video=video_project.create({'name':'Associated Video'},directory=workspace/'video');video.update(audio=str(source),audioOffset=1.25,cues=[{'id':'A','start':2,'end':3,'original':'Keep words','translation':'保留文字'}]);video=video_project.save(video['id'],video)
                core.save_json(video_links.STORE,{'version':1,'links':{ident:{'videoId':video['id'],'audioPath':str(source)}}});before=copy.deepcopy(video)
                result=handoff_watch.video_update(ident,{'videoRevision':video['revision'],'draftsSaved':True});after=video_project.load(result['videoId'])
                assert after['cues']==before['cues'] and after['styles']==before['styles'] and after['audioOffset']==before['audioOffset']
            # Generated preview caches are excluded; referenced outside media is collected.
            (workspace/'Cache').mkdir();(workspace/'Cache/Preview.bin').write_bytes(b'rebuildable')
            model_cache=workspace/'analysis/whisper_models/snapshots/model';model_cache.mkdir(parents=True)
            (model_cache/'config.json').write_text('{"cache":true}',encoding='utf8')
            lyric=workspace/'exports/lyrics/Original.lrc';lyric.write_text('[00:01.00]Text',encoding='utf8')
            first=wait(support.submit(ident,{'kind':'backup'}))['result'];assert first['changedFiles']>0
            original_manifest=Path(first['folder'])/'Manifest.json';manifest_hash=core.sha(original_manifest)
            assert not any('whisper_models' in name for name in core.read_json(original_manifest)['files'])
            failure_folder=root/'Failure Task';failure_folder.mkdir()
            failure_job={'id':'failed-fixture','kind':'backup','scope':'music','project':ident,'folder':str(failure_folder),'cancel':threading.Event()}
            # A required missing source used to leak an entire completed working copy.
            real_status=project_assets.status(ident)
            missing=copy.deepcopy(real_status);missing['assets']['mix']={'path':str(home/'Missing.wav')}
            with patch.object(project_assets,'status',return_value=missing):
                try:project_backup.create(failure_job,str(backup))
                except ValueError as error:assert 'Missing.wav' in str(error)
                else:raise AssertionError('Missing input accepted')
            assert not (failure_folder/'Working Copy').exists()
            # Cancellation after copying has the same cleanup guarantee.
            real_copy=project_packages.shutil.copy2
            def cancel_after_copy(source,destination,*a,**kw):
                result=real_copy(source,destination,*a,**kw);failure_job['cancel'].set();return result
            with patch.object(project_packages.shutil,'copy2',side_effect=cancel_after_copy):
                try:project_packages.pack(failure_job)
                except InterruptedError:pass
                else:raise AssertionError('Cancellation was ignored')
            assert not (failure_folder/'Working Copy').exists();failure_job['cancel'].clear()
            with patch.object(project_backup.shutil,'disk_usage',return_value=type('Disk',(),{'free':0})()):
                try:project_backup.create(failure_job,str(backup))
                except ValueError as error:assert '空间' in str(error)
                else:raise AssertionError('Full backup disk accepted')
            assert not (failure_folder/'Working Copy').exists()
            # Failure while publishing must clean only the unfinished destination.
            lyric.write_text('[00:01.00]Changed for failure test',encoding='utf8')
            def broken_publish(source,destination,*a,**kw):
                if any(part.startswith('Preparing Backup ') for part in Path(destination).parts):
                    Path(destination).write_bytes(b'partial');raise OSError('Synthetic interrupted copy')
                return real_copy(source,destination,*a,**kw)
            with patch.object(project_backup.shutil,'copy2',side_effect=broken_publish):
                try:project_backup.create(failure_job,str(backup))
                except OSError:pass
                else:raise AssertionError('Publish failure was ignored')
            assert not (failure_folder/'Working Copy').exists()
            assert not list(Path(first['folder']).parent.glob('Preparing Backup *'))
            assert core.sha(original_manifest)==manifest_hash and core.sha(source)==source_hash
            lyric.write_text('[00:01.00]Text',encoding='utf8')
            # Existing folders are never adopted and deleted as temporary work.
            existing=failure_folder/'Working Copy';existing.mkdir();(existing/'Keep.txt').write_text('keep')
            try:project_packages.pack(failure_job)
            except FileExistsError:pass
            else:raise AssertionError('Existing working copy was overwritten')
            assert (existing/'Keep.txt').read_text()=='keep'
            failure_job['request']={'backupDirectory':str(backup)}
            with patch.object(project_backup,'create',side_effect=ValueError('Missing source')):support.run(failure_job)
            assert failure_job['status']=='failed' and '暂停' in failure_job['stage']
            support.configure({'intervalHours':24})
            assert not support.backup_due(support.config(),ident,0,time.time()+86400*30)
            with patch.object(project_backup,'create',return_value={'synthetic':True}):support.run(failure_job)
            assert failure_job['status']=='completed'
            d=support.config();assert support.backup_due(d,ident,0,time.time())
            d['lastScheduled'][ident]=time.time()
            assert not support.backup_due(d,ident,0,time.time()+601)
            assert support.backup_due(d,ident,0,time.time()+86401)
            second=wait(support.submit(ident,{'kind':'backup'}))['result'];assert second['changedFiles']==0 and second['newBytes']==0,second
            lyric.write_text('[00:01.00]Updated',encoding='utf8')
            third=wait(support.submit(ident,{'kind':'backup'}))['result'];assert third['changedFiles']==1,third
            checked=wait(support.submit(ident,{'kind':'verify-backup','snapshot':third['name']}));assert checked['result']['verified']
            before=core.sha(svp);restored=wait(support.submit(ident,{'kind':'restore-backup','snapshot':second['name'],'name':'Recovered Song'}))['result']
            assert restored['id']!=ident and Path(restored['root'])!=workspace and core.sha(svp)==before and core.sha(source)==source_hash
            assert (Path(restored['root'])/'exports/lyrics/Original.lrc').read_text(encoding='utf8')=='[00:01.00]Text'
            restored_song=Path(project_assets.status(restored['id'])['assets']['song']['path']);assert any(r.suffix=='.preset' and r.is_file() and r.is_relative_to(Path(restored['root'])) for r in project_packages.native_refs(restored_song));assert preset.read_bytes()==b'synthetic native plugin state'
            folder,_=project_backup.project_folder(str(backup),ident);_,snapshot=project_backup.snapshot(folder,third['name']);record=snapshot['files']['exports/lyrics/Original.lrc'];stored=project_backup.stored(folder,record);stored.write_bytes(b'corrupt')
            bad=support.submit(ident,{'kind':'verify-backup','snapshot':third['name']});deadline=time.monotonic()+20
            while support.own(bad['id'])['status'] in ('queued','running') and time.monotonic()<deadline:time.sleep(.02)
            assert support.own(bad['id'])['status']=='failed'
            for malicious in [{'snapshot':'../outside','file':'song.svp'},{'snapshot':'Backup 001','file':'../secret'}]:
                try:project_backup.stored(folder,malicious)
                except ValueError:pass
                else:raise AssertionError('Backup reference escaped its owner')
            # Progress is real, monotonic and carries per-stage estimates only.
            progress=separation_progress.Progress(root,2);progress.begin(0,'DeUX');progress.last=0;progress.callback(50,100,'inference');assert separation_progress.read(root)['stageProgress']==50
            progress.last=0;progress.callback(20,100,'late');assert separation_progress.read(root)['stageProgress']==50;progress.complete();progress.begin(1,'Frazer');assert separation_progress.read(root)['progress']==50
            with patch.object(separation_progress.os,'replace',side_effect=PermissionError('Synthetic unavailable telemetry')):progress.complete()
            assert separation_progress.read(root)['progress']==50,'Telemetry failure must retain the prior readable record'
            # Deferred updates wait for real idleness and refuse changed packages.
            package=home/'Source.zip'
            with zipfile.ZipFile(package,'w') as z:z.writestr('LICENSE','fixture')
            app_identity.defer({'path':str(package),'confirm':True})
            with patch('lifecycle.status',return_value={'canExit':False}):app_identity.apply_pending()
            assert core.read_json(app_identity.PENDING)['status']=='waiting'
            package.write_bytes(package.read_bytes()+b'changed')
            with patch('lifecycle.status',return_value={'canExit':True}):app_identity.apply_pending()
            assert core.read_json(app_identity.PENDING)['status']=='failed'
            # A measurement fixture checks parsing and time cues without external dependencies.
            job={'id':'measurement','project':ident,'folder':str(root/'Measurement'),'request':{'path':str(source)}};Path(job['folder']).mkdir()
            def command(params,label,duration=None):
                if 'loudnorm=' in str(params):return '{"input_i":"-17.4","input_tp":"0.4","input_lra":"4.1"}'
                if 'silencedetect=' in str(params):return 'silence_start: 1\nsilence_end: 1.8\nChannel: 1\nRMS level dB: -20\nChannel: 2\nRMS level dB: -21'
                return 'RMS level dB: -12'
            report=audio_qc.analyze(job,command,lambda *a:None,lambda:None);assert {'silence','true-peak','tail'}<={i['code'] for i in report['issues']};assert core.sha(source)==source_hash
            saved=audio_qc.ignore(ident,{'sha256':report['sha256'],'ignored':[report['issues'][0]['id']]});assert len(saved['ignored'])==1 and not saved['stale']
            if args.installed:
                assert ff and probe,'Configure FFmpeg for installed verification'
                actual=wait(support.submit(ident,{'kind':'audio-check','path':str(source)}));assert actual['result']['measured']['input_i'] is not None and any(r['code']=='silence' for r in actual['result']['issues']),actual
                assert core.sha(source)==source_hash
    print('PASS: stable native handoffs, collected incremental snapshots, no-copy unchanged backup, fresh-identity restore, tamper/traversal refusal, progress and music measurements without source edits')

if __name__=='__main__':main()
