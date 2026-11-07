"""Synthetic recovery, presets, immutable releases, reversible cleanup and portable native projects."""
from pathlib import Path
import copy,json,struct,sys,tempfile,threading,time,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import core,workspaces,projects,project_assets,daw,video_project as video,video_edit,video_jobs,video_links,video_workflow
import video_recovery as recovery,production_presets as presets,release_versions as releases,project_context,project_tasks as tasks,project_packages as packages,project_disk as disk


def wait(job):
    deadline=time.monotonic()+90
    while tasks.get(job['id'])['status'] in ('queued','running'):
        assert time.monotonic()<deadline;time.sleep(.03)
    return tasks.get(job['id'])


with tempfile.TemporaryDirectory(prefix='cw safety ') as td:
    root=Path(td);modules=[core,workspaces,projects,project_assets,daw,video,video_links,video_workflow,presets,releases,tasks,packages,disk]
    for module in modules:module.ROOT=root
    video.BASE=root/'projects/video';project_assets.STORE=root/'config/project-assets.local.json';video_links.STORE=root/'config/video-links.local.json';presets.STORE=root/'config/production-presets.local.json';tasks.BASE=root/'work/Project Packages';disk.ARCHIVE=root/'work/Recoverable Cleanup';daw.BASE=root/'projects/studio-one';daw.BUILD_INDEX=root/'data/daw-build-index.json'
    songroot=root/'projects/Artist - Song';songroot.mkdir(parents=True);external=root/'External';external.mkdir()
    (external/'Media').mkdir();audio=external/'Media/Backing.wav';audio.write_bytes(b'synthetic audio content');reference=external/'Media/Reference.wav';reference.write_bytes(b'vocal reference')
    svp=external/'Vocal.svp';score={'version':147,'time':{'tempo':[{'position':0,'bpm':120}]},'tracks':[{'name':'Lead','dispOrder':0,'mainRef':{},'mainGroup':{'uuid':'fixture','notes':[{'onset':0,'duration':705600000,'pitch':60,'lyrics':'la'}]},'groups':[]},{'name':'Audio','mainRef':{},'mainGroup':{'notes':[]},'groups':[],'filename':'Media/Reference.wav'}]}
    core.save_json(svp,score)
    state=json.dumps({'projectPath':str(svp).replace('\\','\\\\')}).encode();host=b'VST3'+struct.pack('<I',1)+next(iter(sorted(__import__('asset_storage').SV_IDS)))+struct.pack('<Q',48+len(state))+state+b'List'+struct.pack('<I',1)+struct.pack('<4sQQ',b'Comp',48,len(state))
    song=external/'Mix.song'
    with zipfile.ZipFile(song,'w') as z:z.writestr('Song.xml','<Song url="media:Media/Backing.wav"/>');z.writestr('SV.vstpreset',host);z.writestr('Effect.vstpreset',b'unchanged third-party state')
    p={'id':'fixture-song','title':'Song','artist':'Artist','language':'en','duration':12,'pilot':str(songroot),'working':str(svp),'managedSVP':str(svp),'sv2Working':str(songroot/'working/sv2/project.svp'),'snapshot':str(svp),'selectedVersion':'source.svp','versions':['source.svp'],'audio':{},'files':[],'metrics':{},'waveform':[],'comparison':{},'lyricsRaw':'','subtitleSource':None,'builtAt':'2020-01-01 00:00:00'}
    core.save_json(root/'config/projects.json',[p]);core.save_json(root/'config/workspaces.local.json',{p['id']:str(songroot)});core.save_json(root/'data/projects/fixture-song.json',{'project':p,'parsed':core.parse_svp(svp),'flags':[]});core.save_json(songroot/'analysis/review.json',{'decisions':{},'edits':{},'subtitles':[],'subtitleMode':'none'})
    core.save_json(project_assets.STORE,{'revision':1,'projects':{p['id']:{'svp':str(svp),'song':str(song),'mix':str(audio)}}})
    doc=video.create({'name':'Fixture Video'},directory=songroot/'video');movie=video.folder(doc['id'])/'Jobs/Download 001/Legacy Movie.mp4';movie.parent.mkdir(parents=True);movie.write_bytes(b'video media under a legacy Jobs directory')
    doc.update(video=str(movie),audio=str(audio),audioOffset=5,cues=[{'id':'A','start':6,'end':7,'original':'Keep words','translation':'保留文字'}]);doc=video.save(doc['id'],doc);doc['timing']=video_workflow.timing(doc,'audio');core.save_json(video.folder(doc['id'])/'project.json',doc)
    core.save_json(video_links.STORE,{'version':1,'links':{p['id']:{'videoId':doc['id']}}})
    original=copy.deepcopy(doc);snapshot=video.folder(doc['id'])/'project.json';before=core.sha(snapshot);session='a'*32;draft=recovery.payload(doc);draft['audioOffset']=7;draft['cues'][0]['original']='Recovered words'
    recovery.update(doc['id'],{'session':session,'sequence':2,'baseRevision':doc['revision'],'baseTiming':doc['timing'],'payload':draft})
    assert core.sha(snapshot)==before and recovery.update(doc['id'],{'session':session,'sequence':1,'baseRevision':doc['revision'],'payload':{}})['saved'] is False
    doc['audioOffset']=9;doc=video.save(doc['id'],doc);saved=recovery.listing(doc['id'])['drafts'][0];assert saved['conflict']
    recovered=recovery.recover_copy(doc['id'],{'name':saved['name'],'updated':saved['updated']});assert recovered['cues'][0]['start']==8
    recovered=video.save(recovered['id'],recovered);assert recovered['cues'][0]['start']==8 and video.load(doc['id'])['cues'][0]['start']==10
    recovery.update(doc['id'],{'session':session,'sequence':3,'baseRevision':doc['revision'],'action':'dismiss','payload':{}});assert not recovery.listing(doc['id'])['drafts']
    profile=presets.builtins()[0];presets.save({'name':'My Preset','settings':profile['settings']});assert presets.listing()[-1]['name']=='My Preset'
    try:presets.save({'name':'Unsafe','settings':{'audioOffset':8}})
    except ValueError:pass
    else:raise AssertionError('Preset moved audio')
    versions=releases.register('music',p['id'],{'kind':'mix','stage':'final','label':'My Final','path':str(audio),'revision':0});entry=versions['entries'][0];audio.write_bytes(b'updated original mix')
    assert Path(entry['path']).read_bytes()==b'synthetic audio content' and releases.provenance(doc)['unmarked']
    doc['audio']=entry['path'];doc=video.save(doc['id'],doc);assert releases.provenance(doc)['mixVersion']==entry['id']
    versions=releases.stage('music',p['id'],{'entry':entry['id'],'stage':'published','revision':versions['revision']});assert versions['entries'][0]['stage']=='published'
    fingerprints={f:core.sha(f) for f in [svp,song,audio,reference,snapshot,movie]}
    job=wait(tasks.submit('music',p['id'],{'action':'pack'}));assert job['status']=='completed',job
    package=Path(job['result']['path']);assert all(core.sha(f)==h for f,h in fingerprints.items())
    with zipfile.ZipFile(package) as z:
        manifest=json.loads(z.read('Manifest.json'));assert any('Legacy Movie.mp4' in n for n in manifest['files']);assert not any('/Cache/' in n for n in manifest['files'])
    imported=wait(tasks.submit('music','new',{'action':'import','path':str(package),'name':'Artist - Song'}));assert imported['status']=='completed',imported
    restored=imported['result'];dest=Path(restored['root']);assert dest.name=='Artist - Song_v2' and restored['id']!=p['id']
    assets=project_assets.status(restored['id'])['assets'];assert all(not a['path'] or Path(a['path']).is_relative_to(dest) for a in assets.values())
    linked=core.read_json(video_links.STORE)['links'][restored['id']]['videoId'];newdoc=video.load(linked);assert newdoc['cues']==doc['cues'] and newdoc['styles']==doc['styles'] and newdoc['audioOffset']==9 and Path(newdoc['video']).is_file()
    assert list(__import__('asset_storage').sv_references(core.read_json(assets['svp']['path']),Path(assets['svp']['path']).parent))[0].is_file()
    with zipfile.ZipFile(assets['song']['path']) as z:
        assert z.read('Effect.vstpreset')==b'unchanged third-party state'
        for tag,payload in daw.chunks(z.read('SV.vstpreset')):
            if tag==b'Comp':assert Path(json.loads(payload)['projectPath'].replace('\\\\','\\')).is_file()
    assert not releases.listing('music',restored['id'])['entries'][0]['changed']
    bad=root/'Malicious.zip';escape=b'bad'
    with zipfile.ZipFile(bad,'w') as z:
        z.writestr('Manifest.json',json.dumps({'schema':1,'files':{'../escape.txt':{'bytes':3,'sha256':__import__('hashlib').sha256(escape).hexdigest()}}}));z.writestr('Project/../escape.txt',escape)
    failed=wait(tasks.submit('music','new',{'action':'import','path':str(bad)}));assert failed['status']=='failed' and not (root/'escape.txt').exists()
    cache=video.folder(doc['id'])/'Cache/Filmstrips';cache.mkdir(parents=True);(cache/'Frames.jpg').write_bytes(b'cache data');cached_hash=core.sha(cache/'Frames.jpg')
    preview=video.folder(doc['id'])/'Jobs/Preview 001';core.save_json(preview/'job.json',{'id':'c'*32,'project':doc['id'],'kind':'preview','status':'completed','created':1,'version':1,'folder':str(preview)});(preview/'preview.mp4').write_bytes(b'generated preview')
    # A stale/corrupt native registration must not break another cache scan.
    broken=root/'Broken.song';broken.write_bytes(b'not a ZIP project')
    registration=core.read_json(project_assets.STORE);registration['projects'][p['id']]['song']=str(broken);core.save_json(project_assets.STORE,registration)
    plan=disk.scan('music',p['id']);selected=[e['id'] for e in plan['candidates'] if e['path']==str(cache)]
    assert selected and not any(e['path']==str(movie.parent) for e in plan['candidates'])
    archived=disk.archive('music',p['id'],{'token':plan['token'],'entries':selected});assert not cache.exists() and movie.exists() and Path(entry['path']).exists()
    info=disk.scan('music',p['id'])['archives'][-1];disk.manage('music',p['id'],{'action':'restore','name':info['name'],'created':info['created']});assert core.sha(cache/'Frames.jpg')==cached_hash
    plan=disk.scan('music',p['id']);archived=disk.archive('music',p['id'],{'token':plan['token'],'entries':[e['id'] for e in plan['candidates'] if e['path']==str(cache)]});info=disk.scan('music',p['id'])['archives'][-1]
    disk.manage('music',p['id'],{'action':'purge','name':info['name'],'created':info['created'],'confirm':True});assert movie.exists() and Path(entry['path']).exists()
    print('PASS: durable/conflicting drafts and exactly-once offset recovery, setting-only presets, immutable releases, collected native/package dependencies, moved/renamed import, hostile archive rejection, protected media and reversible cache cleanup')
