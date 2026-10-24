"""Read-only, bounded Studio One static mixer snapshots for local auditions."""
from pathlib import Path
import hashlib
import json
import zipfile
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import native_audio as host

CLASSES = {
 '72C4DB717A4D459AB97E51745D84B39D': ('FabFilter Pro-Q 3', 'eq'),
 '79F415E3C8E74807AD5DA3CF7024F618': ('FabFilter Pro-C 2', None),
 '59E324D08EE811E1B8578101BBE59B18': ('FabFilter Pro-DS', None),
 '6070873C802A4B078FC06AB5459154E9': ('FabFilter Pro-R 2', 'reverb'),
 'D2EE67F2C552402D902115931AFDAE6B': ('FabFilter Timeless 3', 'delay'),
}
TAGS = {'AudioOutputChannel', 'AudioSynthChannel', 'AudioTrackChannel', 'AudioEffectChannel', 'AudioGroupChannel'}


def child(node, tag, key):
    return node.find(f'./{tag}[@x_id="{key}"]')


def read_xml(archive, name):
    item = archive.getinfo(name)
    if item.file_size > 4_000_000:
        raise ValueError('工程 XML 太大，暂不支持该布局')
    return ET.fromstring(archive.read(name).decode('utf-8-sig').replace('x:id', 'x_id'))


def finite(value, low=0, high=64):
    return host.number(value, low, high)


