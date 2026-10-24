"""Exercise a clean, relocated checkout with no personal data or model dependencies."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', action='store_true', help='Also run the Playwright UI flow (npm install first)')
    args = parser.parse_args()
    paths = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=ROOT).decode().strip('\0').split('\0')
    (ROOT / 'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='portable checkout ', dir=ROOT / 'work') as td:
        dest = Path(td).resolve()
        assert dest.is_relative_to((ROOT / 'work').resolve())
        for name in set(paths):
            source = ROOT / name
            if source.is_file():
                target = dest / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
        assert not (dest / 'config/projects.json').exists()
        assert not (dest / 'data/projects/hoshi.json').exists()
        assert not (dest / 'config/settings.local.json').exists()
        subprocess.run([sys.executable, '-I', str(dest / 'tools/setup.py')], check=True, stdout=subprocess.DEVNULL)
        assert json.loads((dest / 'config/projects.json').read_text()) == []
        source = dest / 'input.svp'
        source.write_text(json.dumps({'version': 147, 'time': {'tempo': [{'position': 0, 'bpm': 120}]}, 'tracks': [
            {'name': 'Lead', 'dispOrder': 0, 'mainRef': {}, 'mainGroup': {'uuid': 'test-group', 'notes': [
                {'onset': 0, 'duration': 705600000, 'pitch': 60, 'lyrics': 'la'}]}, 'groups': []}]}), encoding='utf-8')
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        (dest / 'input.lrc').write_text('[00:01.000]First line\n[00:04.000]Second line\n', encoding='utf-8')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = {**os.environ, 'COVERWORKBENCH_PORT': str(port), 'PYTHONNOUSERSITE': '1'}
        # -I avoids PYTHONPATH and user site; insert only this clean app path.
        launch = 'import sys,runpy;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2],run_name="__main__")'
        log = (dest / 'logs/test-server.log').open('w', encoding='utf-8')
        process = subprocess.Popen([sys.executable, '-I', '-c', launch, str(dest / 'app'), str(dest / 'app/server.py')], env=env, stdout=log, stderr=log)
        base = f'http://127.0.0.1:{port}'
        def request(path, body=None, headers=None):
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(base + path, data=data, headers=headers or ({'Content-Type': 'application/json'} if data else {}))
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.load(response)
        try:
            for _ in range(100):
                try:
                    health = request('/api/health'); break
                except OSError:
                    if process.poll() is not None: raise RuntimeError('Fresh server failed: ' + (dest / 'logs/test-server.log').read_text())
                    time.sleep(.1)
            else: raise AssertionError('Server timeout')
            assert Path(health['root']) == dest
            assert request('/api/projects') == []
            assert request('/api/video-status')['projects'] == []
            assert {t['id'] for t in request('/api/daw/status')['templates']} == {'studio-vocal-plate', 'studio-vocal-delay'}
            assert request('/api/settings')['settings']['ffmpeg'] == ''
            if args.browser:
                subprocess.run(['node', str(ROOT / 'tests/portable-ui.cjs'), base, str(source)], check=True, cwd=ROOT)
                rows = request('/api/projects'); assert len(rows) == 1
                ident = rows[0]['id']
            else:
                imported = request('/api/project-import/new', {'svp': '"' + str(source) + '"', 'title': 'My First Cover', 'language': 'en'})
                ident = imported['id']
            project = request('/api/project/' + ident)
            assert project['parsed']['notes'][0]['pitch'] == 60
            assert Path(project['project']['working']).is_relative_to(dest)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            # Optional Japanese package must not be required for English text import.
            package = request('/api/lyrics-build/' + ident, {'text': 'la la'})
            assert package['rows'][0]['original'] == 'la la'
            assert request('/api/workflow/' + ident)['jobs'] == []
            request('/api/settings/new', {'songsDirectory': str(dest / 'My Songs')})
            assert request('/api/daw/status')['outputOptions'][1]['path'] == str(dest / 'My Songs')
            # Cross-origin writes and invalid executables must be rejected.
            for body, headers, expected in [({}, {'Content-Type': 'application/json', 'Origin': 'https://example.com'}, 403),
                                            ({'ffmpeg': 'relative.exe'}, {'Content-Type': 'application/json'}, 400)]:
                try: request('/api/settings/new', body, headers)
                except urllib.error.HTTPError as error: assert error.code == expected
                else: raise AssertionError('Invalid request accepted')
            script_dest = dest / 'SV scripts'
            subprocess.run([sys.executable, str(dest / 'tools/install_sv_tools.py'), '--dest', str(script_dest)], check=True, stdout=subprocess.DEVNULL)
            assert len(list(script_dest.glob('*.lua'))) == 4
            for script in script_dest.glob('*.lua'):
                text = script.read_text(encoding='utf-8')
                assert '__CW_ROOT__' not in text
                assert dest.as_posix() in text
            # Exit is POST-only, instance-bound, and subject to the same origin checks.
            service = request('/api/lifecycle')
            for payload, headers, expected in [({'confirm': True, 'instance': service['instance']}, {'Content-Type': 'application/json', 'Origin': 'https://example.com'}, 403),
                                                ({'confirm': False, 'instance': service['instance']}, {'Content-Type': 'application/json'}, 400),
                                                ({'confirm': True, 'instance': 'stale'}, {'Content-Type': 'application/json'}, 409)]:
                try: request('/api/shutdown/local', payload, headers)
                except urllib.error.HTTPError as error: assert error.code == expected
                else: raise AssertionError('Invalid shutdown accepted')
            if args.browser:
                subprocess.run(['node', str(ROOT / 'tests/video-ui.cjs'), base], check=True, cwd=ROOT)
                subprocess.run(['node', str(ROOT / 'tests/video-timeline.cjs'), base], check=True, cwd=ROOT)
                subprocess.run(['node', str(ROOT / 'tests/video-undo.cjs'), base], check=True, cwd=ROOT)
                subprocess.run(['node', str(ROOT / 'tests/video-shell.cjs'), base], check=True, cwd=ROOT)
                subprocess.run(['node', str(ROOT / 'tests/music-video.cjs'), base], check=True, cwd=ROOT)
                subprocess.run(['node', str(ROOT / 'tests/production-ui.cjs'), base], check=True, cwd=ROOT)
                subprocess.run(['node', str(ROOT / 'tests/workspaces-ui.cjs'), base], check=True, cwd=ROOT)
                subprocess.run(['node', str(ROOT / 'tests/lifecycle-ui.cjs'), base], check=True, cwd=ROOT)
            else:
                assert request('/api/shutdown/local', {'confirm': True, 'instance': service['instance']})['state'] == 'stopping'
            assert process.wait(timeout=15) == 0, 'Web exit must terminate the actual server process'
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', port))
            print('PASS: clean process exit and released localhost port')
            print('PASS: clean relocated startup, import, lyrics, settings, optional dependencies, origin checks, SV script installation' + (', desktop/mobile browser flow' if args.browser else ''))
        finally:
            if process.poll() is None:process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
            log.close()


if __name__ == '__main__':
    main()
