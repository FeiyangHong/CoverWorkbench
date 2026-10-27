"""Explicit same-project editing enablement preserves saved music/subtitle clocks."""
from pathlib import Path
from unittest.mock import patch
import copy
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from core import read_json,sha
import video_project as project
import video_edit as edit
import video_links
import video_workflow as workflow


def main():
    with tempfile.TemporaryDirectory(prefix='enable multi edit ') as td:
        root=Path(td);project.BASE=root/'projects';video_links.STORE=root/'links.json'
        video=root/'Original.mp4';audio=root/'Mix.wav'
        video.write_bytes(b'synthetic video');audio.write_bytes(b'synthetic audio')
        doc=project.create({'name':'Enable Edit Fixture'})
        doc.update(video=str(video),audio=str(audio),audioOffset=.4,subtitleShift=.1,gainDb=-2,
                   cues=[dict(id='A',start=.3,end=2.1,original='Original lyric',translation='保留字幕',originalTiming={'start':.2,'end':2.3})])
        doc=project.save(doc['id'],doc);doc=workflow.review(doc['id'],{'revision':doc['revision'],'action':'video-clock'})
        before=copy.deepcopy(doc);original_hash=sha(project.folder(doc['id'])/'project.json');sources={p:sha(p) for p in [video,audio]}
        try:edit.enable(doc['id'],{'revision':doc['revision']-1})
        except ValueError as e:assert '工程已更新' in str(e)
        else:raise AssertionError('Stale enablement overwrote a project')
        assert sha(project.folder(doc['id'])/'project.json')==original_hash
        def metadata(path):
            return {'kind':'audio' if Path(path)==audio else 'video','duration':6 if Path(path)==audio else 2.33,'width':320,'height':180}
        with patch.object(edit,'inspect',side_effect=metadata),patch.object(edit,'command',return_value=b''):
            result=edit.enable(doc['id'],{'revision':doc['revision'],'autoProxy':False})
        now=result['project'];assert now['id']==before['id'] and now['name']==before['name']
        assert len(project.listing())==1 and now['revision']==before['revision']+1
        for key in ['cues','styles','audio','video','audioOffset','subtitleShift','gainDb','timing','workflow']:
            assert now.get(key)==before.get(key),key+' changed while enabling editing'
        assert now['composition']['duration']==6.4 and len(now['composition']['clips'])==1
        clip=now['composition']['clips'][0];assert clip['start']==0 and clip['in']==0 and clip['duration']==2.32
        assert read_json(project.folder(doc['id'])/'History'/f"r{before['revision']:06}.json")==before
        assert all(sha(p)==value for p,value in sources.items())
        assert edit.enable(now['id'],{'revision':now['revision']})['project']==now,'Enabling twice duplicated clips'
        blank=project.create({'name':'Blank Multi Edit'})
        enabled=edit.enable(blank['id'],{'revision':blank['revision']})['project']
        assert enabled['composition']['duration']==30 and enabled['composition']['clips']==[]
    print('PASS: explicit editing enablement, same project/links, original picture position, preserved bilingual timing/styles/mix, history backup, stale guards and idempotency')


if __name__=='__main__':main()
