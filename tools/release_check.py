"""Audit the tracked source boundary. Use --for-public-release to require a LICENSE."""
from pathlib import Path
import argparse
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--for-public-release', action='store_true')
    parser.add_argument('--ref', help='Audit every reachable commit and blob in this ref, rather than the working tree')
    args = parser.parse_args()
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().strip('\0').split('\0')
    errors = []
    blocked = {'data', 'projects', 'models', 'runtime', 'logs', 'reports', 'work', 'vendor', 'outputs', 'node_modules', '.venv'}
    private_extensions = {'.svp', '.song', '.vstpreset', '.wav', '.flac', '.mp3', '.mp4', '.lrc', '.srt', '.ckpt', '.pt', '.pth', '.safetensors', '.pem', '.key'}
    secret = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}|sk-proj-[A-Za-z0-9_-]{30,}')
    if args.ref:
        return audit_history(args.ref, args.for_public_release, blocked, private_extensions, secret)
    for name in paths:
        p = Path(name)
        if p.parts[0] in blocked or p.suffix.lower() in private_extensions or '.local.' in p.name or name == 'config/projects.json':
            errors.append('Private/generated file tracked: ' + name)
        if name.startswith('integrations/studio-one/') and p.name != 'README.md':
            errors.append('Proprietary host state tracked: ' + name)
        source = ROOT / p
        if not source.exists():
            continue
        if source.stat().st_size > 2_000_000:
            errors.append('Unexpected large tracked file: ' + name)
        try:
            text = source.read_text(encoding='utf-8-sig')
        except UnicodeError:
            continue
        if secret.search(text):
            errors.append('Potential credential in ' + name)  # Never print the candidate value.
        if re.search(r'[A-Za-z]:[/\\]Users[/\\](?!Public|Your|<|%)[0-9]{3,}[/\\]', text):
            errors.append('Personal home path in ' + name)
    titles = subprocess.check_output(['git', 'log', '--format=%s', 'HEAD'], cwd=ROOT).decode('utf-8').splitlines()
    pattern = re.compile(r'^\[(FEAT|FIX|DOCS|STYLE|REFACTOR|PERF|TEST|BUILD|CI|CHORE|REVERT)\]: [!-~][ -~]*$')
    for title in titles:
        if not pattern.fullmatch(title):
            errors.append('Non-English or invalid commit title')
    if args.for_public_release and not (ROOT / 'LICENSE').is_file():
        errors.append('Owner license selection is still pending; public release is blocked')
    if errors:
        print('\n'.join(errors));return 1
    print(f'PASS: {len(paths)} tracked paths, English commit titles, no matching credential or private-data paths')
    print('This is a bounded pattern audit, not a comprehensive security/legal review.')
    if not (ROOT / 'LICENSE').exists():
        print('Publication gate: LICENSE pending (use --for-public-release before publishing).')
    return 0


def audit_history(ref, require_license, blocked, private_extensions, secret):
    """Inspect immutable Git objects; ignored local files are never opened."""
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT)
    commits=git('rev-list', ref).decode().splitlines()
    if not commits:raise ValueError('No commits in publication ref')
    seen_blobs=set();seen_paths=set();errors=[]
    title_pattern=re.compile(r'^\[(FEAT|FIX|DOCS|STYLE|REFACTOR|PERF|TEST|BUILD|CI|CHORE|REVERT)\]: [!-~][ -~]*$')
    for commit in commits:
        title=git('show','-s','--format=%s',commit).decode('utf-8').rstrip('\n')
        if not title_pattern.fullmatch(title):errors.append('Invalid title in commit '+commit[:12])
        records=git('ls-tree','-rz','--full-tree',commit).split(b'\0')
        entries={}
        for record in filter(None,records):
            metadata,path=record.split(b'\t',1);mode,kind,oid=metadata.decode().split();name=path.decode('utf-8')
            entries[name]=(kind,oid)
            if name not in seen_paths:
                seen_paths.add(name);p=Path(name)
                ignored=subprocess.run(['git','check-ignore','--no-index','-q','--',name],cwd=ROOT).returncode==0
                if ignored or p.parts[0] in blocked or p.suffix.lower() in private_extensions or '.local.' in p.name:
                    errors.append('Excluded path in history: '+name)
                if kind!='blob':errors.append('Embedded repository in history: '+name)
            if kind!='blob' or oid in seen_blobs:continue
            seen_blobs.add(oid);raw=git('cat-file','blob',oid)
            if len(raw)>2_000_000:errors.append('Large blob in history: '+name)
            try:text=raw.decode('utf-8-sig')
            except UnicodeError:continue
            if secret.search(text):errors.append('Potential credential in history: '+name)
            if re.search(r'[A-Za-z]:[/\\]Users[/\\](?!Public|Your|<|%)[0-9]{3,}[/\\]',text):
                errors.append('Personal home path in history: '+name)
        if require_license and 'LICENSE' not in entries:errors.append('Missing LICENSE in commit '+commit[:12])
    if errors:
        print('\n'.join(sorted(set(errors))));return 1
    print(f'PASS: {len(commits)} commits, {len(seen_paths)} paths, {len(seen_blobs)} unique blobs audited')
    return 0


if __name__ == '__main__':
    sys.exit(main())
