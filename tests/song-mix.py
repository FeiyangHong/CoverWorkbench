"""Synthetic/static Song fixtures; optional licensed native-host integration."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct
import sys
import tempfile
import time
import wave
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import song_mix
import native_audio as host


def wait(job):
    deadline = time.monotonic() + 250
    while host.job(job['id'])['status'] in ['queued', 'running'] and time.monotonic() < deadline:
        time.sleep(.1)
    value = host.job(job['id'])
    assert value['status'] == 'ready', value
    return value['result']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--installed', action='store_true')
    args = parser.parse_args()
    (ROOT / 'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='song-mix-') as td:
        base = Path(td); song = base / 'Synthetic Mix.song'
        with zipfile.ZipFile(ROOT / 'assets/studio-one/studio-vocal-plate.cwmix') as archive:
            docs = {name: archive.read(name) for name in archive.namelist()}
        def fixture(values):
            with zipfile.ZipFile(song, 'w') as archive:
                for name, raw in values.items():
                    archive.writestr(name, raw)
        fixture(docs)
        graph = song_mix.read(str(song))
        assert len(graph['channels']) == 9 and len(graph['order']) == 9
        assert len(graph['targets']) == 7
        assert not [b for b in graph['blockers'] if not b.startswith('本机缺少 ')], graph['blockers']
        assert all(effect['preset'] is None for c in graph['channels'] for effect in c['inserts'])
        # Preserve both post- and pre-fader sends, and reject graph features we cannot restore.
        altered = dict(docs)
        altered['Devices/audiomixer.xml'] = docs['Devices/audiomixer.xml'].replace(b'pan="0.5"', b'pan="0.2"', 1)
        fixture(altered)
        assert any('声像' in b for b in song_mix.read(str(song))['blockers'])
        altered = dict(docs)
        altered['Song/song.xml'] = docs['Song/song.xml'].replace(b'</Song>', b'<AutomationRegion title="Test"><Url x:id="points" url="media:///missing.envelopex"/></AutomationRegion></Song>')
        fixture(altered)
        assert any('自动化' in b for b in song_mix.read(str(song))['blockers'])
        try:
            song_mix.enqueue({'song': str(song), 'songHash': graph['sha256'], 'target': graph['targets'][0]['id']}, True)
        except ValueError as error:
            assert '已改变' in str(error)
        else:
            raise AssertionError('Stale Song snapshot was accepted')
        fixture(docs)
        graph = song_mix.read(str(song))
        before = hashlib.sha256(song.read_bytes()).hexdigest()
        print('PASS: static routing/order, real preset metadata, unsupported pan/automation and stale-Song rejection')
        if not args.installed:
            print('SKIP: licensed plugin integration (--installed)')
            return
        assert not graph['blockers'], graph['blockers']
        import numpy as np
        import song_mix_worker as worker
        # Exact arithmetic oracle independent of plugin DSP: routing/faders/pre-send/bus.
        channels = []
        for cid, destination, gain in [(0, None, .8), (1, 3, .5), (2, 0, .2), (3, 0, .6), (4, 3, .4)]:
            channels.append({'id': cid, 'label': str(cid), 'destination': destination, 'gain': gain,
                             'mute': False, 'inputGainDB': 0, 'invert': [False, False], 'inserts': [], 'sends': []})
        channels[1]['sends'] = [{'to': 4, 'level': .1, 'pre': True, 'bypass': False}]
        tiny = {'channels': channels, 'order': [1, 2, 4, 3, 0], 'main': 0}
        signals = {1: np.full((2, 100), .1, np.float32), 2: np.full((2, 100), .2, np.float32)}
        spec = {'target': {'id': 'none', 'channel': 4}, 'enableTarget': False}
        out, _, _ = worker.render_graph(tiny, signals, spec, base)
        assert np.allclose(out, ((.1*.5 + .1*.1*.4)*.6 + .2*.2)*.8, atol=1e-8)
        channels[1]['sends'][0]['pre'] = False
        out, _, _ = worker.render_graph(tiny, signals, spec, base)
        assert np.allclose(out, ((.1*.5 + .1*.5*.1*.4)*.6 + .2*.2)*.8, atol=1e-8)
        voice, backing = base / 'voice.wav', base / 'backing.wav'
        for path, hz in [(voice, 220), (backing, 733)]:
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                stream.writeframes(b''.join(struct.pack('<h', round(math.sin(i/48000*2*math.pi*hz)*5000)) for i in range(48000*5)))
        target = next(t for t in graph['targets'] if t['kind'] == 'reverb')
        payload = {'song': str(song), 'songHash': graph['sha256'], 'target': target['id']}
        probe = wait(song_mix.enqueue(payload, True))
        assert probe['componentRestored'] and probe['baseline']['mix'] == '100%'
        lead = next(c for c in graph['channels'] if c['type'] == 'AudioSynthChannel')
        back = next(c for c in graph['channels'] if c['type'] == 'AudioTrackChannel')
        payload.update(start=1, end=2, tail=2, sources=[{'path': str(voice), 'channel': lead['id'], 'role': 'vocal'},
                                                      {'path': str(backing), 'channel': back['id'], 'role': 'backing'}],
                       changes={'space': 1.2})
        result = wait(song_mix.enqueue(payload))
        assert result['duration'] == 3 and result['differenceRms'] > .00001
        assert result['parametersB']['mix'] == result['parametersA']['mix'] == '100%'
        assert result['parametersB']['predelay'] == result['parametersA']['predelay']
        assert all(effect['componentRestored'] for effect in result['chainA'] + result['chainB'])
        assert len(result['chainA']) >= 5 and result['mappedChannels'] == [lead['id'], back['id']]
        for side in ['a', 'b']:
            path = host.media(result['a'].split('/')[2], side + '.wav')
            with wave.open(str(path), 'rb') as stream:
                assert stream.getnframes() == 48000 * 3
        assert hashlib.sha256(song.read_bytes()).hexdigest() == before
        print('PASS: routing arithmetic, exact preset-component restoration/controller sync, original-vs-edited full chain, backing mapping, matching lengths and unchanged Song')


if __name__ == '__main__':
    main()
