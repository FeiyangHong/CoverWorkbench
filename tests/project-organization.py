"""Synthetic legacy migration: original archive, native links, captions and readable lyrics."""
from pathlib import Path
import copy,json,sys,tempfile,struct,zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import core,organize_projects as organize,workspaces,lyric_files,video_project,daw,project_assets,project_library

with tempfile.TemporaryDirectory(prefix='cw organize ') as td:
    root=Path(td);modules=[core,organize,workspaces,lyric_files,video_project,daw,project_assets,project_library]
    for module in modules:module.ROOT=root
    video_project.BASE=root/'projects/video';daw.BASE=root/'projects/studio-one';daw.BUILD_INDEX=root/'data/daw-build-index.json';project_assets.STORE=root/'config/project-assets.local.json';project_library.STORE=root/'config/project-library.local.json'
    songroot=root/'projects/Artist - 歌';old=daw.BASE/'Legacy';old.mkdir(parents=True);songroot.mkdir(parents=True)
    marker=songroot/'analysis/cache/empty-marker.json';marker.parent.mkdir(parents=True);marker.write_bytes(b'')
    p={'id':'song-fixture','title':'歌','artist':'Artist','pilot':str(songroot),'builtAt':'2020-01-01 00:00:00'}
    core.save_json(root/'config/projects.json',[p]);core.save_json(root/'config/workspaces.local.json',{p['id']:str(songroot)});core.save_json(root/'data/projects/song-fixture.json',{'project':p})
    core.save_json(old/'SV/project.svp',{'renderConfig':{'destination':str(old/'Mixdown')},'tracks':[{'lyrics':'Keep words'}]});(old/'Media').mkdir();(old/'Media/Backing.wav').write_bytes(b'unchanged audio')
    with (old/'SV/project.svp').open('ab') as stream:stream.write(b'\x00')
    payload=json.dumps({'projectPath':str(old/'SV/project.svp').replace('\\','\\\\')}).encode();host=b'VST3'+struct.pack('<I',1)+next(iter(sorted(__import__('asset_storage').SV_IDS)))+struct.pack('<Q',48+len(payload))+payload+b'List'+struct.pack('<I',1)+struct.pack('<4sQQ',b'Comp',48,len(payload))
    song=old/'Legacy.song'
    with zipfile.ZipFile(song,'w') as z:z.writestr('Song.xml','<Song url="'+(old/'Media/Backing.wav').as_uri()+'"/>');z.writestr('Host.vstpreset',host);z.writestr('OtherPlugin.vstpreset',b'commercial plugin unchanged')
    core.save_json(old/'build.json',{'name':'Legacy','song':str(song),'svp':str(old/'SV/project.svp'),'sourceSVP':str(root/'Original.svp'),'createdAt':1})
    core.save_json(project_assets.STORE,{'projects':{p['id']:{'song':str(song)}}})
    oldvideo=video_project.BASE/'My Video';doc={'id':'My Video','name':'My Video','updated':'2020-01-01T00:00:00','revision':7,'audioOffset':5.145,'subtitleShift':.12,'styles':{'font':'Keep Font'},'cues':[{'start':1,'end':2,'original':'Keep words','translation':'保留'}],'video':str(oldvideo/'Media/Movie.mp4')};core.save_json(oldvideo/'project.json',doc);(oldvideo/'Media').mkdir();(oldvideo/'Media/Movie.mp4').write_bytes(b'original video')
    core.save_json(root/'config/video-links.local.json',{'links':{p['id']:{'videoId':'My Video'}}})
    directory=songroot/'working/lyrics';directory.mkdir(parents=True);source=directory/'song-random_source.json';line=directory/'song-random_lines.json';original='[00:01.00]Hello\n[00:02.00]World\n';translation='[00:01.00]你好\n[00:02.00]世界\n'
    core.save_json(source,{'source':'fixture','original':original,'translation':translation,'romaji':''})
    export=songroot/'exports/lyrics/hash_original.lrc';export.parent.mkdir(parents=True);export.write_text(original)
    reading=export.with_name('hash_original_romaji.txt');reading.write_text('Hello\nWorld')
    result={'rows':[{'start':1,'end':2,'original':'Hello','translation':'你好','romaji':'hello','readingSource':'user'},{'start':2,'end':3,'original':'World','translation':'世界','romaji':'world','readingSource':'user'}],'metadata':{'title':'歌','artist':'Artist'},'sourceFile':str(source),'source':'fixture','timed':True,'exports':[{'file':str(reading),'url':'/download/song-fixture/'+reading.name},{'file':str(export),'url':'/download/song-fixture/'+export.name}]};core.save_json(line,result);core.save_json(songroot/'analysis/lyrics-current.json',result)
    originals={str(f):core.sha(f) for folder in (old,oldvideo) for f in folder.rglob('*') if f.is_file()}
    proposal=organize.plan()
    with patch('urllib.request.urlopen',side_effect=OSError('closed')):report=organize.apply(proposal)
    assert not daw.BASE.exists() and not video_project.BASE.exists()
    current=core.read_json(songroot/'analysis/lyrics-current.json');assert len(current['exports'])==5 and all(Path(x['file']).is_file() for x in current['exports']);assert all('hash_' not in x['file'] for x in current['exports'])
    assert list(directory.glob('*.json'))==[] and (directory/'Lyrics 001/Source.json').is_file()
    updated=video_project.load('My Video');assert updated['cues']==doc['cues'] and updated['styles']==doc['styles'] and updated['audioOffset']==doc['audioOffset'] and Path(updated['video']).is_file()
    new=songroot/'studio-one/歌/Legacy.song'
    with zipfile.ZipFile(new) as z:
        assert z.read('OtherPlugin.vstpreset')==b'commercial plugin unchanged'
        for tag,value in daw.chunks(z.read('Host.vstpreset')):
            if tag==b'Comp':assert Path(json.loads(value)['projectPath'].replace('\\\\','\\')).is_file()
        assert str(old).replace('\\','/') not in z.read('Song.xml').decode()
    backup=Path(report['backup'])
    for oldpath,h in originals.items():assert core.sha(backup/'originals'/Path(oldpath).relative_to(root/'projects'))==h
    assert core.read_json(project_assets.STORE)['projects'][p['id']]['song']==str(new)
    state=project_library.save('music',{'mode':'manual','order':[p['id']]});assert state['order']==[p['id']]
    # A later lyric revision retains all download formats and creates a new readable file set.
    lyric_files.export(p,copy.deepcopy(current),directory/'Lyrics 001',revision=1)
    # A previously unadopted song reserves its planned root before nested copies.
    second={'id':'old-song','title':'New Song','artist':'Artist','pilot':str(root/'Original Pilot')}
    core.save_json(root/'config/projects.json',[p,second]);core.save_json(root/'data/projects/old-song.json',{'project':second})
    core.save_json(root/'config/video-links.local.json',{'links':{'old-song':{'videoId':'Other Video'}}})
    core.save_json(video_project.BASE/'Other Video/project.json',{**doc,'id':'Other Video','name':'Other Video'})
    with patch('urllib.request.urlopen',side_effect=OSError('closed')):organize.apply(organize.plan())
    assert workspaces.registry()['old-song']==str(root/'projects/Artist - New Song') and not (root/'projects/Artist - New Song_v2').exists()
    print('PASS: backed-up migration, native Song/SV links, unchanged plugin/media bytes, preserved video captions/style/alignment, readable lyric versions/download URLs and shelf preferences')
