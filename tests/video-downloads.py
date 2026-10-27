"""Provider-title downloads with flat media, separate records and no network access."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import sys
import tempfile
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from core import read_json,save_json,sha
from windows_names import component
import media_names
import video_project as project
import video_storage as storage
import video_jobs as jobs
import video_edit as edit
import video_links


def main():
    for title in ['合成歌手 - テスト曲 (Official Video)','测试 #1 100%','../outside','CON','NUL.txt','Intro: Part / 2?','🎵'*150]:
        name=media_names.filename(title,'.mkv');assert component(name)==name and len(name.encode('utf-16-le'))<=510
    assert media_names.filename('Intro: Part / 2?','.mp4')=='Intro： Part ／ 2？.mp4'
    assert media_names.filename('CON','.mkv')=='Video - CON.mkv'
    with tempfile.TemporaryDirectory(prefix='titled download ') as td:
        video_links.STORE=Path(td)/'config/video-links.local.json'
        project.BASE=Path(td)/'projects';doc=project.create({'name':'Synthetic Downloads'})
        root=project.folder(doc['id']);legacy=root/'Jobs/Download 005';legacy.mkdir()
        old=legacy/'source.mkv';old.write_bytes(b'old media must remain referenced')
        legacy_id='f'*32
        record={'id':legacy_id,'kind':'download','project':doc['id'],'status':'completed','version':5,'created':1,
                'files':['source.mkv','provenance.json'],'folder':str(legacy),'result':{'path':str(old)}}
        save_json(legacy/'job.json',record)
        doc.update(video=str(old),audio=str(old),audioOffset=.4,subtitleShift=.2,cues=[dict(id='A',start=1,end=2,original='Keep original',translation='保持原位')])
        doc=project.save(doc['id'],doc)
        protected={p:sha(p) for p in [old,legacy/'job.json',root/'project.json']}
        title='合成歌手 - テスト曲 (Official Video)';payload=b'first completed video';requests=[]
        def fake_command(job,args,**kwargs):
            template=Path(args[args.index('-o')+1]);assert template.is_relative_to(root/'Cache/Downloads')
            assert title not in ' '.join(map(str,args)), 'Website title reached a shell/CLI argument'
            template.with_name('source.mkv').write_bytes(payload)
            save_json(template.with_name('source.info.json'),{'title':title,'id':'synthetic','extractor':'youtube'})
            (Path(job['folder'])/'command-00.log').write_text('synthetic downloader log')
            requests.append(args);return ''
        def task():
            minimum=max((j.get('version',0) for j in jobs.history(doc['id']) if j['kind']=='download'),default=0)+1
            folder,version=storage.reserve(root,'download',minimum)
            assert folder.parent==root/'Tasks'
            j=dict(id=uuid.uuid4().hex,project=doc['id'],kind='download',folder=str(folder),outputRoot=str(root),version=version,
                   status='running',created=time.time(),files=[],spec={'url':'https://www.youtube.com/watch?v=synthetic','height':1080},cancel=threading.Event())
            save_json(folder/'snapshot.json',doc)
            return j
        with patch.object(jobs,'command',side_effect=fake_command),patch.object(jobs,'probe',return_value={'duration':3,'streams':[{'codec_type':'video'}]}),patch.object(jobs.settings,'executable',return_value='ffmpeg'):
            first=task();jobs.download(first);jobs.update(first,status='completed')
            media=Path(first['result']['path']);assert media==root/'Media/Video'/(title+'.mkv')
            assert first['version']==6 and not first['result']['reused']
            assert not (root/'Cache/Downloads'/first['id']).exists()
            assert (Path(first['folder'])/'info.json').is_file() and (Path(first['folder'])/'provenance.json').is_file()
            assert not list((root/'Media').rglob('*.json')) and not list((root/'Media').rglob('*.log'))
            second=task();jobs.download(second);jobs.update(second,status='completed')
            assert second['result']['path']==str(media) and second['result']['reused']
            payload=b'a different completed video'
            third=task();jobs.download(third);jobs.update(third,status='completed')
            assert Path(third['result']['path']).name==title+'_v2.mkv' and media.read_bytes()==b'first completed video'
            title='Intro: Part / 2?';fourth=task();jobs.download(fourth);jobs.update(fourth,status='completed')
            assert Path(fourth['result']['path']).name=='Intro： Part ／ 2？.mkv'
        assert len(jobs.history(doc['id']))==5
        assert storage.locate(root,legacy_id)[0]==legacy
        assert storage.locate(root,first['id'])[0]==Path(first['folder'])
        with patch.object(edit,'inspect',return_value={'kind':'video','duration':3,'width':320,'height':180}),patch.object(edit,'command',return_value=b''):
            alias=root/'Media/Video/source.mkv';alias.write_bytes(media.read_bytes())
            old_asset=dict(id='0'*32,name='source.mkv',path=str(alias),sha256=sha(alias),kind='video',duration=3)
            save_json(root/'media-library.json',[old_asset])
            before={p for p in (root/'Media').rglob('*') if p.is_file()}
            asset=edit.import_media(doc['id'],{'path':str(media)})
            assert Path(asset['path'])==media and asset['name']==media.name
            assert read_json(root/'media-library.json')[0]==old_asset,'An existing clip/alias was renamed'
            assert {p for p in (root/'Media').rglob('*') if p.is_file()}==before,'Downloaded media was copied a second time'
            linked=Path(td)/'linked output/Media/Video/合成 - Linked.mkv';linked.parent.mkdir(parents=True);linked.write_bytes(b'linked workspace media')
            with patch.object(project,'output_locations',return_value=[Path(td)/'linked output',root]):
                assert Path(edit.import_media(doc['id'],{'path':str(linked)})['path'])==linked
        # Exclusive filename reservation protects independent writers sharing the same project.
        sources=[]
        for i in range(4):
            p=Path(td)/f'input-{i}.mkv';p.write_bytes(bytes([i])*20000);sources.append(p)
        with ThreadPoolExecutor(max_workers=4) as pool:
            targets=list(pool.map(lambda p:jobs.publish_download({'outputRoot':str(root),'cancel':threading.Event()},p,root/'Media/Video','Concurrent Title')[0],sources))
        assert len(set(targets))==4 and {sha(p) for p in targets}=={sha(p) for p in sources}
        # Cancellation removes the owned partial copy and never removes another media file.
        huge=Path(td)/'large.mkv';huge.write_bytes(b'x'*(3*1024*1024));cancel=threading.Event();calls=0
        real_check=jobs.check
        def cancel_during_copy(j):
            nonlocal calls
            calls+=1
            if calls==3:cancel.set()
            real_check(j)
        with patch.object(jobs,'check',side_effect=cancel_during_copy):
            try:jobs.publish_download({'outputRoot':str(root),'cancel':cancel},huge,root/'Media/Video','Cancelled Copy')
            except jobs.Cancelled:pass
            else:raise AssertionError('Cancellation was ignored')
        assert not list((root/'Media/Video').glob('Cancelled Copy*'))
        # Missing metadata must fail in Tasks, not publish a generic source/Download video.
        failed=task();media_before={p:sha(p) for p in (root/'Media/Video').iterdir()}
        def no_metadata(j,args,**kwargs):
            Path(args[args.index('-o')+1]).with_name('source.mkv').write_bytes(b'download without a title')
            return ''
        with patch.object(jobs,'command',side_effect=no_metadata),patch.object(jobs.settings,'executable',return_value='ffmpeg'):
            jobs.run(failed)
        assert failed['status']=='failed' and '标题信息' in failed['message']
        assert {p:sha(p) for p in (root/'Media/Video').iterdir()}==media_before
        assert all(sha(p)==digest for p,digest in protected.items())
    print('PASS: website titles, flat Media/Video, separate Tasks records, safe Unicode names, duplicate reuse/versioning, concurrent publication, cancelled-copy cleanup, library reuse and unchanged legacy references')


if __name__=='__main__':main()
