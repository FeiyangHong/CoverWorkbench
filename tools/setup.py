"""Initialize an empty installation without copying personal pilot records."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import settings

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Report dependencies without creating project data')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11 or later is required.')
    if not args.check:
        settings.initialize()
    print(json.dumps(settings.status(), ensure_ascii=True, indent=2))

if __name__ == '__main__':
    main()
