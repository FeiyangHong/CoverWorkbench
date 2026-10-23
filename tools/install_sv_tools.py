"""Install SV scripts for this checkout without rewriting tracked sources."""
from pathlib import Path
import argparse, hashlib, json, shutil, time
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrations/sv'

def install(dest):
    dest=Path(dest).expanduser().resolve();dest.mkdir(parents=True,exist_ok=True)
    replacement=json.dumps(ROOT.as_posix()+'/',ensure_ascii=False)[1:-1]
    report=[]
    scripts=[('phrase-lyrics','CWPhraseLyrics'),('phrase-reuse','CWPhraseReuse'),('voice-presets','CWVoicePresets')]
    texts={name+'.lua':(SOURCE/'common.lua').read_text(encoding='utf-8')+'\n'+(SOURCE/(stem+'.body.lua')).read_text(encoding='utf-8') for stem,name in scripts}
    texts['CoverWorkbenchLive.lua']=(SOURCE/'CoverWorkbenchLive.lua').read_text(encoding='utf-8')
    for name,text in texts.items():
        text=text.replace('__CW_ROOT__/',replacement);target=dest/name
        if target.exists() and target.read_text(encoding='utf-8')!=text:
            backup=ROOT/'runtime/sv-script-backups'/str(time.time_ns());backup.mkdir(parents=True)
            shutil.copy2(target,backup/name)
        target.write_text(text,encoding='utf-8')
        report.append({'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    for folder in ['data/sv-phrases','data/sv-presets']:(ROOT/folder).mkdir(parents=True,exist_ok=True)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest',type=Path,action='append',required=True,help='SV script directory; repeat for both editors')
    args=parser.parse_args()
    print(json.dumps([row for dest in args.dest for row in install(dest)],ensure_ascii=True,indent=2))
