#!/usr/bin/env python3
"""Launch the local options workbench. Raw data stays on this computer."""
import argparse
import sys
import json
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.options_lab.server import serve

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-root', type=Path, default=Path.home() / 'Desktop/BitcoinFNOData')
    parser.add_argument('--open', action='store_true', help='Open the browser, or reuse a running Options Lab.')
    args = parser.parse_args()
    if args.open:
        url = f'http://127.0.0.1:{args.port}'
        try:
            with urllib.request.urlopen(url + '/api/health', timeout=2) as response:
                if json.load(response).get('application') == 'options-lab':
                    webbrowser.open(url)
                    print(f'Opened the running Options Lab at {url}')
                    sys.exit(0)
        except (urllib.error.URLError, ValueError):
            pass
        opener = threading.Timer(1.0, lambda: webbrowser.open(url))
        opener.daemon = True
        opener.start()
    serve(args.port, args.data_root)
