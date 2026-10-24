"""Native subtitle layout validation, caching and optional real raster parity."""
from pathlib import Path
import argparse
import copy
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import video_captions as captions
import video_project as project
import settings
import lifecycle
from core import sha


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='caption parity ') as tmp:
        captions.CACHE=Path(tmp)/'cache'
        body={'width':1920,'height':1080,'styles':{'original':{**project.STYLE,'font':'Arial','size':40,'spacing':1.2,'bold':True,'outline':3,'color':'#e5ecff'},
              'translation':{**project.STYLE,'size':44,'y':1026,'outline':4}},
              'cues':[{'id':'A','original':'A caption with spacing and outlines','translation':'中文排版测试'}]}
        width,height,doc=captions.layout(body)
        assert (width,height)==(1920,1080) and doc['cues'][0]['start']==0 and doc['cues'][0]['end']==1
        for change in [{'width':float('nan')},{'width':4096,'height':4096},{'cues':[{}]*9},
                       {'styles':{'original':{'font':'Bad,Font'}}},{'cues':[{'id':'A','original':'x'*2001}]}]:
            try:captions.layout({**body,**change})
            except ValueError:pass
            else:raise AssertionError('Invalid native subtitle input accepted')
        for name in ['../project.json','wrong.png','a'*64+'.svg']:
            try:captions.media(name)
            except ValueError:pass
            else:raise AssertionError('Cache path traversal accepted')
        calls=[]
        def fake_run(*a,**kwargs):
            assert lifecycle.status()['operations'].get('字幕排版')==1
            calls.append(1);(Path(kwargs['cwd'])/'layer.png').write_bytes(b'synthetic PNG placeholder')
            return subprocess.CompletedProcess(a,0)
        with patch.object(settings,'executable',return_value=sys.executable),patch.object(captions.subprocess,'run',side_effect=fake_run):
            first=captions.render(body);assert captions.media(first['key']+'.png').is_file()
            assert captions.render(copy.deepcopy(body))==first and len(calls)==1
            changed=copy.deepcopy(body);changed['styles']['original']['size']=50
            second=captions.render(changed);assert second['key']!=first['key'] and len(calls)==2
            changed['cues'][0]['original']='Changed lyric'
            assert captions.render(changed)['key']!=second['key'] and len(calls)==3
        assert lifecycle.status()['canExit']
        if args.installed:
            from PIL import Image,ImageChops,ImageStat
            captions.CACHE=Path(tmp)/'real-cache'
            ff=settings.executable('ffmpeg')
            for width,height in [(1920,1080),(1280,720),(960,720)]:
                payload={**body,'width':width,'height':height}
                result=captions.render(payload);layer=Image.open(captions.media(result['key']+'.png')).convert('RGBA')
                assert layer.getchannel('A').getbbox() and layer.getpixel((0,0))[3]==0
                folder=Path(tmp)/f'ground-{width}';folder.mkdir()
                _,_,doc=captions.layout(payload);project.write_subtitles(doc,folder,1)
                for color,background in [('black',(0,0,0,255)),('white',(255,255,255,255))]:
                    subprocess.run([ff,'-hide_banner','-loglevel','error','-f','lavfi','-i',f'color=c={color}:s={width}x{height}:r=1:d=1,format=rgba',
                                    '-vf','ass=captions.ass','-frames:v','1','-update','1',str(folder/(color+'.png'))],cwd=folder,check=True,timeout=15)
                    expected=Image.open(folder/(color+'.png')).convert('RGB')
                    actual=Image.alpha_composite(Image.new('RGBA',layer.size,background),layer).convert('RGB')
                    diff=ImageChops.difference(actual,expected)
                    mean=sum(ImageStat.Stat(diff).mean)/3
                    # Raster positions, outlines, spacing and shadows share one ASS document.
                    assert mean<.1,(width,height,color,mean)
                    assert actual.size==expected.size
                print(f'PASS: real libass layer vs direct burn-in at {width}x{height}, black/white backgrounds')
    print('PASS: input bounds, private cache paths, layout/text invalidation, reuse and shutdown protection')


if __name__=='__main__':main()
