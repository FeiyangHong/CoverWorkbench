"""Per-installation settings; never require the author's drives or runtime."""
from pathlib import Path
import importlib.util
import json
import os
import shutil
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'config/settings.local.json'
LOCK = threading.RLock()
DEFAULTS = {
    'ffmpeg': '', 'ffprobe': '', 'studioOne': '',
    'songsDirectory': str(Path.home() / 'Documents/Studio One/Songs'),
    'lyricCache': str(Path(os.environ.get('APPDATA', str(Path.home() / '.config'))) / 'MusicLyricApp/cache'),
    'msstUrl': 'http://127.0.0.1:7860', 'msstLauncher': '', 'msstDirectory': '', 'msstPython': '',
}


def initialize():
    for folder in ['config', 'logs', 'runtime', 'data/projects', 'projects', 'reports']:
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    index = ROOT / 'config/projects.json'
    try:
        with index.open('x', encoding='utf-8') as stream:
            stream.write('[]\n')
    except FileExistsError:
        pass


def load():
    with LOCK:
        local = json.loads(FILE.read_text(encoding='utf-8-sig')) if FILE.exists() else {}
        return {**DEFAULTS, **local}


def save(body):
    if not isinstance(body, dict) or set(body) - set(DEFAULTS):
        raise ValueError('Unknown settings fields')
    values = {}
    for key, value in body.items():
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError('Invalid settings value')
        value = value.strip().strip('"“”')
        if any(c in value for c in '\x00\r\n'):
            raise ValueError('Paths must not contain control characters')
        if key == 'msstUrl':
            from separation import local_url
            values[key] = local_url(value)
            continue
        if key in ['msstLauncher', 'msstDirectory', 'msstPython'] and value.startswith(('\\\\', '//')):
            raise ValueError('请选择本机已安装的 MSST 启动程序')
        if value and not Path(value).is_absolute():
            raise ValueError('Use an absolute path, or leave the field empty for automatic detection')
        if value and key in ['ffmpeg', 'ffprobe', 'studioOne', 'msstPython']:
            if not Path(value).is_file() or (os.name == 'nt' and Path(value).suffix.lower() != '.exe'):
                raise ValueError('Select an existing executable: ' + key)
        if value and key == 'msstLauncher' and (not Path(value).is_file() or Path(value).suffix.lower() not in {'.exe', '.lnk'}):
            raise ValueError('请选择已安装 MSST 的 .exe 或桌面 .lnk 快捷方式')
        if value and key == 'msstDirectory' and not Path(value).is_dir():
            raise ValueError('请选择 MSST 安装目录')
        values[key] = value
    with LOCK:
        result = {**load(), **values}
        FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = FILE.with_suffix('.tmp')
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(FILE)
    return status()


def executable(name, required=True):
    configured = load().get(name, '')
    found = configured or shutil.which(name) or ''
    if not found and name == 'studioOne' and os.name == 'nt':
        base = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PreSonus'
        found = next((str(p) for p in sorted(base.glob('Studio One */Studio One.exe'), reverse=True)), '')
    if found and Path(found).is_file():
        return str(Path(found).resolve())
    if required:
        raise ValueError(f'{name} is not configured. Open Environment settings / 环境设置.')
    return ''


def status():
    return {'settings': load(), 'root': str(ROOT), 'python': sys.version.split()[0],
            'platform': sys.platform, 'tools': {k: executable(k, False) for k in ['ffmpeg', 'ffprobe', 'studioOne']},
            'romajiAvailable': importlib.util.find_spec('pykakasi') is not None}
