"""Optional Pedalboard host. Run on the child process main thread, never in the HTTP server."""
from pathlib import Path
import json
import os
import subprocess
import sys
import wave
import numpy as np
from pedalboard import load_plugin


def configure(plugin, spec, before=False):
    """Use plugin-exposed physical values; save native readbacks as audition evidence."""
    values = spec['values']
    if spec['plugin'] == 'reverb':
        plugin.lock_mix = 'Unlocked'
        plugin.freeze = 'Freeze Off'
        plugin.auto_gate_enabled = False
        plugin.predelay_sync = 'Free'
        plugin.space = 3.2 if before else values['space']
        plugin.predelay = values['predelay']
        plugin.mix = values['mix']
        keys = ['space', 'predelay', 'mix']
    elif spec['plugin'] == 'delay':
        plugin.lock_mix = 'Unlocked'
        plugin.delay_sync = 'Free'
        plugin.delay_freeze = False
        plugin.delay_time = values['time']
        plugin.feedback = 65 if before else values['feedback']
        plugin.mix = values['mix']
        keys = ['delay_time', 'feedback', 'mix']
    else:
        plugin.processing_mode = 'Zero Latency'
        for band in range(1, 25):
            setattr(plugin, f'band_{band}_used', 'Unused')
        plugin.band_1_used = 'Used'
        plugin.band_1_enabled = True
        plugin.band_1_shape = spec['shape']
        plugin.band_1_frequency = values['freq']
        plugin.band_1_gain = values['gain']
        plugin.band_1_q = values['q']
        plugin.band_1_dynamic_range = 0.
        keys = ['band_1_shape', 'band_1_frequency', 'band_1_gain', 'band_1_q', 'processing_mode']
    return {key: str(getattr(plugin, key)) for key in keys}


def run(folder):
    spec = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    rate = 48000
    warm = min(2., spec['start'])
    frames = round((spec['end'] - spec['start'] + spec['tail']) * rate)
    warm_frames = round(warm * rate)
    duration = spec['end'] - spec['start'] + warm
    decode = subprocess.run([spec['ffmpeg'], '-v', 'error', '-nostdin', '-ss', str(spec['start'] - warm),
                             '-i', spec['path'], '-t', str(duration), '-vn', '-ac', '2', '-ar', str(rate),
                             '-f', 'f32le', 'pipe:1'], capture_output=True, timeout=35, check=True,
                            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    samples = np.frombuffer(decode.stdout, dtype='<f4').reshape(-1, 2).T
    signal = np.zeros((2, warm_frames + frames), dtype=np.float32)
    count = min(samples.shape[1], round(duration * rate))
    signal[:, :count] = samples[:, :count]
    if not np.isfinite(signal).all():
        raise ValueError('Input contains invalid samples')
    plugin = load_plugin(spec['pluginPath'])
    readbacks = configure(plugin, spec)
    b = plugin(signal, rate, buffer_size=512)[:, warm_frames:warm_frames + frames]
    a = signal[:, warm_frames:warm_frames + frames].copy()
    a_readbacks = None
    if spec['comparison'] != 'dry':
        previous = load_plugin(spec['pluginPath'])
        a_readbacks = configure(previous, spec, before=True)
        a = previous(signal, rate, buffer_size=512)[:, warm_frames:warm_frames + frames]
    if a.shape != b.shape or not np.isfinite(b).all() or not np.isfinite(a).all():
        raise ValueError('Plugin returned invalid audio')
    peak = max(float(np.max(np.abs(a))), float(np.max(np.abs(b))), 1e-9)
    common = min(1., .95 / peak)
    for name, audio in [('a', a), ('b', b)]:
        with wave.open(str(folder / (name + '.wav')), 'wb') as stream:
            stream.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
            stream.writeframes((np.clip(audio.T * common, -1., 1.) * 32767).round().astype('<i2').tobytes())
    result = {'engine': 'FabFilter VST3 / Pedalboard', 'plugin': plugin.name,
              'start': spec['start'], 'end': spec['end'], 'tail': spec['tail'],
              'duration': frames / rate, 'sampleRate': rate, 'commonGain': common,
              'parametersB': readbacks, 'parametersA': a_readbacks, 'comparison': spec['comparison'],
              'rmsA': float(np.sqrt(np.mean(a ** 2))), 'rmsB': float(np.sqrt(np.mean(b ** 2))),
              'differenceRms': float(np.sqrt(np.mean((a - b) ** 2)))}
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    run(Path(sys.argv[1]))
