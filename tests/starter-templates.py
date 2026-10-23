"""Exercise public starter mixes with synthetic media and no native applications."""
from pathlib import Path
from unittest.mock import patch
import io
import json
import sys
import tempfile
import wave
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import daw
import mix_bundle
import starter_templates


def main():
    entries = starter_templates.entries()
    assert {row['id'] for row in entries} == {'studio-vocal-plate', 'studio-vocal-delay'}
    for row in entries:
        raw = (starter_templates.ASSETS / row['bundle']).read_bytes()
        mix_bundle.validate(raw, row)
        # Reject accidental media attachments, even when they are tiny or synthetic.
        buffer = io.BytesIO(raw)
        with zipfile.ZipFile(buffer, 'a') as archive:
            archive.writestr('Media/unexpected.wav', b'RIFF')
        try:
            mix_bundle.validate(buffer.getvalue())
        except ValueError:
            pass
        else:
            raise AssertionError('Mix validator accepted a media attachment')
    (ROOT / 'work').mkdir(exist_ok=True)
    builds = 0
    with tempfile.TemporaryDirectory(prefix='starter & mixes ', dir=ROOT / 'work') as td:
        folder = Path(td).resolve()
        audio = folder / 'synthetic.wav'
        with wave.open(str(audio), 'wb') as stream:
            stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            stream.writeframes(b'\0' * 48000 * 4)
        # Isolate DAW indexes and template materialization from personal runtime data.
        with patch.object(starter_templates, 'ROOT', folder), patch.object(daw, 'BUILD_INDEX', folder / 'build-index.json'), \
             patch.object(daw, 'BASE', folder / 'builds'), patch.object(daw, 'media_info', return_value={
                 'duration': 1, 'rate': 48000, 'frames': 48000, 'channels': 2, 'bits': 16, 'float': False}):
            for row in entries:
                d = daw.template(row['id'])
                daw.validate_template(d['originalSong'])
                assert Path(d['originalSong']).is_relative_to(folder)
                with zipfile.ZipFile(d['originalSong']) as archive:
                    expected = {name: archive.read(name) for name in archive.namelist()
                                if name.startswith('Presets/Effects/')}
                for names in [['Lead A'], ['Lead A', 'Lead B', 'Harmony']]:
                    source = folder / 'input.svp'
                    raw = {'version': 147, 'time': {'tempo': [{'position': 0, 'bpm': 120}]}, 'tracks': [
                        {'name': name, 'dispOrder': index, 'mainRef': {}, 'groups': [],
                         'mainGroup': {'uuid': f'group-{index}', 'notes': [
                             {'onset': 0, 'duration': 705600000, 'pitch': 60, 'lyrics': 'la'}]}}
                        for index, name in enumerate(names)]}
                    source.write_text(json.dumps(raw), encoding='utf-8')
                    source_hash = daw.sha(source)
                    preview = daw.inspect({'svp': str(source)})
                    result = daw.build({'svp': str(source), 'engine': 'sv1', 'sourceSHA256': source_hash,
                        'tracks': [{'index': track['index'], 'role': track['role']} for track in preview['tracks']],
                        'name': row['id'] + '-' + str(len(names)), 'template': row['id'],
                        'accompaniment': str(audio), 'outputDir': str(folder / 'builds')})
                    assert len(result['mapping']) == len(names)
                    assert daw.sha(source) == source_hash
                    with zipfile.ZipFile(result['song']) as archive:
                        for name, value in expected.items():
                            assert archive.read(name) == value, 'Effect preset changed during generation'
                        for name in archive.namelist():
                            if not name.endswith('.xml'):
                                continue
                            doc = daw.xml(archive.read(name))
                            for node in doc.iter():
                                url = node.get('url', '')
                                if url.startswith('file:///'):
                                    target = daw.external(url).resolve()
                                    assert target.is_relative_to(Path(result['folder']).resolve()), url
                                    assert target.exists(), url
                        synth = next(name for name in archive.namelist() if name.startswith('Presets/Synths/'))
                        state, _ = json.JSONDecoder().raw_decode(dict(daw.chunks(archive.read(synth)))[b'Comp'].decode())
                        assert state['projectPath'] == result['svp']
                    builds += 1
    print(f'PASS: 2 audited starter bundles, media rejection, {builds} relocated Song builds, '
          'lead-only/multiple-lead/harmony mapping, unchanged sources/effects, local references')


if __name__ == '__main__':
    main()
