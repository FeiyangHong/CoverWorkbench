"""Bounded, on-demand contact sheets for registered video sources; never edit originals."""
from pathlib import Path
import hashlib
import json
import re
import tempfile
import threading
from urllib.parse import quote

import settings
import video_project as project
import video_edit

WORKERS = threading.BoundedSemaphore(2)
LOCKS = tuple(threading.Lock() for _ in range(32))
CELLS, WIDTH, HEIGHT = 8, 120, 68


def cache(ident):
    return project.folder(ident) / 'Cache/Filmstrips'


def prepare(ident, body):
    item = video_edit.asset(ident, body.get('asset'))
    if not item or item['kind'] != 'video': raise ValueError('请选择媒体库内的视频')
    level, bucket = body.get('level'), body.get('bucket')
    if type(level) is not int or not 0 <= level <= 20 or type(bucket) is not int or not 0 <= bucket <= 270000:
        raise ValueError('无效的缩略图区间')
    step = .04 * 2**level; start = bucket * CELLS * step
    if start >= item['duration']: raise ValueError('缩略图区间超出素材时长')
    source = project.local(item['path'], project.MEDIA); stat = source.stat()
    key = hashlib.sha256(json.dumps([str(source), stat.st_size, stat.st_mtime_ns, level, bucket, 1]).encode()).hexdigest()
    folder = cache(ident); output = folder / (key+'.jpg')
    with LOCKS[int(key[:4],16)%len(LOCKS)], WORKERS:
        if not output.exists():
            folder.mkdir(parents=True, exist_ok=True)
            # Each seek decodes a single frame rather than the entire span of a long song.
            with tempfile.TemporaryDirectory(prefix='sheet-', dir=folder) as temp:
                for index in range(CELLS):
                    time = min(start+index*step, max(0, item['duration']-.08))
                    video_edit.command([settings.executable('ffmpeg'), '-v','error','-nostdin', '-threads','1',
                        '-ss',f'{time:.6f}','-i',source,'-frames:v','1','-vf',
                        f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1',
                        '-threads','1','-q:v','4',Path(temp)/f'{index:02}.jpg'], timeout=40)
                sheet = Path(temp)/'sheet.jpg'
                video_edit.command([settings.executable('ffmpeg'),'-v','error','-nostdin','-framerate','1','-i',Path(temp)/'%02d.jpg',
                    '-vf','tile=4x2','-frames:v','1','-threads','1','-q:v','4',sheet], timeout=40)
                sheet.replace(output)
    return {'url':'/video-filmstrip/'+quote(ident,safe='')+'/'+key,'start':start,'step':step,
            'cells':CELLS,'columns':4,'rows':2,'width':WIDTH,'height':HEIGHT}


def media(ident, key):
    if not re.fullmatch(r'[0-9a-f]{64}', key): raise ValueError('无效的缩略图')
    result = cache(ident)/(key+'.jpg')
    if not result.is_file(): raise ValueError('缩略图尚未生成')
    return result
