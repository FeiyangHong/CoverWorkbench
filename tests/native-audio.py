"""Optional real-plugin integration check; synthetic audio only, never bundled renders."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import native_audio as host


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--installed', action='store_true', help='Render with locally installed, licensed FabFilter plugins')
    args = parser.parse_args()
    for bad in [float('nan'), float('inf'), -1, 31, True]:
        try:
            host.number(bad, 0, 30)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid range accepted')
    for bad in ['relative.wav', '../a.wav', 'https://example.com/audio.wav', '\x00.wav']:
        try:
            host.source(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid source accepted')
    for jid, name in [('../', 'a.wav'), ('a' * 32, 'request.json'), ('a' * 32, 'a.wav')]:
        try:
            host.media(jid, name)
        except ValueError:
            pass
        else:
            raise AssertionError('Unregistered/private file exposed')
    print('PASS: interval finite/range checks, local-source validation, private-file isolation')
    if not args.installed:
        print('SKIP: real FabFilter rendering (use --installed on an authorized local installation)')
        return
    assert host.status()['engine'] and host.status()['decoder']
    root = ROOT / 'work'
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='native-audio-', dir=root) as folder:
        source = Path(folder) / 'synthetic voice.wav'
        rate = 48000
        with wave.open(str(source), 'wb') as stream:
            stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            stream.writeframes(b''.join(struct.pack('<h', round(6000 * math.sin(2 * math.pi * (220 + i / rate * 100) * i / rate))) for i in range(rate * 3)))
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        results = []
        for plugin, comparison in [('reverb', 'dry'), ('delay', 'dry'), ('eq', 'dry'), ('reverb', 'tail'), ('delay', 'feedback')]:
            body = {'path': '"' + str(source) + '"', 'start': 1, 'end': 2, 'plugin': plugin, 'comparison': comparison, 'tail': 2}
            job = host.enqueue(body)
            # Waiting for the single worker avoids filling the bounded queue.
            import time
            deadline = time.monotonic() + 130
            while host.job(job['id'])['status'] in ['queued', 'running'] and time.monotonic() < deadline:
                time.sleep(.1)
            job = host.job(job['id'])
            assert job['status'] == 'ready', job
            data = job['result']
            assert data['duration'] == 3 and data['sampleRate'] == rate
            assert data['differenceRms'] > .00001 and data['rmsB'] > .00001, data
            assert bool(data['parametersA']) == (comparison != 'dry')
            signals = []
            for side in ['a', 'b']:
                with wave.open(str(host.media(job['id'], side + '.wav')), 'rb') as stream:
                    assert stream.getnframes() == rate * 3 and stream.getnchannels() == 2
                    import numpy as np
                    signals.append(np.frombuffer(stream.readframes(rate * 3), dtype='<i2').reshape(-1, 2) / 32768.)
            assert max(abs(x).max() for x in signals) <= .951
            if plugin in ['reverb', 'delay']:
                assert (signals[1][rate + rate // 5:] ** 2).sum() > .001, 'Effect tail missing'
            if plugin == 'eq':
                from pedalboard import load_plugin
                import native_audio_worker as worker
                effect = load_plugin(str(host.plugin_path('eq')))
                spec = {'plugin': 'eq', 'values': {'freq': 350., 'gain': -6., 'q': 1.}, 'shape': 'Bell'}
                worker.configure(effect, spec)
                impulse = np.zeros((2, rate), dtype=np.float32)
                impulse[:, 100] = .1
                assert np.argmax(abs(effect(impulse, rate)[0])) == 100, 'Zero-latency EQ alignment changed'
            results.append({'plugin': plugin, 'comparison': comparison, 'differenceRms': data['differenceRms']})
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest, 'Input was modified'
        from pedalboard import load_plugin
        import native_audio_worker as worker
        small = load_plugin(str(host.plugin_path('reverb')))
        worker.configure(small, {'plugin': 'reverb', 'values': {'space': .4, 'predelay': 30, 'mix': 25}})
        assert abs(float(small.space) - 400) < 5, 'Subsecond Space must use the plugin milliseconds range'
    print('PASS: real FabFilter render, parameter readbacks, aligned lengths, EQ impulse alignment, tails, headroom and unchanged input')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
