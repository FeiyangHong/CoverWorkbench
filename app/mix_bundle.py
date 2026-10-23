"""Validate the narrow, media-free format used for public starter mix assets."""
import hashlib
import io
import json
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

XML_FILES = {'metainfo.xml', 'settings.xml', 'Song/song.xml', 'Song/mediapool.xml',
             'Devices/transportdevice.xml', 'Devices/audiomixer.xml',
             'Devices/audiosynthfolder.xml', 'Devices/musictrackdevice.xml'}
CLASSES = {b'72C4DB717A4D459AB97E51745D84B39D', b'79F415E3C8E74807AD5DA3CF7024F618',
           b'59E324D08EE811E1B8578101BBE59B18', b'6070873C802A4B078FC06AB5459154E9',
           b'D2EE67F2C552402D902115931AFDAE6B', b'ABCDEF019182FAEB44746E6353565232'}


def validate(raw, metadata=None):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 40:
            raise ValueError('Duplicate or excessive starter mix entries')
        if sum(item.file_size for item in archive.infolist()) > 500_000:
            raise ValueError('Starter mix exceeds the uncompressed size limit')
        if not XML_FILES.issubset(names):
            raise ValueError('Missing starter mix document')
        components = []
        synths = 0
        docs = {}
        for name in names:
            data = archive.read(name)
            if name in XML_FILES:
                text = data.decode('ascii')
                node = ET.fromstring(text.replace('x:id', 'x_id'))
                docs[name] = node
                for item in node.iter():
                    if item.tag in ['AutomationRegion', 'MusicEvent', 'NoteEvent']:
                        raise ValueError('Song content in starter mix')
                    for key, value in item.attrib.items():
                        if key in ['machineID', 'deviceName', 'userName', 'author']:
                            raise ValueError('Personal device metadata in starter mix')
                        if key == 'url' and value not in [
                            'file:///C:/CoverWorkbench/Template/instrumental.wav',
                            'file:///C:/CoverWorkbench/Template/template.song',
                            'file:///C:/CoverWorkbench/Template/Mixdown/']:
                            raise ValueError('Non-placeholder resource in starter mix')
                        if key == 'text' and value.startswith('Presets/') and value not in names:
                            raise ValueError('Missing embedded starter preset')
                        if re.search(r'(?<![A-Za-z])[A-Za-z]:[/\\]', value) and not value.startswith('file:///C:/CoverWorkbench/Template/'):
                            raise ValueError('Personal absolute path in starter mix')
                continue
            if not re.fullmatch(r'Presets/(Effects/FX\d{2}|Synths/Synthesizer V)\.vstpreset', name):
                raise ValueError('Unexpected starter mix attachment')
            if data[:4] != b'VST3' or data[8:40] not in CLASSES:
                raise ValueError('Unsupported starter plugin class')
            offset = struct.unpack_from('<Q', data, 40)[0]
            if data[offset:offset + 4] != b'List':
                raise ValueError('Invalid starter preset index')
            chunks = {}
            count = struct.unpack_from('<I', data, offset + 4)[0]
            if count != 3:
                raise ValueError('Unexpected starter preset chunks')
            for index in range(count):
                tag, start, size = struct.unpack_from('<4sQQ', data, offset + 8 + index * 20)
                if start < 48 or start + size > offset or tag in chunks:
                    raise ValueError('Invalid starter preset chunk range')
                chunks[tag] = data[start:start + size]
            if set(chunks) != {b'Comp', b'Cont', b'Info'} or chunks[b'Cont']:
                raise ValueError('Unexpected controller metadata in starter preset')
            if '/Synths/' in name:
                synths += 1
                state = json.loads(chunks[b'Comp'])
                if state != {'projectPath': '', 'sessionConfiguration': {'channelLayout': 536870930}, 'araBridgeEnabled': False}:
                    raise ValueError('Nonempty SV project in starter mix')
            else:
                if chunks[b'Comp'][:4] not in (b'FFBS', b'FabF'):
                    raise ValueError('Unexpected effect component format')
                components.append(hashlib.sha256(chunks[b'Comp']).hexdigest())
        if synths != 1:
            raise ValueError('Starter mix needs one empty SV host')
        meta = {node.get('id'): node.get('value') for node in docs['metainfo.xml']}
        if meta.get('Document:Creator') != 'CoverWorkbench' or any(
                key.startswith('Media:Artist') for key in meta):
            raise ValueError('Unexpected starter authorship metadata')
        events = list(docs['Song/song.xml'].iter('AudioEvent'))
        if len(events) != 1 or events[0].get('length') != '1' or events[0].get('name') != 'Instrumental':
            raise ValueError('Starter mix must contain only its placeholder audio event')
        if metadata and (hashlib.sha256(raw).hexdigest() != metadata['sha256'] or
                         components != metadata['effectComponents']):
            raise ValueError('Starter mix checksum or effect-component mismatch')
    return {'effects': len(components), 'files': len(names)}