def read(value, dest=None):
    if not isinstance(value, str):
        raise ValueError('请选择已保存的 Studio One Song')
    path = Path(value.strip().strip('"“”'))
    if not path.is_absolute() or not path.is_file() or path.suffix.lower() != '.song':
        raise ValueError('请选择本机已有的 .song 工程')
    path = path.resolve()
    if path.stat().st_size > 100_000_000:
        raise ValueError('工程文件超过 100 MB，暂不支持')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('工程包含重复的内部路径')
        mixer = read_xml(archive, 'Devices/audiomixer.xml')
        song = read_xml(archive, 'Song/song.xml')
        nodes = [n for n in mixer.iter() if n.tag in TAGS]
        if not 1 <= len(nodes) <= 64:
            raise ValueError('试听支持 1–64 个混音通道')
        uid_map = {}
        for index, node in enumerate(nodes):
            uid = child(node, 'UID', 'uniqueID')
            if uid is None or uid.get('uid') in uid_map:
                raise ValueError('混音通道缺少唯一标识')
            uid_map[uid.get('uid')] = index
        blockers, warnings, channels, targets = [], [], [], []
        def route(node):
            connection = child(node, 'Connection', 'destination')
            if connection is None:
                return None
            value = connection.get('objectID', '').split('/')[0]
            if value not in uid_map:
                blockers.append('存在未识别的输出／发送目标：' + connection.get('friendlyName', value))
            return uid_map.get(value)
        fx_count = 0
        for index, node in enumerate(nodes):
            row = {'id': index, 'label': node.get('label', node.get('name')), 'type': node.tag,
                   'gain': finite(node.get('gain', 1)), 'mute': node.get('mute') == '1',
                   'destination': route(node), 'inserts': [], 'sends': []}
            if node.get('solo') == '1':
                blockers.append(row['label'] + ' 存在 Solo；暂不重建宿主独奏逻辑')
            if node.tag != 'AudioOutputChannel' and row['destination'] is None:
                blockers.append(row['label'] + ' 没有可识别的输出')
            pan = child(node, 'Attributes', 'Panner')
            speaker = child(node, 'SpeakerSetup', 'speakerType')
            if speaker is not None and speaker.get('type') != 'Stereo':
                blockers.append(row['label'] + ' 不是双声道；当前不还原单声道／环绕声的声像律')
            if abs(float(node.get('pan', .5)) - .5) > 1e-6 or (pan is not None and any(abs(float(pan.get(k, v)) - v) > 1e-6 for k, v in [('panX1', .5), ('panX2', 0), ('panWidth', 1), ('stereoMode', 0), ('spatialObjectMode', 0)])):
                blockers.append(row['label'] + ' 使用了当前不能准确还原的声像／宽度设置')
            inp = child(node, 'Attributes', 'InputFX')
            row['inputGainDB'] = finite(inp.get('gain', 0), -60, 36) if inp is not None else 0
            row['invert'] = [inp is not None and inp.get(k) == '1' for k in ['invertPhaseL', 'invertPhaseR']]
            mixfx = child(node, 'Attributes', 'AudioBusMixFX')
            if mixfx is not None and mixfx.get('passThrough') != '1':
                blockers.append(row['label'] + ' 包含 Mix FX，独立宿主不能还原')
            for group in ['Inserts', 'PostFaderInserts']:
                container = child(node, 'Attributes', group)
                if container is None:
                    continue
                for slot in list(container):
                    data = child(slot, 'Attributes', 'deviceData')
                    if data is None:
                        if slot.get('x_id') == 'Combinator' and any(n.tag == 'Connection' for n in slot.iter()):
                            blockers.append(row['label'] + ' 包含 FX Chain 宏路由')
                        continue
                    if group == 'PostFaderInserts':
                        blockers.append(row['label'] + ' 包含推子后插入，暂不还原其发送取点')
                    fx_count += 1
                    if fx_count > 64:
                        raise ValueError('工程效果器过多，试听最多支持 64 个')
                    preset = child(slot, 'String', 'presetPath')
                    effect = {'id': f'{index}:{len(row["inserts"])}', 'label': data.get('name', ''),
                              'bypass': slot.get('bypass') == '1', 'preset': None, 'kind': None}
                    if preset is None or preset.get('text') not in archive.namelist():
                        blockers.append(effect['label'] + ' 缺少工程内 VST3 状态')
                    else:
                        name = preset.get('text')
                        if archive.getinfo(name).file_size > 4_000_000:
                            raise ValueError('插件状态过大')
                        blob = archive.read(name)
                        key = blob[8:40].decode('ascii', errors='ignore') if blob[:4] == b'VST3' else ''
                        if key not in CLASSES:
                            blockers.append(effect['label'] + ' 不是当前支持的 FabFilter VST3')
                        else:
                            binary, kind = CLASSES[key]
                            binary_path = host.plugin_binary(binary)
                            effect.update(binary=str(binary_path) if binary_path else '', kind=kind,
                                          stateSha256=hashlib.sha256(blob).hexdigest())
                            if not binary_path and not effect['bypass']:
                                blockers.append('本机缺少 ' + binary)
                            if dest:
                                filename = f'fx-{fx_count}.vstpreset'
                                (dest / filename).write_bytes(blob)
                                effect['preset'] = filename
                    if any(n.tag == 'Connection' for n in slot.iter()):
                        blockers.append(effect['label'] + ' 包含外部侧链连接')
                    row['inserts'].append(effect)
                    if effect['kind']:
                        targets.append({'id': effect['id'], 'channel': index, 'channelLabel': row['label'],
                                        'label': effect['label'], 'kind': effect['kind'],
                                        'muted': row['mute'], 'bypassed': effect['bypass']})
            sends = child(node, 'Attributes', 'Sends')
            if sends is not None:
                for send in sends:
                    if child(send, 'Connection', 'destination') is None:
                        continue
                    if abs(float(send.get('pan', .5)) - .5) > 1e-6:
                        blockers.append(row['label'] + ' 的发送使用了非居中声像')
                    row['sends'].append({'to': route(send), 'level': finite(send.get('level', 1)),
                                         'pre': send.get('prefader') == '1', 'bypass': send.get('bypass') == '1'})
            channels.append(row)
        outputs = [c['id'] for c in channels if c['type'] == 'AudioOutputChannel']
        if len(outputs) != 1:
            blockers.append('当前仅支持一个主输出')
        # Topological order for dry paths, sends, FX returns and shared buses.
        edges = {c['id']: {d for d in [c['destination']] + [s['to'] for s in c['sends'] if not s['bypass']] if d is not None} for c in channels}
        indegree = {c['id']: 0 for c in channels}
        for destinations in edges.values():
            for d in destinations:
                indegree[d] += 1
        queue = [k for k, v in indegree.items() if v == 0]
        order = []
        while queue:
            item = queue.pop(0); order.append(item)
            for d in edges[item]:
                indegree[d] -= 1
                if indegree[d] == 0:
                    queue.append(d)
        if len(order) != len(channels):
            blockers.append('存在反馈／循环路由，不能按静态图离线还原')
        for region in song.iter('AutomationRegion'):
            if region.get('mute') == '1':
                continue
            ref = child(region, 'Url', 'points')
            name = unquote(urlsplit(ref.get('url', '')).path).lstrip('/') if ref is not None else ''
            if name not in archive.namelist() or archive.getinfo(name).file_size > 1_000_000 or not archive.read(name).endswith(b'events[]}'):
                blockers.append('存在非空或无法读取的自动化：' + region.get('title', 'Automation'))
        backing = []
        if 'Song/mediapool.xml' in archive.namelist():
            pool = read_xml(archive, 'Song/mediapool.xml')
            clips = {c.get('mediaID'): c for c in pool.iter('AudioClip')}
            for track in song.iter('MediaTrack'):
                if track.get('mediaType') != 'Audio':
                    continue
                uid = child(track, 'UID', 'channelID')
                events = list(track.iter('AudioEvent'))
                if uid is None or uid.get('uid') not in uid_map or len(events) != 1:
                    warnings.append('部分音频事件不能自动推荐；请手动选择完整伴奏文件与时间偏移')
                    continue
                event = events[0]; clip = clips.get(event.get('clipID'))
                url = child(clip, 'Url', 'path') if clip is not None else None
                if url is None or event.get('timeFormat') != '0' or float(event.get('speed', 1)) != 1:
                    warnings.append('伴奏事件时间格式／变速不受支持，请手动映射素材')
                    continue
                u = urlsplit(url.get('url', ''))
                p = Path(unquote(u.path).lstrip('/')) if u.scheme == 'file' else path.parent / 'Media' / Path(unquote(u.path)).name
                backing.append({'channel': uid_map[uid.get('uid')], 'path': str(p), 'exists': p.is_file(),
                                'offset': float(event.get('start', 0)) - float(event.get('offset', 0))})
        tempo_segments = list(song.iter('TempoMapSegment'))
        if len(tempo_segments) > 1:
            blockers.append('工程存在变速，当前无法向独立插件提供完整宿主节拍')
        bpm = 60 / host.number(tempo_segments[0].get('tempo', .5), .01, 60) if tempo_segments else 120
        warnings.append('读取磁盘已保存状态；只播放映射的音频，不运行 SV，也不自动生成其他主声／和声。')
        warnings.append('独立 VST3 静态路由试听尚未与 Studio One 原生导出做抵消验证；尾音和压缩预热可能有差异。')
        return {'path': str(path), 'sha256': digest, 'channels': channels, 'targets': targets,
                'order': order, 'main': outputs[0] if outputs else None, 'backing': backing,
                'blockers': list(dict.fromkeys(blockers)), 'warnings': list(dict.fromkeys(warnings)), 'bpm': bpm}


