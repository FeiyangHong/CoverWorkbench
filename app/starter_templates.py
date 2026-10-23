"""Media-free bundled mixing recipes, materialized only in ignored runtime storage."""
from pathlib import Path
from html import escape
import hashlib
import io
import json
import threading
import zipfile
from mix_bundle import validate

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets/studio-one'
LOCK = threading.RLock()
PLACEHOLDER = b'file:///C:/CoverWorkbench/Template/'


def entries():
    index = ASSETS / 'index.json'
    return json.loads(index.read_text(encoding='utf-8')) if index.exists() else []


def resolve(ident):
    row = next((row for row in entries() if row['id'] == ident), None)
    if row is None:
        return None
    raw = (ASSETS / row['bundle']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ValueError('Bundled mix template checksum mismatch')
    validate(raw, row)
    folder = ROOT / 'runtime/starter-templates' / row['id']
    song = folder / 'template.song'
    buffer = io.BytesIO()
    prefix = escape('file:///' + folder.as_posix().lstrip('/') + '/', quote=True).encode()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.endswith('.xml'):
                data = data.replace(PLACEHOLDER, prefix)
            target.writestr(item, data)
    with LOCK:
        folder.mkdir(parents=True, exist_ok=True)
        data = buffer.getvalue()
        if not song.exists() or song.read_bytes() != data:
            temp = song.with_suffix('.tmp')
            temp.write_bytes(data)
            temp.replace(song)
    return {**row, 'originalSong': str(song), 'bundled': True}
