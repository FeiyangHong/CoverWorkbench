"""Restore real component state and render an acyclic static Studio One mixer."""
from pathlib import Path
import json
import os
import struct
import subprocess
import sys
import wave
import numpy as np
from pedalboard import load_plugin, AudioProcessorParameter

PARAMETERS = {}


def parameter(plugin, key):
    # Construct only named parameters: plugin.parameters scans every EQ band,
    # including unused ones, and can dominate the entire audition render time.
    cache = PARAMETERS.setdefault(plugin, {})
    if key not in cache:
        name = key.replace('_', ' ').title().replace('Xlfo', 'XLFO')
        cache[key] = AudioProcessorParameter(plugin, name)
    return cache[key]


def set_value(plugin, key, value):
    param = parameter(plugin, key)
    param.raw_value = param.get_raw_value_for(value)


def component(blob):
    offset = struct.unpack_from('<Q', blob, 40)[0]
    if blob[offset:offset + 4] != b'List':
        raise ValueError('Invalid VST3 state')
    for i in range(struct.unpack_from('<I', blob, offset + 4)[0]):
        tag, start, size = struct.unpack_from('<4sQQ', blob, offset + 8 + 20 * i)
        if tag == b'Comp':
            return blob[start:start + size]
    raise ValueError('Missing VST3 component')


def controller(blob):
    offset = struct.unpack_from('<Q', blob, 40)[0]
    for i in range(struct.unpack_from('<I', blob, offset + 4)[0]):
        tag, start, size = struct.unpack_from('<4sQQ', blob, offset + 8 + 20 * i)
        if tag == b'Cont':
            return blob[start:start + size]
    return b''


def component_preset(raw, ui_state):
    """Sanitized starter presets intentionally omit controller/UI metadata."""
    chunks = [(b'Comp', component(raw)), (b'Cont', ui_state)]
    body = b''; index = []
    for tag, data in chunks:
        index.append(struct.pack('<4sQQ', tag, 48 + len(body), len(data)))
        body += data
    return raw[:40] + struct.pack('<Q', 48 + len(body)) + body + b'List' + struct.pack('<I', len(chunks)) + b''.join(index)


def restore(effect, folder):
    raw = (folder / effect['preset']).read_bytes()
    initial = load_plugin(effect['binary'])
    initial.preset_data = raw if controller(raw) else component_preset(raw, controller(initial.preset_data))
    # JUCE's preset import can leave the FabFilter controller at default values.
    # Reload the complete state to synchronize controller and DSP before editing.
    plugin = initial
    plugin.raw_state = plugin.raw_state
    if component(plugin.preset_data) != component(raw):
        raise ValueError(effect['label'] + ' 的 DSP 状态未能精确恢复；停止试听，未使用默认值代替')
    return plugin


def display(plugin, key):
    return parameter(plugin, key).string_value


def physical(plugin, key):
    value = float(display(plugin, key).split()[0].rstrip('%'))
    if key == 'space' and display(plugin, key).strip().endswith('ms'):
        value /= 1000
    return value


