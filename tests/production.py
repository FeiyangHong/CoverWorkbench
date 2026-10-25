"""Native handoffs and MSST boundaries, with disposable files and a local fake server."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import json
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import project_assets as assets
import separation
import settings
import video_links
from core import save_json, sha


def rejects(fn, text):
    try:
        fn()
    except ValueError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError('Expected rejection: ' + text)


def main():
    with tempfile.TemporaryDirectory(prefix='production handoffs ') as tmp:
        root = Path(tmp)
        assets.ROOT = video_links.ROOT = root
        assets.STORE = root / 'config/project-assets.local.json'
        video_links.STORE = root / 'config/video-links.local.json'
        settings.FILE = root / 'config/settings.local.json'
        paths = {name: root / name for name in ['project.svp', 'session.song', 'lead.wav', 'backing.wav', 'final.wav', 'new.wav']}
        for p in paths.values():
            p.write_bytes(b'synthetic fixture')
        hashes = {p: sha(p) for p in paths.values()}
        project = dict(id='demo', title='Demo', pilot=str(root / 'pilot'), working=str(root / 'copy.svp'),
                       files=[{'original': str(paths['project.svp'])}], audio={'mix': {'original': str(paths['final.wav'])}})
        save_json(root / 'config/projects.json', [{'id': 'demo', 'title': 'Demo'}])
        save_json(root / 'data/projects/demo.json', {'project': project})
        save_json(root / 'projects/studio-one/exact/build.json', dict(svp=str(paths['project.svp']), song=str(paths['session.song']), sourceAudio=str(paths['backing.wav']), createdAt=1))
        save_json(root / 'projects/studio-one/wrong/build.json', dict(svp=str(root / 'other.svp'), song=str(root / 'wrong.song'), createdAt=2))
        state = assets.status('demo')
        assert state['assets']['svp']['path'] == str(paths['project.svp'])
        assert state['assets']['song']['path'] == str(paths['session.song'])
        assert state['assets']['accompaniment']['path'] == str(paths['backing.wav'])
        state = assets.save('demo', {'revision': 0, 'storageMode': 'reference', 'assets': {'mix': '"' + str(paths['new.wav']) + '"', 'lead': str(paths['lead.wav'])}})
        assert state['assets']['lead']['exists'] and state['assets']['mix']['custom']
        assert video_links.materials('demo')['audio']['path'] == str(paths['new.wav']), 'Project mix was not handed off to video sources'
        rejects(lambda: assets.save('demo', {'revision': 0, 'assets': {'mix': str(paths['final.wav'])}}), '其他窗口更新')
        rejects(lambda: assets.save('demo', {'revision': 1, 'assets': {'svp': str(paths['final.wav'])}}), '本地文件')
        rejects(lambda: assets.save('demo', {'revision': 1, 'assets': {'executable': 'anything'}}), '未知')
        rejects(lambda: assets.open_asset('demo', {'asset': 'lead', 'action': 'open'}), '仅支持')
        with patch.object(assets.daw, 'open_local', return_value={'opened': True}) as opened:
            assets.open_asset('demo', {'asset': 'song', 'action': 'open'})
            assert opened.call_args.args[0] == {'path': str(paths['session.song']), 'action': 'song'}
        assets.save('demo', {'revision': 1, 'assets': {'mix': ''}})
        assert assets.status('demo')['assets']['mix']['path'] == str(paths['final.wav'])
        assert assets.STORE.with_name('project-assets.local.previous.json').exists()
        assert all(sha(p) == h for p, h in hashes.items())
        rejects(lambda: assets.status('../unknown'), '导入')
        for bad in ['https://127.0.0.1:7860', 'http://example.com', 'http://0.0.0.0', 'http://127.0.0.1@evil.test', 'http://user:pass@localhost', 'http://127.0.0.1:99999', 'http://127.0.0.1/?token=a', 'http://127.0.0.1/\\evil']:
            rejects(lambda: separation.local_url(bad), '本机 HTTP')
        assert separation.local_url(' http://localhost:7860/ ') == 'http://localhost:7860'
        assert separation.local_url('http://[::1]:7860') == 'http://[::1]:7860'
        class Handler(BaseHTTPRequestHandler):
            mode = 'msst'
            def log_message(self, *_):
                pass
            def do_GET(self):
                if self.mode == 'redirect':
                    self.send_response(302); self.send_header('Location', 'http://example.com'); self.end_headers(); return
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps({'title': 'MSST-WebUI' if self.mode == 'msst' else 'Other app'}).encode())
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        try:
            url = 'http://127.0.0.1:' + str(httpd.server_port)
            settings.save({'msstUrl': url})
            assert separation.status()['ready']
            Handler.mode = 'other'
            assert separation.status()['reachable'] and not separation.status()['ready']
            rejects(separation.launch, '其他服务')
            Handler.mode = 'redirect'
            assert not separation.probe(url)['ready'], 'Redirects must not be followed outside localhost'
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()
        launcher = root / 'MSST test.exe'; launcher.write_bytes(b'not executed')
        settings.save({'msstLauncher': str(launcher)})
        with patch.object(separation, 'probe', return_value={'ready': False, 'reachable': False, 'message': 'offline'}), patch.object(separation.subprocess, 'Popen') as start:
            separation.ROOT = root
            first = separation.launch()
            assert first['starting'] and start.call_count == 1
            assert start.call_args.args[0] == [str(launcher)]
            separation.launch()
            assert start.call_count == 1, 'Repeated launch started duplicate processes'
        rejects(lambda: settings.save({'msstUrl': 'http://external.test'}), '本机 HTTP')
    print('PASS: exact-file DAW association, explicit assets, stale guards, original hashes, video mix handoff, local-only MSST probes, identity/redirect checks and duplicate launch protection')


if __name__ == '__main__':
    main()
