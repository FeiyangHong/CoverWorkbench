"""Timing provenance, exactly-once deltas, stale previews and generated caption guards."""
from pathlib import Path
import json
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import video_project as project
import video_workflow as workflow
import video_jobs
from core import sha,save_json


def review(doc,action):return workflow.review(doc['id'],{'revision':doc['revision'],'action':action})


def main():
    with tempfile.TemporaryDirectory(prefix='video timing ') as tmp:
        root=Path(tmp);project.BASE=root/'projects'
        video=root/'mv.mp4';audio=root/'mix.wav'
        video.write_bytes(b'synthetic video');audio.write_bytes(b'synthetic audio')
        original=root/'original.lrc';translation=root/'translation.lrc'
        original.write_text('[00:10.000]Hello\n[00:14.000]\n',encoding='utf-8')
        translation.write_text('[00:10.000]Test translation\n[00:14.000]\n',encoding='utf-8')
        hashes={str(p):sha(p) for p in [video,audio,original,translation]}
        doc=project.create({'name':'Guided Video'})
        assert not workflow.checks(doc,[])['steps'][0]['done']
        doc.update(video=str(video),audio=str(audio),audioOffset=5,subtitleShift=3)
        doc=project.save(doc['id'],doc)
        body={'original':str(original),'translation':str(translation),'clock':'audio'}
        doc=project.import_captions(doc['id'],body)
        assert doc['cues'][0]['start']==15 and doc['subtitleShift']==0
        doc=project.import_captions(doc['id'],body)
        assert doc['cues'][0]['start']==15,'Reimport added an offset twice'
        doc['audioOffset']=7;doc=project.save(doc['id'],doc)
        assert doc['cues'][0]['start']==17 and doc['timing']['appliedAudioOffset']==7
        doc=project.save(doc['id'],doc)
        assert doc['cues'][0]['start']==17,'Repeated save shifted captions twice'
        doc['subtitleShift']=7;doc=project.save(doc['id'],doc)
        assert any('可能重复' in s for s in workflow.blockers(doc))
        doc=review(doc,'ack-shift');assert not workflow.blockers(doc)
        doc['subtitleShift']=0;doc=project.save(doc['id'],doc)
        doc=review(doc,'alignment');assert workflow.checks(doc,[])['steps'][2]['done']
        doc['audioOffset']=8;doc=project.save(doc['id'],doc)
        assert not workflow.checks(doc,[])['steps'][2]['done']
        doc=review(doc,'video-clock');before=doc['cues'][0]['start']
        doc['audioOffset']=9;doc=project.save(doc['id'],doc)
        assert doc['cues'][0]['start']==before,'Fixed video captions moved with audio'
        exported=root/'export';exported.mkdir();project.write_subtitles(doc,exported,30)
        try:project.import_captions(doc['id'],{'original':str(exported/'captions.srt'),'clock':'audio'})
        except ValueError as e:assert '已经使用视频时间' in str(e)
        else:raise AssertionError('Generated video-time captions accepted an audio offset')
        doc=project.import_captions(doc['id'],{'original':str(exported/'captions.srt'),'clock':'video'})
        assert doc['cues'][0]['start']==before
        doc=review(doc,'alignment')
        sig=workflow.signature(doc)
        jid='a'*32;folder=project.folder(doc['id'])/'Jobs'/jid;folder.mkdir()
        job=dict(id=jid,kind='preview',status='completed',created=time.time(),result={'renderSignature':sig})
        save_json(folder/'job.json',job)
        assert workflow.checks(doc,[job])['previewReady']
        doc=review(doc,'preview');assert workflow.checks(doc,[job])['steps'][4]['done']
        doc['styles']['original']['size']=42;doc=project.save(doc['id'],doc)
        assert not workflow.checks(doc,[job])['previewReady'],'Changed typography reused a stale preview'
        assert all(sha(p)==h for p,h in hashes.items())
        audio.write_bytes(b'replaced mix')
        assert any('素材已更换' in s for s in workflow.blockers(doc))
        doc=review(doc,'video-clock');assert not workflow.blockers(doc)
        doc=review(doc,'aligned-audio');assert doc['audioOffset']==0
        doc['audioOffset']=5;doc=project.save(doc['id'],doc)
        assert any('已标记为对齐' in s for s in workflow.blockers(doc))
        catalog=video_jobs.font_catalog()
        assert next(f for f in catalog if f['family']=='Microsoft YaHei')['label']=='微软雅黑'
        assert next(f for f in catalog if f['family']=='SimHei')['label']=='黑体'
    print('PASS: one-time import/delta shifts, fixed video clock, explicit duplicate guards, replaced-source invalidation, fresh preview checks, original hashes and Chinese font labels')


if __name__=='__main__':main()
