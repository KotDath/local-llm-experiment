"""Convenience entry point for the actual VPS-side verification suite."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--mode', choices=['network', 'load', 'limits', 'overflow', 'final', 'all'], default='all')
    args = parser.parse_args()
    for mode in ['network', 'load', 'limits', 'overflow', 'final'] if args.mode == 'all' else [args.mode]:
        subprocess.run([sys.executable, str(ROOT / 'scripts/remote_checks.py'), mode, '--env-file', args.env_file], check=True)


if __name__ == '__main__':
    main()
