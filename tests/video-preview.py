"""Read-only original audio/waveform/proxy caching; optional real FFmpeg integration."""
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
import argparse
import copy
import math
import struct
import subprocess
import sys
import tempfile
import wave

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from core import save_json,sha
import video_project as project
import video_edit as edit
import video_preview as preview
import settings


def reject(fn,text):
    try: fn()
    except ValueError as error: assert text in str(error),str(error)
    else: raise AssertionError('Expected rejection: '+text)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='video monitoring ') as td,ExitStack() as stack:
        root=Path(td);project.BASE=root/'projects';preview.CACHE=root/'runtime/preview'
        audio=root/'Mix.wav'
        with wave.open(str(audio),'wb') as file:
            file.setparams((1,2,48000,0,'NONE','not compressed'))
            file.writeframes(b''.join(struct.pack('<h',round(math.sin(i/48000*440*2*math.pi)*8000)) for i in range(48000*2)))
        video=root/'Source.mkv';silent=root/'Silent.mkv'
        if args.installed:
            ff=settings.executable('ffmpeg')
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=c=red:s=320x180:r=25:d=2','-i',str(audio),'-c:v','libvpx-vp9','-c:a','libopus','-shortest',str(video)],check=True)
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=25:d=2','-c:v','libvpx-vp9',str(silent)],check=True)
        else:
            video.write_bytes(b'synthetic source video');silent.write_bytes(b'synthetic silent video')
            stack.enter_context(patch.object(edit,'inspect',side_effect=lambda p:dict(duration=2,hasAudio=Path(p)!=silent,kind='video',videoCodec='vp9',audioCodec='opus',width=320,height=180)))
            stack.enter_context(patch.object(preview,'peaks',return_value={'available':True,'duration':2,'step':.5,'peaks':[.1,.8,.2,.5]}))
            stack.enter_context(patch.object(edit,'command',side_effect=lambda cmd,**kwargs:Path(cmd[-1]).write_bytes(b'synthetic preview') or b''))
            stack.enter_context(patch.object(settings,'executable',return_value='ffmpeg'))
        doc=project.create({'name':'合成 - Preview'})
        doc.update(video=str(video),audio=str(audio),audioOffset=.4,subtitleShift=.1)
        doc['cues']=[dict(id='L1',start=.4,end=1.4,original='Synthetic',translation='合成字幕')]
        doc=project.save(doc['id'],doc);original=sha(project.folder(doc['id'])/'project.json')
        files={p:sha(p) for p in [video,audio,silent]}
        body=dict(revision=doc['revision'],role='video',expectedPath=str(video))
        waveform=preview.prepare(doc['id'],dict(body,kind='waveform'))
        assert waveform['available'] and max(waveform['peaks'])>0 and len(waveform['peaks'])<=8192
        with patch.object(preview,'peaks',side_effect=AssertionError('Waveform was decoded twice')):
            assert preview.prepare(doc['id'],dict(body,kind='waveform'))==waveform
        sound=preview.prepare(doc['id'],dict(body,kind='audio'));movie=preview.prepare(doc['id'],dict(body,kind='video'))
        assert sound['available'] and movie['proxy'] and preview.media(sound['key'],'audio.m4a').is_file()
        if args.installed:
            assert edit.inspect(preview.media(sound['key'],'audio.m4a'))['audioCodec']=='aac'
            metadata=edit.inspect(preview.media(movie['key'],'video.mp4'))
            assert metadata['hasAudio'] and metadata['videoCodec']=='h264'
        with patch.object(edit,'command',side_effect=AssertionError('Preview was encoded twice')):
            assert preview.prepare(doc['id'],dict(body,kind='audio'))['url']==sound['url']
        reject(lambda:preview.prepare(doc['id'],dict(body,revision=-1)),'工程已更新')
        reject(lambda:preview.prepare(doc['id'],dict(body,expectedPath=str(audio))),'路径尚未应用')
        reject(lambda:preview.prepare(doc['id'],dict(body,asset='missing')),'媒体库')
        reject(lambda:preview.media('../outside','audio.m4a'),'无效')
        reject(lambda:preview.media(sound['key'],'waveform.json'),'无效')
        assert sha(project.folder(doc['id'])/'project.json')==original
        doc['video']=str(silent);doc=project.save(doc['id'],doc)
        result=preview.prepare(doc['id'],{'revision':doc['revision'],'kind':'audio','role':'video'})
        assert not result['available'] and '没有音轨' in result['message']
        if args.installed:
            imported=edit.import_media(doc['id'],{'path':str(video)})
            proxy=edit.proxy(doc['id'],{'asset':imported['id']})
            assert edit.inspect(proxy['proxy'])['hasAudio'],'Library proxy discarded its original audio'
        assert all(sha(p)==value for p,value in files.items())
    print('PASS: waveform/audio/video caches, original sound preserved, missing-audio handling, revision/path guards, private cache boundaries and unchanged media/project')
    if args.installed: print('PASS: real MKV VP9/Opus to browser H264/AAC, audible waveform and library proxy audio')


if __name__=='__main__':main()
