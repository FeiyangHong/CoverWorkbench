"""Layer schema, visibility, legacy compatibility and real top-layer rendering."""
from pathlib import Path
from unittest.mock import patch
import argparse
import copy
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import video_edit as edit
import video_tracks as layers
import video_project as project
import video_filmstrip as film
import settings
from core import sha


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cw layered picture ') as td:
        root=Path(td);project.BASE=root/'projects'
        red=root/'Red.mp4';blue=root/'Blue.mp4'
        assets=[dict(id=c*32,kind='video',duration=4,name=p.name,path=str(p)) for c,p in [('a',red),('b',blue)]]
        lower=dict(id='A',asset='a'*32,start=0,duration=4,**{'in':0},fit='cover',x=0,y=0)
        upper={**lower,'id':'B','asset':'b'*32,'start':1,'duration':2,'track':'V2'}
        legacy=dict(version=1,fps=25,duration=4,allowGaps=False,assets=assets,clips=[lower])
        assert 'tracks' not in edit.validate(legacy) and 'track' not in edit.validate(legacy)['clips'][0]
        comp={**legacy,'tracks':[dict(id='V1',name='主画面',hidden=False),dict(id='V2',name='上层 PV',hidden=False)],'clips':[lower,upper]}
        before=copy.deepcopy(comp);valid=edit.validate(comp)
        assert layers.front(valid,0)[1]['id']=='A' and layers.front(valid,40)[1]['id']=='B' and layers.front(valid,80)[1]['id']=='A'
        assert [(a,b,c['id'] if c else None) for a,b,tr,c in edit.picture_segments(valid,0,100)]==[(0,25,'A'),(25,75,'B'),(75,100,'A')]
        assert edit.gaps(valid)==[] and comp==before
        hidden=copy.deepcopy(valid);hidden['tracks'][1]['hidden']=True
        assert layers.front(hidden,40)[1]['id']=='A' and edit.sources({'composition':hidden})==[str(red)]
        reversed_comp={**valid,'tracks':list(reversed(valid['tracks']))};assert layers.front(reversed_comp,40)[1]['id']=='A'
        overlap=copy.deepcopy(comp);overlap['clips'][1]['track']='V1'
        try:edit.validate(overlap)
        except ValueError as e:assert '同一' in str(e)
        else:raise AssertionError('Same-track overlap accepted')
        unknown=copy.deepcopy(comp);unknown['clips'][1]['track']='missing'
        try:edit.validate(unknown)
        except ValueError:pass
        else:raise AssertionError('Unknown track accepted')
        all_hidden=copy.deepcopy(hidden);all_hidden['tracks'][0]['hidden']=True;assert edit.gaps(all_hidden)==[[0,4]]
        for bad_tracks in [[],[dict(id='Same',name='A'),dict(id='Same',name='B')],[dict(id=f'V{i}',name=str(i)) for i in range(9)]]:
            try:edit.validate({**comp,'tracks':bad_tracks})
            except ValueError:pass
            else:raise AssertionError('Invalid track list accepted')
        with patch.object(edit,'asset',return_value=assets[0]):
            for invalid in [dict(level=-1,bucket=0),dict(level=21,bucket=0),dict(level=1,bucket=-1),dict(level=0,bucket=10**100)]:
                try:film.prepare('unused',invalid)
                except ValueError:pass
                else:raise AssertionError('Unbounded thumbnail request accepted')
        # Lower transitions must not win while an upper layer covers their cut.
        transition=copy.deepcopy(valid);transition['clips']=[{**lower,'duration':2},
            {**lower,'id':'C','start':2,'duration':2,'transition':dict(type='dissolve',duration=.8,**{'from':'A'})},
            {**upper,'start':1.5,'duration':1}]
        transition=edit.validate(transition);assert layers.front(transition,50)[0] is None and layers.front(transition,50)[1]['id']=='B'
        # Clip-level changes preserve independent song and bilingual clocks through save/reload.
        doc=project.create({'name':'Layer Fixture'});doc.update(composition=valid,audioOffset=.4,subtitleShift=.1,cues=[dict(id='L1',start=.4,end=2,original='Keep',translation='保留')]);doc=project.save(doc['id'],doc)
        stored=copy.deepcopy(doc);doc['composition']['tracks'][1]['hidden']=True;doc=project.save(doc['id'],doc)
        for key in ['cues','styles','audioOffset','subtitleShift','audio','timing']:assert doc.get(key)==stored.get(key),key
        if args.installed:
            for target,color in [(red,'red'),(blue,'blue')]:
                edit.command([settings.executable('ffmpeg'),'-v','error','-nostdin','-f','lavfi','-i',f'color=c={color}:s=160x90:r=25:d=4','-an','-c:v','libx264','-threads','1',target])
            originals={p:sha(p) for p in [red,blue]}
            def execute(job,command,stage=''):
                edit.command([settings.executable('ffmpeg'),'-v','error','-nostdin',*command],timeout=120)
            def pixel(path,time):
                data=edit.command([settings.executable('ffmpeg'),'-v','error','-ss',time,'-i',path,'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','pipe:1']);return tuple(data[:3])
            for name,value,expected in [('Visible',valid,'blue'),('Hidden',hidden,'red'),('Reordered',reversed_comp,'red')]:
                folder=root/name;folder.mkdir();out=edit.build_picture({'snapshot':{'composition':value},'folder':str(folder)},1.2,1.6,execute,lambda *a,**k:None)
                r,g,b=pixel(out,.1);assert (b>180 and r<60) if expected=='blue' else (r>180 and b<60),(name,(r,g,b))
            # Contact sheets contain successive source frames and are reused without decoding again.
            changing=root/'Changing.mp4';edit.command([settings.executable('ffmpeg'),'-v','error','-nostdin',
                '-f','lavfi','-i','color=red:s=160x90:r=25:d=1','-f','lavfi','-i','color=green:s=160x90:r=25:d=1','-f','lavfi','-i','color=blue:s=160x90:r=25:d=1',
                '-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]','-map','[v]','-c:v','libx264','-threads','1',changing])
            asset=edit.import_media(doc['id'],{'path':str(changing)});hash_before=sha(changing)
            result=film.prepare(doc['id'],{'asset':asset['id'],'level':4,'bucket':0});key=result['url'].split('/')[-1];sheet=film.media(doc['id'],key)
            rgb=edit.command([settings.executable('ffmpeg'),'-v','error','-i',sheet,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
            def cell(i):
                x=(i%4)*120+60;y=(i//4)*68+34;index=(y*480+x)*3;return tuple(rgb[index:index+3])
            assert cell(0)[0]>180 and cell(2)[1]>70 and cell(4)[2]>180,[cell(i) for i in range(8)]
            with patch.object(edit,'command',side_effect=AssertionError('Cache re-decoded')):assert film.prepare(doc['id'],{'asset':asset['id'],'level':4,'bucket':0})==result
            assert sha(changing)==hash_before and all(sha(p)==h for p,h in originals.items())
            print('PASS: actual layered/hidden/reordered interval renders, sequential contact-sheet pixels, cached reuse and immutable originals')
    print('PASS: legacy schema, parallel tracks, same-track collision checks, layer order/hide, union coverage, transition priority and fixed song/caption clocks')


if __name__=='__main__':main()
