"""Capture documentation using an isolated checkout and synthetic notes only."""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = subprocess.check_output(
        ['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=ROOT
    ).decode().strip('\0').split('\0')
    (ROOT / 'work').mkdir(exist_ok=True)
    output = ROOT / 'docs/images'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='readme-demo-', dir=ROOT / 'work') as td:
        dest = Path(td).resolve()
        assert dest.is_relative_to((ROOT / 'work').resolve())
        for name in set(paths):
            source = ROOT / name
            if source.is_file():
                target = dest / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
        subprocess.run([sys.executable, '-I', str(dest / 'tools/setup.py')], check=True,
                       stdout=subprocess.DEVNULL)
        tracks = []
        for index, name in enumerate(['Lead A', 'Lead B', 'Harmony']):
            tracks.append({'name': name, 'dispOrder': index, 'mainRef': {}, 'groups': [],
                           'mainGroup': {'uuid': f'demo-{index}', 'notes': [
                               {'onset': beat * 705600000, 'duration': 564480000,
                                'pitch': 60 + [0, 2, 4, 7, 4, 2, 0, 0][beat % 8] - index * 3,
                                'lyrics': 'la'} for beat in range(32)]}})
        source = dest / 'demo.svp'
        source.write_text(json.dumps({'version': 147,
                                     'time': {'tempo': [{'position': 0, 'bpm': 120}]},
                                     'tracks': tracks}), encoding='utf-8')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'COVERWORKBENCH_PORT': str(port), 'PYTHONNOUSERSITE': '1'}
        launch = 'import sys,runpy;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2],run_name="__main__")'
        with (dest / 'logs/readme.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-I', '-c', launch,
                                        str(dest / 'app'), str(dest / 'app/server.py')],
                                       env=env, stdout=log, stderr=log)
            base = f'http://127.0.0.1:{port}'

            def request(path, body=None):
                data = None if body is None else json.dumps(body).encode()
                req = urllib.request.Request(base + path, data=data,
                                             headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    return json.load(response)

            try:
                for _ in range(100):
                    try:
                        health = request('/api/health')
                        break
                    except OSError:
                        if process.poll() is not None:
                            raise RuntimeError('Demo server failed to start')
                        time.sleep(.1)
                else:
                    raise RuntimeError('Demo server timed out')
                assert Path(health['root']) == dest
                assert request('/api/projects') == []
                assert {t['id'] for t in request('/api/daw/status')['templates']} == {'studio-vocal-plate', 'studio-vocal-delay'}
                request('/api/project-import/new', {'svp': str(source), 'title': 'Moonlit Demo',
                                                   'artist': 'Synthetic example', 'language': 'en'})
                subprocess.run(['node', str(ROOT / 'tools/capture_readme.cjs'), base, str(output)],
                               cwd=ROOT, check=True)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    main()
