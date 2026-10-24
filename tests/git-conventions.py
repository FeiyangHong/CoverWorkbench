"""Read-only checks for commit titles and source/local-data repository boundaries."""
from pathlib import Path
import ast,json,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
def git(*args,**kwargs):
    return subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,**kwargs)
def main():
    checks={};(ROOT/'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='git-conventions-') as td:
        for title,valid in [('[FEAT]: Initialize the workbench',True),('[FIX]: Handle paths',True),('[DOCS]: Update documentation\n\n说明与验证。',True),('[FIX]: 修正路径',False),('fix: paths',False),('[fix]: paths',False),('[FIX]: ',False),('[OTHER]: paths',False),('[DOCS]:  extra space',False)]:
            p=Path(td)/'message';p.write_text(title+'\n',encoding='utf-8')
            result=git('hook','run','commit-msg','--',str(p))
            assert (result.returncode==0)==valid,(title,result.stderr)
    checks['commitTitleValidAndInvalidCases']=9
    samples=['config/project-assets.local.json','config/project-assets.local.previous.json','config/projects.json','config/video-links.local.json','config/video-links.local.previous.json','data/projects/hoshi.json','projects/studio-one/example/example.song','models/checkpoint.pt','runtime/server.pid','logs/server.log','reports/test.json','work/scratch.txt','vendor/GAME/infer.py','integrations/studio-one/sv2-host.json','assets/icons/preview.html','example.wav','.env']
    result=git('check-ignore','-z','--stdin',input=('\0'.join(samples)+'\0').encode())
    assert set(result.stdout.decode().strip('\0').split('\0'))==set(samples)
    checks['localAndGeneratedPathsIgnored']=len(samples)
    for rel in ['app/server.py','assets/icons/cw-signature.ico','config/projects.example.json','integrations/sv/CWPhraseLyrics.lua']:
        # --no-index keeps this check meaningful after the files are committed.
        assert git('check-ignore','--no-index',rel).returncode==1,rel
    checks['sourceAndProductAssetsIncluded']=True
    paths=[p for folder in ['app','tools','tests'] for p in (ROOT/folder).glob('*.py')]
    for p in paths:ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
    checks['pythonSourcesParsed']=len(paths)
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/git-setup-checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks))
if __name__=='__main__':main()
