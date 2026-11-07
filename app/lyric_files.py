"""Readable, versioned lyric packages and downloads; no generated timestamps or IDs."""
from pathlib import Path
from urllib.parse import quote
import re
from windows_names import generated
from core import save_json
import media_names
import workspaces


def allocate(p):
    root=workspaces.outputs(p);parent=root/'working/lyrics';parent.mkdir(parents=True,exist_ok=True)
    number=1
    while True:
        folder=parent/f'Lyrics {number:03}'
        try:folder.mkdir();break
        except FileExistsError:number+=1
    return folder


def lrc(rows, key):
    lines=[]
    for row in rows:
        if row.get('start') is None or not row.get(key):continue
        centis=round(max(0,row['start'])*100);minute,rest=divmod(centis,6000);second,cs=divmod(rest,100)
        for line in str(row[key]).splitlines():lines.append(f'[{minute:02}:{second:02}.{cs:02}]{line}')
    return '\n'.join(lines)+'\n' if lines else ''


def export(p,result,folder,revision=None,raw=None):
    output=workspaces.outputs(p)/'exports/lyrics';output.mkdir(parents=True,exist_ok=True)
    label=' - '.join(filter(None,[p.get('artist'),p['title'],folder.name]))+(f' - Revision {revision:03}' if revision else '')
    entries=[]
    def write(role,title,text,extension):
        if not text.strip():return
        target=output/generated(media_names.filename(label,''),' - '+title+extension)
        if target.exists():raise ValueError('歌词版本文件已存在，原文件保留，请重新整理')
        target.write_text(text,encoding='utf-8-sig')
        entries.append({'role':role,'label':{'reading':'原文＋罗马音 TXT','original':'原文 '+extension[1:].upper(),'translation':'译文 '+extension[1:].upper(),'romaji':'罗马音 '+extension[1:].upper(),'bilingual':'双语 LRC'}[role],'file':str(target),'url':f"/download/{p['id']}/{quote(target.name)}"})
    rows=result['rows'];timed=result['timed']
    write('reading','Reading','\n\n'.join('\n'.join(str(r.get(k,'')) for k in ['original','romaji','translation'] if r.get(k)) for r in rows)+'\n','.txt')
    for role in ['original','translation','romaji']:
        text=((raw or {}).get(role) or None) if not revision else None
        if text is None:text=lrc(rows,role) if timed else '\n'.join(str(r.get(role,'')) for r in rows if r.get(role))+'\n'
        extension='.lrc' if timed and re.search(r'\[\d+:\d',text) else '.txt'
        write(role,role.title(),text,extension)
    if timed and any(r.get('translation') for r in rows):
        write('bilingual','Bilingual',lrc([{**r,'both':r['original']+'\n'+r.get('translation','')} for r in rows],'both'),'.lrc')
    result.update(exports=entries,outputDirectory=str(output),batch=folder.name)
    record=folder/(f'Reading {revision:03}.json' if revision else 'Lines.json')
    result['recordFile']=str(record);save_json(record,result)
    return result