def profile(plugin, target, band):
    kind = target['kind']
    bands = []
    if kind == 'reverb':
        rows = [('space', 'space', 'Space · 空间时间', .2, 10, .01, 's'),
                ('predelay', 'predelay', 'Predelay · 预延迟', 0, 500, 1, 'ms'),
                ('mix', 'mix', 'Mix · 湿声比例', 0, 100, 1, '%')]
    elif kind == 'delay':
        rows = [('time', 'delay_time', 'Delay Time · 回声间隔', 1, 999, .1, 'ms'),
                ('feedback', 'feedback', 'Feedback · 反馈', 0, 95, 1, '%'),
                ('mix', 'mix', 'Mix · 湿声比例', 0, 100, 1, '%')]
    else:
        for i in range(1, 25):
            if parameter(plugin, f'band_{i}_used').raw_value > .5:
                bands.append({'id': i, 'label': f'Band {i} · {display(plugin, f"band_{i}_frequency")} · {display(plugin, f"band_{i}_shape")}'})
        if band not in [b['id'] for b in bands]:
            band = bands[0]['id'] if bands else 1
        prefix = f'band_{band}_'
        rows = [('freq', prefix + 'frequency', 'Frequency · 中心频率', 10, 30000, 1, 'Hz'),
                ('gain', prefix + 'gain', 'Gain · 增益', -30, 30, .1, 'dB'),
                ('q', prefix + 'q', 'Q · 范围宽窄', .025, 40, .025, '')]
    controls = [{'key': key, 'parameter': name, 'label': label, 'min': low, 'max': high, 'step': step,
                 'unit': unit, 'value': physical(plugin, name), 'readback': display(plugin, name)}
                for key, name, label, low, high, step, unit in rows]
    notes = []
    if kind == 'eq':
        notes.append(f'只修改当前频点 Band {band}，其余频点、形状和动态 EQ 保留工程状态。')
        shape = display(plugin, f'band_{band}_shape')
        if shape in ['Low Cut', 'High Cut', 'Notch', 'Band Pass']:
            for control in controls:
                if control['key'] == 'gain':
                    control['disabled'] = True
            notes.append('该频点形状为 ' + shape + '，不使用增益旋钮；可调整频率或 Q。')
        if not bands:
            notes.append('工程没有已使用频点；B 修改时会启用 Band 1，A 保持原工程。')
    return {'controls': controls, 'bands': bands, 'band': band, 'notes': notes,
            'baseline': {c['parameter']: c['readback'] for c in controls}}


def ensure_free_timing(plugin, effect):
    keys = ['predelay_sync', 'auto_gate_sync'] if effect['kind'] == 'reverb' else ['delay_sync'] + [f'xlfo_{i}_sync_mode' for i in range(1, 7)] if effect['kind'] == 'delay' else []
    for key in keys:
        value = display(plugin, key)
        if value not in ['Free', 'Off', 'Disabled']:
            raise ValueError(effect['label'] + ' 使用宿主节拍同步（' + key + ' = ' + value + '），当前独立宿主不能准确还原')


