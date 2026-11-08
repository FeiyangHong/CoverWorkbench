"""Read-only comparison reports and an explicit media allowlist."""
from pathlib import Path
from core import ROOT,read_json

def listing():
    file=ROOT/'runtime/pymss/Comparisons.json'
    return read_json(file) if file.is_file() else []

def report(ident):
    row=next((x for x in listing() if x['id']==ident),None)
    if not row:raise ValueError('未找到模型对比工程')
    root=Path(row['folder']).resolve()
    if not root.is_relative_to((ROOT/'projects').resolve()):raise ValueError('对比目录不在工作台项目目录内')
    return root,read_json(root/'analysis/Benchmark.json')

def media(ident,key):
    root,doc=report(ident)
    paths={}
    for song in doc['songs']:
        paths[song['id']+'/original']=song['original']
    for row in doc['results']:
        if row.get('inputAudio'):paths[row['song']+'/'+row['modelId']+'/input']=row['inputAudio']
        for kind,items in [('raw',row.get('outputs',{})),('matched',row.get('matched',{}))]:
            for role,value in items.items():paths[row['song']+'/'+row['modelId']+'/'+kind+'/'+role]=value
    if key not in paths:raise ValueError('未登记的试听文件')
    result=(root/paths[key]).resolve()
    if not result.is_relative_to(root) or result.suffix.lower()!='.wav' or not result.is_file():raise ValueError('试听文件不存在')
    return result
