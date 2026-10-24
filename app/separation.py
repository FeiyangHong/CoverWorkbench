"""Optional MSST service boundary: local launch, identity probe and browser handoff."""
from pathlib import Path
from urllib.parse import urlsplit
import http.client
import json
import os
import subprocess
import threading
import time

from core import ROOT
import settings

LOCK = threading.RLock()
LAST_LAUNCH = 0


def local_url(value):
    value = value.strip().rstrip('/')
    try:
        u = urlsplit(value)
        valid = (u.scheme == 'http' and u.hostname in {'127.0.0.1', 'localhost', '::1'}
                 and not u.username and not u.password and not u.query and not u.fragment
                 and (u.port is None or 1 <= u.port <= 65535))
    except ValueError:
        valid = False
    if not valid or any(c in value for c in '\x00\r\n\\'):
        raise ValueError('MSST 地址请使用本机 HTTP 地址，例如 http://127.0.0.1:7860')
    return value


def probe(url):
    u = urlsplit(local_url(url))
    connection = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=1.5)
    try:
        connection.request('GET', (u.path.rstrip('/') or '') + '/config')
        response = connection.getresponse()
        raw = response.read(1_000_001)
        if response.status != 200 or len(raw) > 1_000_000:
            return {'reachable': True, 'ready': False, 'message': '地址可访问，但未识别到 MSST；请确认端口或先在新标签页检查'}
        config = json.loads(raw)
        text = json.dumps(config, ensure_ascii=False).lower()
        recognized = any(s in text for s in ['msst', 'music source separation', 'big_beta', 'roformer'])
        return {'reachable': True, 'ready': recognized, 'message': 'MSST 已就绪' if recognized else '检测到其他网页，请确认 MSST 地址'}
    except (OSError, ValueError, http.client.HTTPException):
        return {'reachable': False, 'ready': False, 'message': 'MSST 尚未启动或地址不可用'}
    finally:
        connection.close()


def status():
    config = settings.load()
    url = local_url(config['msstUrl'])
    launcher = Path(config['msstLauncher']) if config['msstLauncher'] else None
    result = probe(url)
    return {**result, 'url': url, 'launcher': str(launcher) if launcher else '',
            'canLaunch': bool(launcher and launcher.is_file() and launcher.suffix.lower() in {'.exe', '.lnk'}),
            'starting': not result['ready'] and bool(LAST_LAUNCH and time.monotonic() - LAST_LAUNCH < 90)}


def launch():
    global LAST_LAUNCH
    with LOCK:
        state = status()
        if state['ready']:
            return state
        if state['reachable']:
            raise ValueError('这个地址已有其他服务，请先确认 MSST 地址，避免重复启动')
        if state['starting']:
            return state
        if os.name != 'nt' or not state['canLaunch']:
            raise ValueError('请在服务设置中选择已安装 MSST 的 Windows EXE 或桌面快捷方式')
        p = Path(state['launcher']).resolve()
        log = ROOT / 'logs/msst-launch.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('ab') as output:
            if p.suffix.lower() == '.lnk':
                script = 'Start-Process -FilePath $env:CW_MSST_LAUNCHER -WindowStyle Hidden'
                subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                 env={**os.environ, 'CW_MSST_LAUNCHER': str(p)},
                                 stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen([str(p)], cwd=str(p.parent), stdout=output, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        LAST_LAUNCH = time.monotonic()
        return {**state, 'starting': True, 'message': '已请求启动 MSST，请稍后检查连接'}
