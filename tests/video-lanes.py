"""Independent language clocks survive saving, shifts, ASS/SRT and real burn-in."""
from pathlib import Path
import argparse
import copy
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import video_project as project
import video_workflow as workflow
import settings
from core import read_json,read_srt,sha


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='independent captions ') as tmp:
        root=Path(tmp);project.BASE=root/'projects'
        video=root/'video.mp4';audio=root/'audio.wav';video.write_bytes(b'private video placeholder');audio.write_bytes(b'private mix placeholder')
        hashes={str(p):sha(p) for p in [video,audio]}
        doc=project.create({'name':'Independent Captions'})
        doc.update(video=str(video),audio=str(audio),audioOffset=2,cues=[
            {'id':'A','start':1,'end':3,'original':'One','translation':'T1','translationTiming':{'start':1.5,'end':3.5}},
            {'id':'B','start':5,'end':6,'original':'Two','translation':'T2'}])
        doc=project.save(doc['id'],doc,internal={'timing':workflow.timing(doc,'audio','test')})
        assert project.load(doc['id'])['cues']==doc['cues']
        original=copy.deepcopy(doc)
        doc['audioOffset']=3;doc=project.save(doc['id'],doc)
        assert doc['cues'][0]['start']==2 and doc['cues'][0]['translationTiming']=={'start':2.5,'end':4.5}
        doc=project.save(doc['id'],doc);assert doc['cues'][0]['translationTiming']['start']==2.5
        doc['audioOffset']=2;doc=project.save(doc['id'],doc);assert doc['cues']==original['cues']
        for timing in [{'start':-1,'end':2},{'start':2,'end':1},{'start':1},'invalid',{'start':1,'end':2,'extra':1}]:
            invalid=copy.deepcopy(doc);invalid['cues'][0]['translationTiming']=timing
            try:project.save(doc['id'],invalid)
            except ValueError:pass
            else:raise AssertionError('Invalid independent time was saved')
        assert project.load(doc['id'])['cues']==doc['cues']
        folder=root/'output';folder.mkdir();project.write_subtitles(doc,folder,10)
        text=(folder/'captions.ass').read_text(encoding='utf-8-sig')
        assert 'Dialogue: 0,0:00:01.00,0:00:03.00,S0_original' in text
        assert 'Dialogue: 0,0:00:01.50,0:00:03.50,S0_translation' in text
        srt=read_srt(folder/'captions.srt')
        assert [(r['start'],r['end'],r['text']) for r in srt]==[(1,1.5,'One'),(1.5,3,'One\nT1'),(3,3.5,'T1'),(5,6,'Two\nT2')]
        doc['subtitleShift']=.25;project.write_subtitles(doc,folder,10)
        assert read_srt(folder/'captions.srt')[0]['start']==1.25
        assert doc['cues']==original['cues'],'Writing applied the subtitle shift to stored times'
        if args.installed:
            from PIL import Image
            doc['subtitleShift']=0
            doc['styles']['original'].update(font='Arial',color='#ff0000',shadow=0)
            doc['styles']['translation'].update(font='Arial',color='#0000ff',shadow=0)
            project.write_subtitles(doc,folder,10)
            for time,red,blue in [(0.25,False,False),(1.25,True,False),(1.75,True,True),(3.25,False,True)]:
                out=folder/f'frame-{time}.png'
                subprocess.run([settings.executable('ffmpeg'),'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=white:s=640x360:r=25:d=4',
                                '-vf',f'ass=captions.ass,select=gte(t\\,{time})','-frames:v','1','-update','1',str(out)],cwd=folder,check=True,timeout=15)
                data=Image.open(out).convert('RGB').tobytes();pixels=list(zip(data[0::3],data[1::3],data[2::3]))
                has_red=any(r>150 and g<100 and b<100 for r,g,b in pixels)
                has_blue=any(b>150 and r<100 and g<100 for r,g,b in pixels)
                assert (has_red,has_blue)==(red,blue),(time,has_red,has_blue)
            print('PASS: real ASS burn-in before, during and after independently timed language lines')
        assert all(sha(p)==checksum for p,checksum in hashes.items())
    print('PASS: independent clocks, save/reload, exact-once audio shifts, validation, non-overlapping bilingual SRT and source preservation')


if __name__=='__main__':main()
