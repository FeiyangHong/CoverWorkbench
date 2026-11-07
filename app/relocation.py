"""Retarget project references without rebuilding unrelated native plugin state."""
from pathlib import Path
import json,os,struct,zipfile
import daw,asset_storage

def replacements(mapping):
    pairs=[]
    for old,new in mapping.items():
        if old.startswith('/download/'):
            pairs.append((old,new));continue
        for a,b in [(old,new),(old.replace('\\','\\\\'),new.replace('\\','\\\\')),(Path(old).as_posix(),Path(new).as_posix()),(Path(old).as_uri(),Path(new).as_uri())]:
            if a!=b:pairs.append((a,b))
    pairs=sorted(set(pairs),key=lambda row:-len(row[0]))
    def text(value):
        for a,b in pairs:value=value.replace(a,b)
        return value
    def document(value):
        if isinstance(value,str):return text(value)
        if isinstance(value,list):return [document(x) for x in value]
        if isinstance(value,dict):return {text(k):document(v) for k,v in value.items()}
        return value
    return text,document


def preset(blob,transform):
    if blob[:4]!=b'VST3' or blob[8:40] not in asset_storage.SV_IDS:return blob
    chunks=[]
    for tag,data in daw.chunks(blob):
        if tag==b'Comp':
            raw=data.decode('utf-8');state,end=json.JSONDecoder().raw_decode(raw);changed=transform(state)
            if state!=changed:data=(json.dumps(changed,ensure_ascii=True)+raw[end:]).encode()
        chunks.append((tag,data))
    payload=b'';records=[]
    for tag,data in chunks:records.append((tag,48+len(payload),len(data)));payload+=data
    return blob[:40]+struct.pack('<Q',48+len(payload))+payload+b'List'+struct.pack('<I',len(records))+b''.join(struct.pack('<4sQQ',*r) for r in records)


def patch(path,text,document):
    suffix=path.suffix.lower();before=path.read_bytes();after=before
    if not before:return False  # Some model caches intentionally use empty .json marker files.
    if suffix in ('.json','.svp'):
        raw=before.decode('utf-8-sig');padding=len(raw)-len(raw.rstrip('\x00'))
        obj=json.loads(raw.rstrip('\x00'));updated=document(obj)
        if obj!=updated:after=(json.dumps(updated,ensure_ascii=False,indent=2)+'\n'+'\x00'*padding).encode()
    elif suffix=='.vstpreset':after=preset(before,document)
    elif suffix in ('.song','.songtemplate'):
        import io
        buffer=io.BytesIO();changed=False
        with zipfile.ZipFile(io.BytesIO(before)) as source,zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as dest:
            for entry in source.infolist():
                data=source.read(entry);new=text(data.decode('utf-8-sig')).encode() if entry.filename.endswith('.xml') else preset(data,document) if entry.filename.endswith('.vstpreset') else data
                changed|=new!=data;dest.writestr(entry,new)
        if changed:after=buffer.getvalue()
    elif suffix in ('.toml','.xml','.txt','.md','.log','.py','.ps1','.vbs','.bat','.ffconcat'):
        try:after=text(before.decode('utf-8')).encode()
        except UnicodeDecodeError:pass
    if before!=after:
        stat=path.stat();path.write_bytes(after);os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        return True
    return False
