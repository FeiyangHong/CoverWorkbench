"""Export a sanitized, media-free starter mix from an owner's local Song."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import daw

PLACEHOLDER = 'file:///C:/CoverWorkbench/Template/'
REQUIRED = ['metainfo.xml', 'settings.xml', 'Song/song.xml', 'Song/mediapool.xml',
            'Devices/transportdevice.xml', 'Devices/audiomixer.xml',
            'Devices/audiosynthfolder.xml', 'Devices/musictrackdevice.xml']


def preset(blob, synth=False):
    payload = b''
    records = []
    for tag, data in daw.chunks(blob):
        if tag == b'Cont':
            data = b''  # Controller/UI metadata can contain source track names.
        elif tag == b'Comp' and synth:
            data = json.dumps({'projectPath': '', 'sessionConfiguration': {'channelLayout': 536870930},
                               'araBridgeEnabled': False}).encode()
        elif tag not in (b'Comp', b'Info'):
            raise ValueError('Unexpected plugin state chunk')
        records.append((tag, 48 + len(payload), len(data)))
        payload += data
    return (blob[:40] + struct.pack('<Q', 48 + len(payload)) + payload + b'List' +
            struct.pack('<I', len(records)) + b''.join(struct.pack('<4sQQ', *r) for r in records))


def export(source, ident, name, output):
    daw.validate_template(source)
    source_hash = daw.sha(source)
    with zipfile.ZipFile(source) as archive:
        docs = {n: daw.xml(archive.read(n)) for n in REQUIRED}
        mix = docs['Devices/audiomixer.xml']
        labels = {}
        lead = 0
        for c in daw.channels(mix):
            old = c.get('label', '')
            if c.tag == 'AudioSynthChannel':
                if re.search('harmony|和声', old, re.I):
                    new = 'Harmony'
                elif re.search('lead|主声', old, re.I):
                    lead += 1
                    new = f'Lead {lead}'
                else:
                    new = old
            else:
                new = {'AudioTrackChannel': 'Instrumental', 'AudioGroupChannel': 'Vocal Bus',
                       'AudioOutputChannel': 'Main'}.get(c.tag, old.replace('Timeless', 'Delay'))
            labels[old] = new
        # Drop song-specific automation and non-musical global tracks.
        song = docs['Song/song.xml']
        tracks = daw.child(song.find('Attributes'), 'List', 'Tracks')
        for track in list(tracks):
            if track.tag not in ['MediaTrack', 'MarkerTrack']:
                tracks.remove(track)
        for doc in docs.values():
            for node in doc.iter():
                if node.get('x_id') == 'AutomationRegionList':
                    node.clear(); node.set('x_id', 'AutomationRegionList'); node.set('visible', '0')
        for track in tracks.iter('MediaTrack'):
            track.set('name', 'SV Vocals' if track.get('mediaType') == 'Music' else 'Instrumental')
        for marker in tracks.iter('MarkerEvent'):
            marker.set('name', 'End' if marker.get('markerType') == '3' else 'Start')
            if marker.get('markerType') == '3': marker.set('start', '2')
        event = next(song.iter('AudioEvent'))
        event.attrib.update(name='Instrumental', start='0', length='1', speed='1')
        song.find('Attributes').set('length', '60')
        context = daw.child(song.find('Attributes'), 'Attributes', 'timeContext')
        tempo = daw.child(context, 'TempoMap', 'tempoMap'); tempo.clear(); tempo.set('x_id', 'tempoMap')
        ET.SubElement(tempo, 'TempoMapSegment', curveType='0', start='0', end='1.7976931348623156e+200', tempo='0.5')
        meter = daw.child(context, 'TimeSignatureMap', 'timeSignatureMap'); meter.clear(); meter.set('x_id', 'timeSignatureMap')
        ET.SubElement(meter, 'TimeSignatureMapSegment', start='0', numerator='4', denominator='4')
        next(context.iter('TimeZone')).set('end', '60')
        transport = docs['Devices/transportdevice.xml']
        transport.attrib.update(position='0', loopStart='0', loopEnd='1', loopActive='0')
        pool = docs['Song/mediapool.xml']
        clip = next(pool.iter('AudioClip')); clip.set('peak', '1')
        daw.child(clip, 'Url', 'path').set('url', PLACEHOLDER + 'instrumental.wav')
        daw.child(clip, 'Attributes', 'format').attrib.update(frameCount='48000', sampleRate='48000',
            numChannels='2', bitDepth='24', sampleType='0')
        for node in clip.iter('AudioTempoMap'):
            node.clear(); node.set('x_id', 'tempoMap'); node.set('tempoApproved', '0')
        daw.child(pool, 'Attributes', 'documentPath').set('url', PLACEHOLDER + 'template.song')
        for node in docs['settings.xml'].iter():
            if 'fileName' in node.attrib: node.set('fileName', 'Cover_Mixdown')
            if node.get('x_id') == 'mixdown': node.set('url', PLACEHOLDER + 'Mixdown/')
        meta = ET.Element('MetaInformation')
        for key, value in {'Document:Title': name, 'Document:Creator': 'CoverWorkbench',
                           'Document:MimeType': 'application/x.presonus-song', 'Document:FormatVersion': '8',
                           'Media:SampleRate': '48000', 'Media:Tempo': '120', 'Media:Length': '1',
                           'Media:BitDepth': '24', 'Media:TimeSignatureNumerator': '4',
                           'Media:TimeSignatureDenominator': '4'}.items():
            ET.SubElement(meta, 'Attribute', id=key, value=value)
        docs['metainfo.xml'] = meta
        output_files = {}
        renames = {}
        preserved = []
        for index, old in enumerate(n for n in archive.namelist() if n.endswith('.vstpreset')):
            is_synth = 'Synthesizer V' in old
            new = 'Presets/Synths/Synthesizer V.vstpreset' if is_synth else f'Presets/Effects/FX{index:02}.vstpreset'
            renames[old] = new
            blob = archive.read(old)
            cleaned = preset(blob, synth=is_synth)
            if not is_synth:
                before = dict(daw.chunks(blob))[b'Comp']
                assert before == dict(daw.chunks(cleaned))[b'Comp']
                preserved.append(hashlib.sha256(before).hexdigest())
            output_files[new] = cleaned
        # Clear external preset browser links; embedded DSP state remains authoritative.
        for doc in docs.values():
            for parent in doc.iter():
                for node in list(parent):
                    if node.get('url', '').startswith('file:') and node.get('x_id') == 'url':
                        parent.remove(node)
            for node in doc.iter():
                for key, value in list(node.attrib.items()):
                    if value in renames: value = renames[value]
                    if value in labels: value = labels[value]
                    if key == 'pname': value = 'Starter'
                    if not value.isascii(): value = 'Default'
                    node.set(key, value)
                node.text = None; node.tail = None
        # Reset instance/track identifiers, preserving vendor plugin class IDs.
        ids = {}
        for doc in docs.values():
            for node in doc.iter():
                for key in ['trackID', 'mediaID', 'clipID']:
                    if node.get(key): ids[node.get(key)] = daw.uid()
                if node.tag == 'UID' and node.get('x_id') in ['uniqueID', 'channelID']:
                    ids[node.get('uid')] = daw.uid()
        for path, doc in docs.items():
            raw = daw.xmlbytes(doc)
            for old, new in ids.items(): raw = raw.replace(old.encode(), new.encode())
            output_files[path] = raw
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for path, raw in sorted(output_files.items()):
                entry = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0)); entry.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(entry, raw)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(buffer.getvalue())
    assert daw.sha(source) == source_hash, 'Source Song changed'
    return {'id': ident, 'name': name, 'bundle': output.name, 'sha256': daw.sha(output),
            'requiredPlugins': ['FabFilter Pro-Q 3', 'FabFilter Pro-C 2', 'FabFilter Pro-DS',
                                'FabFilter Pro-R 2', 'FabFilter Timeless 3'],
            'effectComponents': preserved,
            'warnings': ['Vocal Delay 返回默认静音；需要时自行启用。'] if any(
                c.get('label') == 'Vocal Delay' and c.get('mute') == '1' for c in daw.channels(mix)) else []}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--song', type=Path, required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.song, args.id, args.name, args.output), indent=2))