def decode(source, spec, frames, warm, rate):
    out = np.zeros((2, frames), dtype=np.float32)
    absolute_start = spec['start'] - warm
    file_start = max(0., absolute_start - source['offset'])
    lead = max(0, round((source['offset'] - absolute_start) * rate))
    stop = spec['end'] + (spec['tail'] if source['role'] == 'backing' else 0)
    count = max(0, min(frames - lead, round((stop - max(absolute_start, source['offset'])) * rate)))
    if count <= 0:
        return out
    result = subprocess.run([spec['ffmpeg'], '-v', 'error', '-nostdin', '-ss', str(file_start), '-i', source['path'],
                             '-t', str(count / rate), '-vn', '-ac', '2', '-ar', str(rate), '-f', 'f32le', 'pipe:1'],
                            capture_output=True, timeout=35, check=True,
                            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    audio = np.frombuffer(result.stdout, dtype='<f4').reshape(-1, 2).T
    n = min(count, audio.shape[1]); out[:, lead:lead + n] = audio[:, :n]
    if not np.isfinite(out).all():
        raise ValueError('素材中包含非有限音频采样')
    return out * (10 ** (source.get('gainDB', 0) / 20))


def render_graph(graph, signals, spec, folder, edited=False, cache=None):
    cache = {} if cache is None else cache
    shape = next(iter(signals.values())).shape
    pending = {c['id']: np.zeros(shape, dtype=np.float32) for c in graph['channels']}
    for key, data in signals.items():
        pending[key] += data
    loaded = []
    readbacks = {}
    target_id = spec['target']['id']
    for cid in graph['order']:
        channel = graph['channels'][cid]
        audio = pending[cid]
        if channel['mute'] and not (spec['enableTarget'] and cid == spec['target']['channel']):
            continue
        if not np.any(audio):
            continue
        audio *= 10 ** (channel['inputGainDB'] / 20)
        for i, invert in enumerate(channel['invert']):
            if invert:
                audio[i] *= -1
        for effect in channel['inserts']:
            is_target = effect['id'] == target_id
            if effect['bypass'] and not (is_target and spec['enableTarget']):
                continue
            if effect['id'] not in cache:
                cache[effect['id']] = restore(effect, folder)
                ensure_free_timing(cache[effect['id']], effect)
            plugin = cache[effect['id']]
            details = profile(plugin, spec['target'], spec['band']) if is_target else None
            if is_target and edited:
                changes = spec['changes']
                if spec['target']['kind'] == 'eq' and changes and not details['bands']:
                    set_value(plugin, f'band_{details["band"]}_used', 'Used')
                    set_value(plugin, f'band_{details["band"]}_enabled', True)
                for control in details['controls']:
                    if control['key'] in changes:
                        value = changes[control['key']]
                        if control['parameter'] == 'space' and value < 1:
                            value *= 1000
                        set_value(plugin, control['parameter'], value)
            if is_target:
                readbacks = {c['parameter']: display(plugin, c['parameter']) for c in details['controls']}
            loaded.append({'id': effect['id'], 'label': effect['label'], 'stateSha256': effect['stateSha256'],
                           'componentRestored': True, 'latencySamples': plugin.reported_latency_samples})
            audio = plugin(audio, 48000, buffer_size=512)
        before_fader = audio
        audio = before_fader * channel['gain']
        for send in channel['sends']:
            if not send['bypass'] and send['to'] is not None:
                pending[send['to']] += (before_fader if send['pre'] else audio) * send['level']
        if channel['destination'] is not None:
            pending[channel['destination']] += audio
        if cid == graph['main']:
            return audio, readbacks, loaded
    return np.zeros(shape, dtype=np.float32), readbacks, loaded


def run(folder):
    spec = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    graph = json.loads((folder / 'mixer.json').read_text(encoding='utf-8'))
    target = next(e for c in graph['channels'] for e in c['inserts'] if e['id'] == spec['target']['id'])
    plugin = restore(target, folder)
    ensure_free_timing(plugin, target)
    details = profile(plugin, spec['target'], spec['band'])
    if spec['mode'] == 'song-probe':
        result = {**details, 'target': spec['target'], 'componentRestored': True}
    else:
        rate = 48000; warm = min(2., spec['start']); begin = round(warm * rate)
        n = round((spec['end'] - spec['start'] + spec['tail']) * rate)
        signals = {s['channel']: decode(s, spec, n + begin, warm, rate) for s in spec['sources']}
        cache = {target['id']: plugin}
        a, read_a, chain_a = render_graph(graph, signals, spec, folder, cache=cache)
        b, read_b, chain_b = render_graph(graph, signals, spec, folder, True, cache=cache)
        a = a[:, begin:begin + n]; b = b[:, begin:begin + n]
        if not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError('工程混音产生了无效采样')
        peak = max(abs(a).max(), abs(b).max(), 1e-9); common = min(1., .95 / float(peak))
        for key, audio in [('a', a), ('b', b)]:
            with wave.open(str(folder / (key + '.wav')), 'wb') as stream:
                stream.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
                stream.writeframes((np.clip(audio.T * common, -1, 1) * 32767).round().astype('<i2').tobytes())
        result = {'engine': 'Studio One static mixer / real FabFilter VST3', 'mode': 'song',
                  'plugin': spec['target']['label'], 'songSha256': graph['sha256'],
                  'duration': n / rate, 'start': spec['start'], 'end': spec['end'], 'tail': spec['tail'],
                  'sampleRate': rate, 'commonGain': common, 'comparison': 'song',
                  'parametersA': read_a, 'parametersB': read_b, 'chainA': chain_a, 'chainB': chain_b,
                  'mappedChannels': list(signals), 'enableTarget': spec['enableTarget'],
                  'differenceRms': float(np.sqrt(np.mean((a - b) ** 2))),
                  'rmsA': float(np.sqrt(np.mean(a ** 2))), 'rmsB': float(np.sqrt(np.mean(b ** 2)))}
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    try:
        run(Path(sys.argv[1]))
    except (ValueError, RuntimeError) as error:
        (Path(sys.argv[1]) / 'error.json').write_text(json.dumps({'error': str(error)}, ensure_ascii=False), encoding='utf-8')
        raise