def public(graph):
    return {k: v for k, v in graph.items() if k not in ['order', 'main']}


def enqueue(body, probe=False):
    graph = read(body.get('song'))
    if body.get('songHash') != graph['sha256']:
        raise ValueError('Song 已改变，请重新读取工程')
    if graph['blockers']:
        raise ValueError('暂不能还原：' + '；'.join(graph['blockers']))
    target = next((t for t in graph['targets'] if t['id'] == body.get('target')), None)
    if not target:
        raise ValueError('请选择工程内要调整的插件')
    if not host.status()['engine']:
        raise ValueError('请先安装本机试听引擎')
    band = host.number(body.get('band', 1), 1, 24)
    if not band.is_integer():
        raise ValueError('EQ 频点编号必须是整数')
    band = int(band)
    spec = {'mode': 'song-probe' if probe else 'song', 'song': graph['path'], 'songHash': graph['sha256'],
            'target': target, 'band': band, 'enableTarget': body.get('enableTarget') is True}
    if not probe:
        start = host.number(body.get('start'), 0, 36000)
        end = host.number(body.get('end'), start + .25, start + 30)
        spec.update(start=start, end=end, tail=host.number(body.get('tail', 4), 0, 8), sources=[])
        rows = body.get('sources')
        if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
            raise ValueError('请映射 1–16 路音频')
        seen = set()
        for row in rows:
            channel = row.get('channel')
            if isinstance(channel, bool) or not isinstance(channel, int) or channel not in [c['id'] for c in graph['channels'] if c['type'] in ['AudioTrackChannel', 'AudioSynthChannel']] or channel in seen:
                raise ValueError('音频通道映射无效或重复')
            seen.add(channel)
            info = host.inspect({'path': row.get('path')})
            offset = host.number(row.get('offset', 0), -3600, 36000)
            if end <= offset or start >= offset + info['duration']:
                raise ValueError('素材与试听区间没有重叠：' + info['name'])
            role = row.get('role', 'vocal')
            if role not in ['vocal', 'backing']:
                raise ValueError('素材类型无效')
            spec['sources'].append({**info, 'channel': channel, 'offset': offset, 'role': role,
                                    'gainDB': host.number(row.get('gainDB', 0), -36, 12)})
        changes = body.get('changes', {})
        ranges = {'reverb': {'space': (.2, 10), 'predelay': (0, 500), 'mix': (0, 100)},
                  'delay': {'time': (1, 999), 'feedback': (0, 95), 'mix': (0, 100)},
                  'eq': {'freq': (10, 30000), 'gain': (-30, 30), 'q': (.025, 40)}}[target['kind']]
        if not isinstance(changes, dict) or set(changes) - set(ranges):
            raise ValueError('不支持的参数修改')
        spec['changes'] = {k: host.number(v, *ranges[k]) for k, v in changes.items()}
        spec['ffmpeg'] = host.settings.executable('ffmpeg')
    # Snapshot and parameter bytes belong only to this ignored audition directory.
    return host.submit(spec, prepare=lambda folder: _snapshot(graph, folder))


def _snapshot(graph, folder):
    snapshot = read(graph['path'], folder)
    if snapshot['sha256'] != graph['sha256']:
        raise ValueError('Song 在读取时改变，请保存后重试')
    (folder / 'mixer.json').write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
