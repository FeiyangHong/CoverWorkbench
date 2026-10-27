"""Unicode names and Windows safety rules with disposable creative records only."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from core import read_json, save_json, sha
from windows_names import component, generated
import projects
import project_assets
import workspaces
import video_project as video
import video_links


def rejects(value):
    try:
        component(value)
    except ValueError:
        return
    raise AssertionError('Accepted an illegal Windows component: ' + repr(value))


def main():
    for value in ['合成歌手 - テスト曲', '测试 名称', 'カバー 作品', '123', '曲名（版本二）',
                  '音乐 #1 100%', "歌手's 歌曲", 'A+B, 歌曲; =版本', ' leading space', '歌' * 100, '🎵 テスト']:
        assert component(value) == value
    for value in ['', ' ', '.', '..', '../escape', '..\\escape', 'bad/name', 'bad\\name',
                  'bad:name', 'bad?name', 'bad*name', 'bad|name', 'bad"name', '<name>', 'bad\x00name',
                  'bad\x1fname', 'bad\nname', 'trailing.', 'trailing ', 'CON', 'nul.wav', 'com1',
                  'LPT9.txt', 'COM¹.wav', 'LPT²', 'CON .txt', 'CONIN$', 'conout$.txt', '歌' * 256, '🎵' * 128]:
        rejects(value)
    assert component('歌' * 255) == '歌' * 255
    assert component('🎵' * 127 + '歌') == '🎵' * 127 + '歌'
    output = generated('🎵' * 127, ' - v001.mp4')
    assert len(output.encode('utf-16-le')) <= 510 and output.endswith(' - v001.mp4')
    with tempfile.TemporaryDirectory(prefix='unicode naming ') as td:
        root = Path(td)
        projects.ROOT = project_assets.ROOT = workspaces.ROOT = video_links.ROOT = root
        project_assets.STORE = root / 'config/project-assets.local.json'
        video_links.STORE = root / 'config/video-links.local.json'
        video.BASE = root / 'projects/video'
        save_json(root / 'config/projects.json', [])
        p = projects.create({'title': '测试 テスト曲', 'artist': '合成歌手', 'language': 'ja'})
        workspace = Path(p['pilot'])
        assert workspace.name == '合成歌手 - 测试 テスト曲'
        assert project_assets.status(p['id'])['workspace'] == str(workspace)
        protected = {f: sha(f) for f in workspace.rglob('*') if f.is_file()}
        record = sha(root / 'data/projects' / (p['id'] + '.json'))
        duplicate = projects.create({'title': p['title'], 'artist': p['artist']})
        assert Path(duplicate['pilot']).name == workspace.name + '_v2'
        assert workspaces.allocate(p, 'Do Not Rename') == workspace
        assert sha(root / 'data/projects' / (p['id'] + '.json')) == record
        assert all(sha(f) == h for f, h in protected.items())
        assert video_links.overview(p['id'])['defaultName'] == p['title'] + ' Video'
        name = '合成视频 - テスト #1 100%'
        first = video.create({'name': name})
        original = sha(video.folder(first['id']) / 'project.json')
        second = video.create({'name': name})
        assert first['id'] == name and second['id'] == name + '_v2'
        assert video.load(first['id'])['name'] == name
        assert sha(video.folder(first['id']) / 'project.json') == original
        assert {p['id'] for p in video.listing()} == {first['id'], second['id']}
        before = {p.name for p in (root / 'projects').iterdir()}
        try:
            projects.create({'title': 'Invalid synthetic', 'folderName': '../escape'})
        except ValueError:
            pass
        else:
            raise AssertionError('Traversal created a project')
        assert {p.name for p in (root / 'projects').iterdir()} == before
    print('PASS: Chinese/Japanese/spaces, legal punctuation, Windows device/control/traversal rules, UTF-16 bounds, readable defaults, non-destructive version allocation and unchanged existing projects')


if __name__ == '__main__':
    main()
