"""Final-mix discovery: exact song scope, delivered copies and explicit selections."""
from pathlib import Path
import os
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import mix_sources as mixes
import video_links as links
import video_project as video
import project_assets as assets
from core import save_json,sha


def main():
    with tempfile.TemporaryDirectory(prefix='mix output discovery ') as td:
        root=Path(td);links.ROOT=assets.ROOT=root;links.STORE=root/'config/video-links.local.json';assets.STORE=root/'config/project-assets.local.json';video.BASE=root/'projects/video'
        workspace=root/'projects/Artist - Song';song=workspace/'studio-one/My Song/My Song.song';out=song.parent/'Mixdown'
        files={}
        def file(name,age=30):
            p=Path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'owned synthetic fixture');os.utime(p,(time.time()-age,time.time()-age));files[p]=sha(p);return p
        file(song);svp=file(workspace/'working/sv/project.svp');lead=file(out/'Lead.wav');backing=file(song.parent/'Media/instrumental.wav')
        old=file(out/'Singer - Song_Mixdown.wav',60);latest=file(out/'Singer - Song_Final.flac',20)
        file(root/'projects/Other/studio-one/Other/Mixdown/Other_Final.wav',10)
        p=dict(id='song',title='Song',artist='Artist',pilot=str(workspace),working=str(svp),audio={'lead':{'original':str(lead)},'accompaniment':{'original':str(backing)}})
        save_json(root/'config/projects.json',[{'id':'song','title':'Song'}]);save_json(root/'data/projects/song.json',{'project':p});save_json(root/'config/workspaces.local.json',{'song':str(workspace)})
        registration={'revision':1,'projects':{'song':{'song':str(song)}}};save_json(assets.STORE,registration)
        found=links.overview('song');assert found['audio']['path']==str(latest) and found['audio']['origin']=='studio-one';assert str(out) in found['audioDiscovery']['searchedFolders']
        assert str(lead) not in {r['path'] for r in found['audioCandidates']} and assets.status('song')['assets']['mix']['path']==str(latest)
        # The package copy remains available even when its original input has been removed.
        delivered=file(workspace/'exports/delivery/Done/master.wav');job=dict(id='done',pid='song',kind='delivery',status='completed',createdAt=1,input={'audio':str(root/'gone.wav')},outputDir=str(delivered.parent),files=[{'label':'原样混音音频','path':str(delivered)}])
        save_json(root/'runtime/workflow/done.json',job);assert links.overview('song')['audio']['path']==str(delivered)
        for name,value in [('failed',{**job,'status':'failed','createdAt':100}),('other',{**job,'pid':'other','createdAt':101}),('malformed',{'pid':'song','kind':'delivery','status':'completed','input':[],'files':None,'createdAt':'bad'})]:save_json(root/f'runtime/workflow/{name}.json',value)
        assert links.overview('song')['audio']['path']==str(delivered)
        # Explicit registration wins; clearing an automatic choice does not persist a guessed path.
        explicit=file(root/'Explicit.wav');registration['projects']['song']['mix']=str(explicit);save_json(assets.STORE,registration)
        assert links.overview('song')['audio']['path']==str(explicit)
        source=links.overview('song','"'+str(latest)+'"');assert source['audio']['path']==str(latest)
        target=links.perform('song',{'action':'create','name':'Song Video','audioPath':'','sourceSignature':links.overview('song','')['signature']})
        assert links.overview('song')['audioSelection']==''
        link=links.links();link['song']['audioPath']=str(root/'Moved.wav');links.persist(link)
        missing=links.overview('song');assert missing['audio'] is None and any('上次手动' in w for w in missing['audioDiscovery']['warnings']);assert links.overview('song','')['audio']['path']==str(explicit)
        # A build indexed outside the old global studio-one folder is still associated exactly.
        registration['projects']['song']={};save_json(assets.STORE,registration)
        for path in (root/'runtime/workflow').glob('*.json'):path.unlink()
        external_song=file(root/'External DAW/Session.song');external_mix=file(external_song.parent/'Mixdown/Export_Final.wav')
        record=root/'External DAW/build.json';save_json(record,dict(sourceSVP=str(svp),svp=str(root/'External DAW/SV/project.svp'),song=str(external_song),createdAt=3))
        save_json(root/'data/daw-build-index.json',[str(record)])
        state=assets.status('song');assert state['assets']['song']['path']==str(external_song) and state['assets']['mix']['path']==str(external_mix)
        # Never fall back to arbitrary lead/original audio, or to a file still being written.
        record.unlink();save_json(root/'data/daw-build-index.json',[]);registration['projects']['song']={'song':str(song)};save_json(assets.STORE,registration)
        old.unlink();latest.unlink();files.pop(old);files.pop(latest)
        recent=file(out/'Still_Final.wav',0);result=mixes.collect(p,root);assert not result['candidates'] and any('刚写入' in w for w in result['warnings']);recent.unlink();files.pop(recent)
        only_stems=mixes.collect(p,root);assert only_stems['candidates']==[]
        unmarked=file(workspace/'exports/audio/SV Render.wav');pending=mixes.collect(p,root);assert pending['candidates'] and mixes.preferred(pending) is None;assert pending['warnings']
        assert links.overview('song','')['audio'] is None and links.overview('song',str(unmarked))['audio']['path']==str(unmarked)
        watched=file(root/'WatchedCopy.wav');save_json(root/'runtime/workflow/watched.json',dict(pid='song',kind='delivery',status='completed',createdAt=10,fromWatcher=True,input={'audio':str(unmarked)},files=[dict(label='原样混音音频',path=str(watched))]));assert mixes.preferred(mixes.collect(p,root)) is None
        assert all(sha(path)==h for path,h in files.items())
    print('PASS: associated Mixdown/exports discovery, delivery copies after source removal, registered/manual precedence, missing-selection diagnostics, external build indexes, stem/unrelated/partial exclusion and immutable originals')


if __name__=='__main__':main()
