"""Managed copies, native dependency relocation and atomic registration, synthetic only."""
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
import json
import re
import struct
import sys
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
from core import read_json, save_json, sha
import asset_storage
import project_assets as assets
import projects
import workspaces
import daw


def rejects(fn, message):
    try:
        fn()
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError('Expected rejection: ' + message)


def preset(state):
    payload = json.dumps(state).encode() + b'\x00tail'
    header = b'VST3' + struct.pack('<I', 1) + next(iter(asset_storage.SV_IDS))
    return header + struct.pack('<Q', 48 + len(payload)) + payload + b'List' + struct.pack('<I', 1) + struct.pack('<4sQQ', b'Comp', 48, len(payload))


def main():
    with tempfile.TemporaryDirectory(prefix='managed assets ') as td:
        root = Path(td)
        assets.ROOT = workspaces.ROOT = projects.ROOT = root
        assets.STORE = root / 'config/project-assets.local.json'
        save_json(root / 'config/projects.json', [])
        source = root / 'outside'
        source.mkdir()
        wav = source / 'voice.wav'; wav.write_bytes(b'synthetic audio')
        svp = source / 'finished.svp'
        doc = {'version': 196, 'time': {'tempo': [{'position': 0, 'bpm': 130}]}, 'tracks': [
            {'name': 'Lead', 'mainGroup': {'notes': [{'onset': 0, 'duration': 705600000, 'pitch': 65, 'lyrics': 'la'}]},
             'mainRef': {'database': {'name': 'Licensed Voice'}, 'voice': {'tension': .3}}},
            {'name': 'Reference', 'mainRef': {'isInstrumental': True, 'audio': {'filename': 'voice.wav', 'duration': 5}}}]}
        save_json(svp, doc)
        baseline = {svp: sha(svp), wav: sha(wav)}
        with patch.object(projects, 'media_info', return_value=dict(duration=5, rate=48000, channels=1, bits=24)):
            p = projects.create({'svp': str(svp), 'title': 'Demo Song', 'folderName': 'Artist - Song', 'lead': str(wav)})
        ident = p['id']; workspace = Path(p['pilot'])
        state = assets.status(ident)
        assert state['assets']['svp']['path'] == p['working'] and state['assets']['svp']['managed']
        assert Path(state['assets']['lead']['path']).is_relative_to(workspace)
        imported = read_json(p['working'])
        assert imported['tracks'][0] == doc['tracks'][0], 'Voice/note settings changed'
        assert Path(imported['tracks'][1]['mainRef']['audio']['filename']).is_relative_to(workspace)
        assert read_json(p['snapshot']) == doc, 'Source snapshot changed'

        def save(fields, mode='copy', revision=None):
            return assets.save(ident, {'revision': assets.status(ident)['revision'] if revision is None else revision,
                                       'assets': fields, 'storageMode': mode})
        copied = save({'mix': '"' + str(wav) + '"', 'accompaniment': str(wav)})
        mix = Path(copied['assets']['mix']['path'])
        assert mix == workspace / 'exports/audio/Final Mix.wav' and sha(mix) == sha(wav)
        assert copied['assets']['accompaniment']['managed']
        assert save({'mix': str(wav)})['assets']['mix']['path'] == str(mix), 'Duplicate copy created'
        assert save({'mix': str(mix)})['storage']['reused'] == 1
        wav.write_bytes(b'new completed export')
        second = Path(save({'mix': str(wav)})['assets']['mix']['path'])
        assert second.name == 'Final Mix_v2.wav' and mix.read_bytes() == b'synthetic audio'
        explicit = save({'mix': str(wav)}, 'reference')
        assert explicit['assets']['mix']['path'] == str(wav) and not explicit['assets']['mix']['managed']
        state = save({'svp': str(svp)})
        sv_copy = Path(state['assets']['svp']['path'])
        assert 'sv2' in sv_copy.parts and sv_copy != Path(p['working'])
        assert save({'svp': str(svp)})['assets']['svp']['path'] == str(sv_copy)
        # A source dependency change invalidates the cached native bundle.
        wav.write_bytes(b'updated reference recording')
        assert save({'svp': str(svp)})['assets']['svp']['path'] != str(sv_copy)
        baseline[wav] = sha(wav)
        # Being located inside the workspace does not make external references safe.
        loose = workspace / 'working/sv/loose.svp'
        loose_doc = json.loads(json.dumps(doc))
        loose_doc['tracks'][1]['mainRef']['audio']['filename'] = str(wav)
        save_json(loose, loose_doc)
        loose_before = sha(loose)
        fixed = Path(save({'svp': str(loose)})['assets']['svp']['path'])
        assert fixed != loose and sha(loose) == loose_before
        assert save({'svp': str(fixed)})['assets']['svp']['path'] == str(fixed)

        song = source / 'mix.song'
        host_state = {'projectPath': str(svp), 'araBridgeEnabled': True, 'sessionConfiguration': {'channelLayout': 12}, 'other': 42}
        fx = b'opaque effect state remains exact'
        with zipfile.ZipFile(song, 'w') as archive:
            archive.writestr('Song/mediapool.xml', '<Pool><Url url="' + wav.as_uri() + '"/><Url url="media:///inside.wav"/><Url url="media:///external.wav"/></Pool>')
            archive.writestr('settings.xml', '<Settings><Url url="' + (source / 'Mixdown').as_uri() + '/"/></Settings>')
            archive.writestr('SV.vstpreset', preset(host_state))
            archive.writestr('Fx.vstpreset', fx)
            archive.writestr('inside.wav', b'embedded audio')
        (source / 'Media').mkdir()
        (source / 'Media/external.wav').write_bytes(b'relative external media')
        baseline[song] = sha(song)
        built = Path(save({'song': str(song)})['assets']['song']['path'])
        with zipfile.ZipFile(built) as archive:
            assert archive.read('Fx.vstpreset') == fx
            assert archive.read('inside.wav') == b'embedded audio'
            refs = daw.xml(archive.read('Song/mediapool.xml'))
            for node in list(refs)[::2]:
                path = re.sub(r'^/([A-Za-z]:)', r'\1', unquote(urlsplit(node.get('url')).path))
                assert Path(path).is_relative_to(workspace)
            state_bytes = next(chunk for tag, chunk in daw.chunks(archive.read('SV.vstpreset')) if tag == b'Comp')
            host, end = json.JSONDecoder().raw_decode(state_bytes.decode())
            assert state_bytes[end:] == b'\x00tail'
            target = Path(host.pop('projectPath'))
            original = dict(host_state); original.pop('projectPath')
            assert host == original, 'SV plugin settings changed during relocation'
            assert target.is_file() and target.is_relative_to(workspace)
            assert Path(read_json(target)['tracks'][1]['mainRef']['audio']['filename']).is_relative_to(workspace)
        assert save({'song': str(song)})['assets']['song']['path'] == str(built), 'Song bundle duplicated'
        assert save({'song': str(built)})['assets']['song']['path'] == str(built), 'Self-contained Song was recopied'

        # Reject stale/invalid updates before creating copies; dependency failure rolls back every copied role.
        before = assets.document()
        listing = {f for f in workspace.rglob('*') if f.is_file()}
        rejects(lambda: save({'mix': str(wav)}, revision=-1), '其他窗口')
        rejects(lambda: save({'mix': str(wav)}, 'invalid'), '复制到项目')
        missing = source / 'missing.svp'
        save_json(missing, {**doc, 'tracks': [{'mainRef': {'audio': {'filename': 'absent.wav'}}}]})
        wav.write_bytes(b'material for rollback')
        rejects(lambda: save({'mix': str(wav), 'svp': str(missing)}), '参考音频缺失')
        assert assets.document() == before
        assert {f for f in workspace.rglob('*') if f.is_file()} == listing
        bad_song = source / 'missing.song'
        with zipfile.ZipFile(bad_song, 'w') as archive:
            archive.writestr('Song/mediapool.xml', '<Pool><Url url="' + (source / 'absent.wav').as_uri() + '"/></Pool>')
        rejects(lambda: save({'song': str(bad_song)}), 'Song 依赖缺失')
        assert assets.document() == before
        assert {f for f in workspace.rglob('*') if f.is_file()} == listing
        with patch.object(assets, 'save_json', side_effect=OSError('synthetic disk failure')):
            try:
                save({'mix': str(wav)})
            except OSError:
                pass
            else:
                raise AssertionError('Registry failure was ignored')
        assert assets.document() == before
        assert {f for f in workspace.rglob('*') if f.is_file()} == listing
        baseline[wav] = sha(wav)
        assert all(sha(file) == digest for file, digest in baseline.items())
        assert not any('song-' in folder.name for folder in workspace.rglob('*') if folder.is_dir())
        # Legacy adoption previews the new root without moving any existing project.
        legacy = {'id': 'legacy', 'title': 'Legacy Song', 'pilot': str(root / 'old pilot'), 'audio': {'mix': {'original': str(wav)}}}
        save_json(root / 'data/projects/legacy.json', {'project': legacy})
        save_json(root / 'config/projects.json', read_json(root / 'config/projects.json') + [{'id': 'legacy', 'title': 'Legacy Song'}])
        preview = assets.status('legacy')
        assert preview['copyWorkspace'] == str(root / 'projects/Legacy Song')
        assert not Path(preview['copyWorkspace']).exists()
        moved = assets.save('legacy', {'revision': preview['revision'], 'assets': {'mix': str(wav)}})
        assert moved['workspace'] == preview['copyWorkspace'] and moved['assets']['mix']['managed']
        assert sha(wav) == baseline[wav]
    print('PASS: managed imports, native SV audio/Song dependencies, exact voice/plugin settings, reference mode, deduplication/versioning, stale guards, copy/registration rollback and source preservation')


if __name__ == '__main__':
    main()
