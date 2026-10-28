"""Private browser previews and bounded waveforms; registered originals stay read-only."""
from pathlib import Path
from urllib.parse import quote
from array import array
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
import threading
import uuid

from core import ROOT, read_json, save_json
import settings
import video_project as project
import video_edit

CACHE = ROOT / 'runtime/video-preview'
LOCKS = tuple(threading.Lock() for _ in range(32))
WORKERS = threading.BoundedSemaphore(2)


def source(ident, body):
    doc = project.load(ident)
    if body.get('revision') != doc['revision']:
        raise ValueError('工程已更新，请保存当前素材后重试')
    if body.get('asset'):
        item = video_edit.asset(ident, body['asset'])
        if not item:
            raise ValueError('媒体库中没有这个素材')
        path = item['path']
    else:
        role = body.get('role', 'video')
        if role not in ('video', 'audio'):
            raise ValueError('请选择原视频或成品混音')
        path = doc.get(role)
    path = project.local(path, project.MEDIA)
    if body.get('expectedPath') and str(path) != str(Path(project.clean_path(body['expectedPath'])).resolve()):
        raise ValueError('路径尚未应用，请先点击“应用并加载”或保存工程')
    return path, fingerprint(path)


def fingerprint(path):
    stat = path.stat()
    return hashlib.sha256(json.dumps([str(path), stat.st_size, stat.st_mtime_ns, 3]).encode()).hexdigest()


def peaks(path, duration):
    rate, bins = 2000, 4096
    step = max(1, math.ceil(duration * rate / bins))
    values, count, peak = [], 0, 0.
    # Decode in chunks; neither long files nor malformed headers allocate a PCM-sized buffer.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([settings.executable('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(path),
                                    '-vn', '-map', '0:a:0', '-af', f'aresample={rate}:async=1:first_pts=0,apad,atrim=duration={duration}',
                                    '-ac', '1', '-ar', str(rate), '-f', 'f32le', 'pipe:1'],
                                   stdout=subprocess.PIPE, stderr=errors,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        timer = threading.Timer(180, process.kill)
        timer.start()
        try:
            while block := process.stdout.read(32768):
                samples = array('f'); samples.frombytes(block)
                if sys.byteorder != 'little': samples.byteswap()
                for value in samples:
                    if math.isfinite(value): peak = max(peak, abs(value))
                    count += 1
                    if count == step:
                        values.append(round(min(1, peak), 6)); count, peak = 0, 0.
                if len(values) > bins * 2:
                    raise ValueError('音频时长与元数据不符，无法生成波形')
            if process.wait(timeout=5):
                errors.seek(0)
                raise ValueError('无法读取音频波形：' + errors.read().decode('utf-8', errors='replace')[-350:])
            if count: values.append(round(min(1, peak), 6))
        finally:
            timer.cancel()
            if process.poll() is None: process.kill()
            process.wait()
            process.stdout.close()
    return {'available': True, 'duration': duration, 'step': step / rate, 'peaks': values}


def prepare(ident, body):
    kind = body.get('kind', 'waveform')
    if kind not in ('waveform', 'audio', 'video'):
        raise ValueError('无效预览类型')
    path, key = source(ident, body)
    with LOCKS[int(key[:4], 16) % len(LOCKS)], WORKERS:
        folder = CACHE / key
        folder.mkdir(parents=True, exist_ok=True)
        metadata_file = folder / 'metadata.json'
        metadata = read_json(metadata_file) if metadata_file.is_file() else video_edit.inspect(path)
        if not metadata_file.is_file(): save_json(metadata_file, metadata)
        if kind in ('waveform', 'audio') and not metadata['hasAudio']:
            return {'available': False, 'duration': metadata['duration'], 'peaks': [], 'message': '此素材没有音轨'}
        if kind == 'waveform':
            output = folder / 'waveform.json'
            result = read_json(output) if output.is_file() else peaks(path, metadata['duration'])
            if fingerprint(path) != key:
                raise ValueError('源素材在处理期间改变，请重新应用路径')
            if not output.is_file(): save_json(output, result)
            result['key'] = key
            return result
        if kind == 'video' and not body.get('force') and path.suffix.lower() in ('.mp4', '.webm', '.mov') and metadata['videoCodec'] in ('h264', 'vp8', 'vp9', 'av1'):
            return {'available': True, 'url': '/video-source/' + quote(ident, safe='') + '/video?v=' + str(body['revision']), 'proxy': False, **metadata}
        extension = 'm4a' if kind == 'audio' else 'mp4'
        output = folder / (kind + '.' + extension)
        if not output.is_file():
            partial = folder / ('partial-' + uuid.uuid4().hex + '.' + extension)
            args = ['-map', '0:a:0', '-vn','-af',f"aresample=48000:async=1:first_pts=0,apad,atrim=duration={metadata['duration']}", '-c:a', 'aac', '-b:a', '320k'] if kind == 'audio' else [
                '-map', '0:v:0', '-map', '0:a:0?', '-vf', 'scale=960:540:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k']
            try:
                video_edit.command([settings.executable('ffmpeg'), '-v', 'error', '-nostdin', '-i', path,
                                    *args, '-movflags', '+faststart', '-y', partial], timeout=900)
                # A file overwritten by a DAW/download while processing must not get a reusable cache entry.
                if fingerprint(path) != key:
                    raise ValueError('源素材在处理期间改变，请重新应用路径')
                partial.replace(output)
            finally:
                partial.unlink(missing_ok=True)
        return {'available': True, 'key': key, 'url': '/video-preview/' + key + '/' + output.name, 'proxy': True, **metadata}


def media(key, name):
    if not re.fullmatch(r'[0-9a-f]{64}', key) or name not in ('audio.m4a', 'video.mp4'):
        raise ValueError('无效预览文件')
    path = CACHE / key / name
    if not path.is_file(): raise ValueError('预览尚未生成')
    return path
