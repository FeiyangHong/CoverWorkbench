"""Local, optional VST3 auditions in isolated, time-limited worker processes."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import settings
import lifecycle

ROOT = settings.ROOT
CACHE = ROOT / 'runtime/mix-auditions'
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mix-audition')
LOCK = threading.Lock()
JOBS = {}
PLUGINS = {'reverb': 'FabFilter Pro-R 2', 'delay': 'FabFilter Timeless 3', 'eq': 'FabFilter Pro-Q 3'}
CONTROLS = {
    'reverb': [('space', 'Space · 空间时间', .3, 3.5, 1.2, .1, 's'),
               ('predelay', 'Predelay · 预延迟', 0, 100, 30, 1, 'ms'),
               ('mix', 'Mix · 混响比例', 0, 60, 25, 1, '%')],
    'delay': [('time', 'Delay Time · 回声间隔', 100, 750, 375, 5, 'ms'),
              ('feedback', 'Feedback · 反馈', 0, 65, 30, 1, '%'),
              ('mix', 'Mix · 回声比例', 0, 60, 30, 1, '%')],
    'eq': [('freq', 'Frequency · 中心频率', 100, 12000, 350, 10, 'Hz'),
           ('gain', 'Gain · 增益', -12, 12, -6, .5, 'dB'),
           ('q', 'Q · 范围宽窄', .3, 4, 1, .1, '')],
}


def plugin_path(kind):
    return plugin_binary(PLUGINS[kind])


def plugin_binary(name):
    base = os.environ.get('COVERWORKBENCH_VST3_DIR')
    base = Path(base) if base else Path(os.environ.get('CommonProgramFiles', 'C:/Program Files/Common Files')) / 'VST3/FabFilter'
    p = base / (name + '.vst3')
    return p if p.exists() else None


def status():
    engine = importlib.util.find_spec('pedalboard') is not None
    decoder = bool(settings.executable('ffmpeg', False) and settings.executable('ffprobe', False))
    return {'engine': engine, 'decoder': decoder, 'maxSeconds': 30,
            'plugins': [{'id': k, 'name': v, 'installed': plugin_path(k) is not None,
                         'controls': CONTROLS[k]} for k, v in PLUGINS.items()]}


def source(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c in value for c in '\x00\r\n'):
        raise ValueError('音频路径无效')
    p = Path(value.strip().strip('\"“”'))
    if not p.is_absolute() or p.suffix.lower() not in {'.wav', '.flac', '.aif', '.aiff'} or not p.is_file():
        raise ValueError('请选择本机已有的 WAV / FLAC / AIFF 人声文件')
    return p.resolve()


def hidden():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def inspect(body):
    p = source(body.get('path'))
    result = subprocess.run([settings.executable('ffprobe'), '-v', 'error', '-show_entries',
                             'format=duration:stream=codec_type,sample_rate,channels', '-of', 'json', str(p)],
                            capture_output=True, timeout=20, check=True, **hidden())
    data = json.loads(result.stdout)
    seconds = float(data.get('format', {}).get('duration', 0))
    stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'audio'), None)
    if not stream or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('文件中没有可读取的音频时长')
    return {'path': str(p), 'name': p.name, 'duration': seconds,
            'sampleRate': int(stream['sample_rate']), 'channels': stream['channels']}


def number(value, low, high):
    if isinstance(value, bool):
        raise ValueError('数值无效')
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'数值必须在 {low:g}–{high:g} 之间')
    return value


def enqueue(body):
    info = inspect(body)
    kind = body.get('plugin')
    if kind not in PLUGINS or plugin_path(kind) is None:
        raise ValueError('未找到对应 FabFilter VST3 插件，请先在本机安装并授权')
    if not status()['engine']:
        raise ValueError('未安装本机试听引擎，请运行 tools/InstallNativeAudio.ps1')
    start = number(body.get('start'), 0, info['duration'])
    end = number(body.get('end'), start + .25, min(info['duration'], start + 30))
    tail = number(body.get('tail', 4), 0, 8)
    values = body.get('values', {})
    if not isinstance(values, dict) or set(values) - {r[0] for r in CONTROLS[kind]}:
        raise ValueError('未知插件参数')
    values = {key: number(values.get(key, default), low, high)
              for key, _, low, high, default, _, _ in CONTROLS[kind]}
    comparison = body.get('comparison', 'dry')
    if comparison not in ['dry', 'tail', 'feedback'] or (comparison == 'tail' and kind != 'reverb') or (comparison == 'feedback' and kind != 'delay'):
        raise ValueError('对比方式与插件不匹配')
    shape = body.get('shape', 'Bell')
    if shape not in ['Bell', 'High Shelf']:
        raise ValueError('EQ 形状无效')
    spec = {**info, 'start': start, 'end': end, 'tail': tail, 'plugin': kind,
            'pluginPath': str(plugin_path(kind)), 'values': values, 'shape': shape,
            'comparison': comparison, 'ffmpeg': settings.executable('ffmpeg')}
    return submit(spec)


def submit(spec, prepare=None):
    with lifecycle.operation('提交试听任务'):
        return _submit(spec, prepare)


def _submit(spec, prepare=None):
    with LOCK:
        if sum(j['status'] in ['queued', 'running'] for j in JOBS.values()) >= 3:
            raise ValueError('已有试听任务正在渲染，请稍候')
        # Retain only recent in-memory job records; files remain private until cleared explicitly.
        for key in list(JOBS):
            if JOBS[key]['status'] not in ['queued', 'running'] and time.time() - JOBS[key]['created'] > 86400:
                del JOBS[key]
        jid = uuid.uuid4().hex
        folder = CACHE / jid
        folder.mkdir(parents=True)
        if prepare:
            prepare(folder)
        (folder / 'request.json').write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
        JOBS[jid] = {'id': jid, 'status': 'queued', 'created': time.time()}
        POOL.submit(render, jid, folder)
        return dict(JOBS[jid])


def render(jid, folder):
    with lifecycle.operation('试听任务'):
        return _render(jid, folder)


def _render(jid, folder):
    with LOCK:
        JOBS[jid]['status'] = 'running'
    try:
        script = 'song_mix_worker.py' if spec_mode(folder).startswith('song') else 'native_audio_worker.py'
        result = subprocess.run([sys.executable, str(ROOT / ('app/' + script)), str(folder)],
                                capture_output=True, timeout=240, **hidden())
        (folder / 'worker.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            if (folder / 'error.json').is_file():
                raise ValueError(json.loads((folder / 'error.json').read_text(encoding='utf-8'))['error'])
            raise ValueError('FabFilter 渲染失败；请检查插件授权。详细信息保留在本机 worker.log。')
        data = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        with LOCK:
            urls = {'a': f'/mix-audio/{jid}/a.wav', 'b': f'/mix-audio/{jid}/b.wav'} if 'duration' in data else {}
            JOBS[jid].update(status='ready', result={**data, **urls})
    except Exception as error:
        with LOCK:
            JOBS[jid].update(status='error', error='插件渲染超时，工作台仍可使用。' if isinstance(error, subprocess.TimeoutExpired) else str(error))


def job(jid):
    with LOCK:
        if jid not in JOBS:
            raise ValueError('试听任务不存在，请重新生成')
        return dict(JOBS[jid])


def spec_mode(folder):
    return json.loads((folder / 'request.json').read_text(encoding='utf-8')).get('mode', 'single')


def media(jid, name):
    if not re.fullmatch('[a-f0-9]{32}', jid) or name not in {'a.wav', 'b.wav'} or job(jid)['status'] != 'ready':
        raise ValueError('试听文件无效')
    return CACHE / jid / name
