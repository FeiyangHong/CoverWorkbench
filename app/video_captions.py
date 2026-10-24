"""Private cached subtitle layers rendered by the same libass path as exports."""
from pathlib import Path
import copy
import hashlib
import json
import re
import subprocess
import tempfile
import threading
import uuid

from core import ROOT
import lifecycle
import settings
import video_project as project

CACHE = ROOT / 'runtime/video-captions'
SESSION = uuid.uuid4().hex
SLOTS = threading.BoundedSemaphore(2)
LOCKS = tuple(threading.Lock() for _ in range(16))


def layout(body):
    width = int(project.number(body.get('width', 1920), 128, 4096, '字幕画面宽度'))
    height = int(project.number(body.get('height', 1080), 128, 4096, '字幕画面高度'))
    if width * height > 9_000_000:
        raise ValueError('字幕预览画面过大')
    rows = body.get('cues', [])
    if not isinstance(rows, list) or len(rows) > 8 or not all(isinstance(r, dict) for r in rows):
        raise ValueError('单帧最多预览 8 组字幕')
    rows = [{k: copy.deepcopy(v) for k, v in r.items()
             if k in ('id', 'original', 'translation', 'originalStyle', 'translationStyle')}
            | {'start': 0, 'end': 1} for r in rows]
    doc = project.validate(dict(video='', audio='', audioMode='gain', resolution='source',
                                fps='source', format='mp4', burn=True,
                                styles=copy.deepcopy(body.get('styles', {})), cues=rows))
    return width, height, doc


def render(body):
    with lifecycle.operation('字幕排版'):
        return _render(body)


def _render(body):
    width, height, doc = layout(body)
    ffmpeg = settings.executable('ffmpeg')
    signature = json.dumps([SESSION, width, height, doc], ensure_ascii=False, sort_keys=True).encode()
    key = hashlib.sha256(signature).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    output = CACHE / (key + '.png')
    with LOCKS[int(key[:2], 16) % len(LOCKS)]:
        if not output.is_file():
            if not SLOTS.acquire(timeout=3):
                raise ValueError('字幕排版繁忙，请稍后重试')
            try:
                with tempfile.TemporaryDirectory(prefix='layout-', dir=CACHE) as td:
                    folder = Path(td).resolve()
                    assert folder.parent == CACHE.resolve()
                    project.write_subtitles(doc, folder, 1)
                    args = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin',
                            '-f', 'lavfi', '-i', f'color=c=black@0.0:s={width}x{height}:r=1:d=1,format=rgba',
                            '-vf', 'ass=captions.ass:alpha=1', '-frames:v', '1', '-update', '1',
                            '-c:v', 'png', str(folder / 'layer.png')]
                    result = subprocess.run(args, cwd=folder, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if result.returncode or not (folder / 'layer.png').is_file():
                        raise ValueError('本机字幕排版失败，请检查 FFmpeg 的 libass 支持，或使用准确区间预览')
                    (folder / 'layer.png').replace(output)
            except subprocess.TimeoutExpired as exc:
                raise ValueError('字幕排版超时，请稍后重试') from exc
            finally:
                SLOTS.release()
            # Keep this disposable cache bounded; never touch song/project folders.
            cached = []
            for path in CACHE.glob('*.png'):
                try: cached.append((path.stat().st_mtime, path))
                except FileNotFoundError: pass
            for _, path in sorted(cached)[:-256]:
                if path != output:
                    try: path.unlink(missing_ok=True)
                    except OSError: pass
    return {'key': key, 'url': '/video-caption/' + key + '.png',
            'width': width, 'height': height, 'renderer': 'FFmpeg/libass'}


def media(name):
    if not re.fullmatch(r'[0-9a-f]{64}\.png', name):
        raise ValueError('无效字幕预览')
    path = CACHE / name
    if not path.is_file():
        raise ValueError('字幕预览已过期，请重新载入')
    return path
