"""Copy handoff assets and known native dependencies without changing originals."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import copy
import html
import json
import re
import shutil
import struct
import zipfile

from core import read_json, save_json, sha
import daw

AUDIO = {'.wav', '.flac', '.mp3', '.m4a', '.aif', '.aiff', '.ogg'}
ROLES = {'source': ('source', 'Original'), 'vocals': ('separation/imported', 'Vocals'),
         'lead': ('separation/imported', 'Lead'), 'harmony': ('separation/imported', 'Harmony'),
         'accompaniment': ('separation/imported', 'Instrumental'), 'mix': ('exports/audio', 'Final Mix')}
SV_IDS = {b'ABCDEF019182FAEB44746E6353565232', b'ABCDEF019182FAEB44746E6353565332'}


def local_reference(value, base):
    value = daw.clean_path(value)
    if value.startswith('file:'):
        parsed = urlsplit(value)
        if parsed.netloc:
            raise ValueError('暂不收纳网络文件引用：' + value)
        value = unquote(parsed.path)
        if re.match(r'^/[A-Za-z]:', value):
            value = value[1:]
    path = Path(value)
    if value.startswith(('\\\\', '//')):
        raise ValueError('暂不收纳网络文件引用：' + value)
    return (path if path.is_absolute() else base / path).resolve()


def sv_references(doc, base):
    if isinstance(doc, dict):
        for key, value in doc.items():
            if key in ('filename', 'filePath', 'path') and isinstance(value, str) and Path(value).suffix.lower() in AUDIO:
                yield local_reference(value, base)
            else:
                yield from sv_references(value, base)
    elif isinstance(doc, list):
        for value in doc:
            yield from sv_references(value, base)


class Import:
    """One registry update: rollback only newly created, workspace-owned outputs."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.created = []
        self.sources = {}
        self.copied = self.reused = 0
        self.done = False

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if not self.done:
            for path in reversed(self.created):
                path = path.resolve()
                if path != self.root and path.is_relative_to(self.root):
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink(missing_ok=True)

    def check(self):
        for source, digest in self.sources.items():
            if not source.is_file() or sha(source) != digest:
                raise ValueError('源文件在收纳期间改变，请保存后重试：' + str(source))

    def remember(self, source):
        digest = sha(source)
        if source in self.sources and self.sources[source] != digest:
            raise ValueError('源文件在收纳期间改变：' + str(source))
        self.sources[source] = digest
        return digest

    def owned(self, path):
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('项目子目录指向外部位置，请先选择项目内目录：' + str(path))
        return path

    def audio(self, source, parent, label):
        source = Path(source).resolve()
        if source.is_relative_to(self.root):
            self.reused += 1
            return source
        before = self.remember(source)
        self.owned(parent).mkdir(parents=True, exist_ok=True)
        number = 1
        while True:
            dest = parent / (label + (f'_v{number}' if number > 1 else '') + source.suffix.lower())
            # Resolve symlinks before trusting an existing destination.
            if dest.exists():
                if dest.resolve().is_relative_to(self.root) and dest.is_file() and sha(dest) == before:
                    self.reused += 1
                    return dest.resolve()
            else:
                try:
                    with dest.open('xb') as stream:
                        self.created.append(dest)
                        with source.open('rb') as original:
                            shutil.copyfileobj(original, stream, 1024 * 1024)
                    if sha(dest) != before:
                        raise ValueError('复制校验失败：' + str(source))
                    self.copied += 1
                    return dest
                except FileExistsError:
                    pass
            number += 1

    def sv_document(self, source, doc, media):
        """Keep notes/voices/curves intact; relocate audio and render output only."""
        result = copy.deepcopy(doc)
        mapping = {}
        def walk(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ('filename', 'filePath', 'path') and isinstance(value, str) and Path(value).suffix.lower() in AUDIO:
                        path = local_reference(value, source.parent)
                        if not path.is_file():
                            raise ValueError('SVP 参考音频缺失：' + str(path))
                        if path not in mapping:
                            mapping[path] = self.audio(path, media, 'Reference' + (f' {len(mapping) + 1:02}' if mapping else ''))
                        obj[key] = str(mapping[path])
                    else:
                        walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value)
        walk(result)
        result.setdefault('renderConfig', {})['destination'] = str(self.root / 'exports/audio')
        return result

    def bundle(self, source, role):
        source = Path(source).resolve()
        if source.is_relative_to(self.root) and self.self_contained(source, role):
            self.reused += 1
            return source
        before = self.remember(source)
        sv = role == 'svp'
        doc = read_json(source) if sv else None
        parent = self.root / ('working/sv2' if sv and doc.get('version', 0) >= 190 else 'working/sv' if sv else 'studio-one')
        label = 'Imported SV' if sv else 'Imported Mix'
        self.owned(parent).mkdir(parents=True, exist_ok=True)
        number = 1
        while True:
            folder = parent / f'{label} {number:02}'
            manifest = folder / 'import.json'
            if manifest.is_file():
                try:
                    old = read_json(manifest)
                except (ValueError, OSError):
                    old = {}
                files = old.get('files', [])
                if (old.get('source') == str(source) and old.get('sourceSHA256') == before and files
                        and folder.resolve().is_relative_to(self.root)
                        and Path(old['output']).resolve().is_relative_to(folder.resolve())
                        and all(Path(f['path']).resolve().is_relative_to(self.root) and Path(f['path']).is_file() and sha(f['path']) == f['sha256'] for f in files)
                        and all(Path(f['path']).is_file() and sha(f['path']) == f['sha256'] for f in old.get('dependencies', []))):
                    for item in old.get('dependencies', []):
                        self.remember(Path(item['path']))
                    self.reused += 1
                    return Path(old['output'])
            try:
                folder.mkdir()
                self.created.append(folder)
                break
            except FileExistsError:
                number += 1
        output = folder / ('project.svp' if sv else 'Project.song')
        if sv:
            save_json(output, self.sv_document(source, doc, folder / 'Media'))
        else:
            self.song(source, output)
        files = [{'path': str(f), 'sha256': sha(f)} for f in folder.rglob('*') if f.is_file()]
        save_json(manifest, {'source': str(source), 'sourceSHA256': before, 'output': str(output),
                            'files': files, 'dependencies': [{'path': str(f), 'sha256': h} for f, h in self.sources.items()]})
        self.copied += 1
        return output

    def self_contained(self, source, role):
        """An internal document may still link outside: fork it rather than edit it."""
        if role == 'svp':
            return all(p.is_file() and p.is_relative_to(self.root) for p in sv_references(read_json(source), source.parent))
        try:
            with zipfile.ZipFile(source) as archive:
                names = set(archive.namelist())
                for entry in archive.infolist():
                    if entry.file_size > 100_000_000:
                        return False
                    if entry.filename.endswith('.xml'):
                        for value in re.findall(r'''\burl\s*=\s*["']([^"']*)["']''', archive.read(entry).decode('utf-8-sig')):
                            value = html.unescape(value)
                            parsed = urlsplit(value)
                            if parsed.scheme not in ('file', 'media', '') or not value:
                                continue
                            if parsed.scheme == 'media':
                                relative = unquote(parsed.path).lstrip('/')
                                if relative in names or 'Media/' + relative in names:
                                    continue
                                candidates = [source.parent / relative, source.parent / 'Media' / relative]
                                path = next((p.resolve() for p in candidates if p.is_file()), candidates[0].resolve())
                            else:
                                path = local_reference(value, source.parent)
                            if not path.is_relative_to(self.root) or (not value.endswith('/') and not path.is_file()):
                                return False
                    elif entry.filename.endswith('.vstpreset'):
                        data = archive.read(entry)
                        if data[:4] == b'VST3' and data[8:40] in SV_IDS:
                            for tag, payload in daw.chunks(data):
                                if tag != b'Comp':
                                    continue
                                state, _ = json.JSONDecoder().raw_decode(payload.decode('utf-8'))
                                if state.get('projectPath'):
                                    path = local_reference(state['projectPath'].replace('\\\\', '\\'), source.parent)
                                    if not path.is_file() or not path.is_relative_to(self.root) or not self.self_contained(path, 'svp'):
                                        return False
            return True
        except zipfile.BadZipFile:
            return False

    def song(self, source, output):
        """Retarget explicit Song URLs and SV host links; preserve other plugin state."""
        try:
            archive = zipfile.ZipFile(source)
        except zipfile.BadZipFile as error:
            raise ValueError('不是可读取的 Studio One 工程；可选择仅引用原路径') from error
        with archive:
            entries = archive.infolist()
            names = {i.filename for i in entries}
            if len(names) != len(entries) or sum(i.file_size for i in entries) > 512_000_000:
                raise ValueError('Song 内部路径重复或解压内容过大，无法安全收纳')
            mapping = {source: output}
            def dependency(path):
                if path in mapping:
                    return mapping[path]
                if not path.is_file():
                    raise ValueError('Song 依赖缺失：' + str(path) + '；请先在 Studio One 中归集外部文件')
                self.remember(path)
                if path.suffix.lower() == '.svp':
                    target = output.parent / f'SV {len(mapping):02}' / 'project.svp'
                    save_json(target, self.sv_document(path, read_json(path), target.parent / 'Media'))
                    self.copied += 1
                else:
                    label = re.sub(r'[^A-Za-z0-9 _.-]', '_', path.stem).strip(' ._')[:70] or 'Asset'
                    target = self.audio(path, output.parent / 'Media', label)
                mapping[path] = target
                return target
            def replace_url(match):
                value = html.unescape(match.group(2))
                parsed = urlsplit(value)
                if parsed.scheme not in ('file', 'media', '') or not value:
                    return match.group(0)
                if parsed.scheme == 'media':
                    relative = unquote(parsed.path).lstrip('/')
                    if relative in names or 'Media/' + relative in names:
                        return match.group(0)
                    candidates = [source.parent / relative, source.parent / 'Media' / relative]
                    path = next((p.resolve() for p in candidates if p.is_file()), candidates[0].resolve())
                else:
                    path = local_reference(value, source.parent)
                # Output directories are not input dependencies; do not copy directory trees.
                if value.endswith('/') or path.name.lower() == 'mixdown':
                    if path.name.lower() not in ('mixdown', 'exports'):
                        raise ValueError('无法自动收纳目录引用：' + value + '；请先在 Studio One 中归集外部文件')
                    target = output.parent / 'Mixdown'
                    target.mkdir(exist_ok=True)
                else:
                    target = dependency(path)
                return match.group(1) + html.escape(target.as_uri(), quote=True) + ('/' if value.endswith('/') else '') + match.group(3)
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as dest:
                for entry in entries:
                    data = archive.read(entry)
                    if entry.filename.endswith('.xml'):
                        text = data.decode('utf-8-sig')
                        data = re.sub(r'''(\burl\s*=\s*["'])([^"']*)(["'])''', replace_url, text).encode('utf-8')
                    elif entry.filename.endswith('.vstpreset') and data[:4] == b'VST3' and data[8:40] in SV_IDS:
                        result = []
                        for tag, payload in daw.chunks(data):
                            if tag == b'Comp':
                                text = payload.decode('utf-8')
                                state, end = json.JSONDecoder().raw_decode(text)
                                linked = state.get('projectPath')
                                if linked:
                                    target = dependency(local_reference(linked.replace('\\\\', '\\'), source.parent))
                                    state['projectPath'] = str(target).replace('\\', '\\\\') if '\\\\' in linked else str(target)
                                    payload = (json.dumps(state, ensure_ascii=True) + text[end:]).encode()
                            result.append((tag, payload))
                        payload = b''
                        records = []
                        for tag, chunk in result:
                            records.append((tag, 48 + len(payload), len(chunk)))
                            payload += chunk
                        data = data[:40] + struct.pack('<Q', 48 + len(payload)) + payload + b'List' + struct.pack('<I', len(records)) + b''.join(struct.pack('<4sQQ', *r) for r in records)
                    dest.writestr(entry, data)

    def asset(self, source, role):
        if role in ('svp', 'song'):
            return self.bundle(source, role)
        parent, label = ROLES[role]
        return self.audio(source, self.root / parent, label)
