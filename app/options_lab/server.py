from __future__ import annotations

import csv
import io
import json
import mimetypes
import threading
import traceback
import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
WEB = Path(__file__).parent / 'web'
RUNS = ROOT / 'outputs/options_lab/runs'
JOBS = {}
LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=1)
DATA_ROOT = Path.home() / 'Desktop/BitcoinFNOData'


def catalog():
    months = []
    for p in sorted((DATA_ROOT / 'options_data').glob('BTC_*.csv')):
        month = p.stem[4:]
        future = DATA_ROOT / 'futures_data' / f'BTCUSD_{month}.csv'
        months.append(dict(month=month, option_bytes=p.stat().st_size,
                           future_bytes=future.stat().st_size if future.exists() else 0,
                           paired=future.exists()))
    return dict(root=str(DATA_ROOT), months=months, bytes=sum(m['option_bytes'] + m['future_bytes'] for m in months),
                schema=['product_symbol', 'price', 'size', 'timestamp', 'buyer_role'],
                kind='Trade prints · no order book · futures underlying proxy')


def persist(job):
    RUNS.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in job.items() if k != 'cancel'}
    temp = RUNS / (job['id'] + '.tmp')
    temp.write_text(json.dumps(clean, allow_nan=False), encoding='utf-8')
    temp.replace(RUNS / (job['id'] + '.json'))


def worker(job):
    from app.options_lab.engine import run_experiment
    try:
        job.update(status='running', started_at=datetime.now(timezone.utc).isoformat())
        started = time.monotonic()
        def progress(message, fraction):
            if job['cancel'].is_set():
                raise InterruptedError('Cancelled. Completed results are retained only after a full run.')
            job.update(message=message, progress=max(job.get('progress',0),round(fraction,4)), elapsed_seconds=round(time.monotonic()-started,1))
        result = run_experiment(job['request'], DATA_ROOT, ROOT / 'data/options_lab_cache', progress)
        job.update(status='completed', result=result, progress=1, message='Research run complete',
                   elapsed_seconds=round(time.monotonic()-started, 3))
    except InterruptedError as exc:
        job.update(status='cancelled', message=str(exc))
    except Exception as exc:
        traceback.print_exc()
        job.update(status='failed', message=str(exc))
    finally:
        with LOCK:
            if job['id'] in JOBS:
                persist(job)


def delete_runs(ids=None):
    """Remove finished history reversibly; active workers cannot be deleted."""
    with LOCK:
        ids=list(JOBS) if ids is None else ids
        ids=[id for id in ids if id in JOBS and JOBS[id]['status'] not in ('queued','running')]
        trash=RUNS.parent/'deleted_runs'
        trash.mkdir(parents=True,exist_ok=True)
        for id in ids:
            source=RUNS/(id+'.json')
            if source.exists():source.replace(trash/(id+'.json'))
            del JOBS[id]
        return {'deleted':ids,'active_runs_kept':sum(j['status'] in ('queued','running') for j in JOBS.values())}


class Handler(BaseHTTPRequestHandler):
    def respond(self, data, status=200, content_type='application/json', download=None):
        body = data if isinstance(data, bytes) else json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if download:
            self.send_header('Content-Disposition', f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == '/api/health':
                return self.respond({'application': 'options-lab', 'status': 'ready'})
            if path == '/api/presets/strangle-20-delta':
                return self.respond(json.loads((Path(__file__).parent / 'presets/strangle-20-delta.json').read_text()))
            if path == '/api/presets/one-btc-example':
                return self.respond(json.loads((Path(__file__).parent / 'presets/one-btc-example.json').read_text()))
            if path == '/api/presets':
                from .ideas import strategy_library
                return self.respond(strategy_library())
            if path == '/api/catalog':
                return self.respond(catalog())
            if path == '/api/runs':
                return self.respond([{k: j.get(k) for k in ('id', 'created', 'status', 'message', 'request', 'progress')}
                                     for j in sorted(JOBS.values(), key=lambda x: x['created'], reverse=True)])
            if path.startswith('/api/runs/'):
                parts = path.split('/')
                job = JOBS.get(parts[3])
                if not job:
                    return self.respond({'error': 'Run not found'}, 404)
                if len(parts) == 5 and parts[4] == 'trades.csv':
                    result = job.get('result', {})
                    variants = result.get('runs', [])
                    try:
                        variant = int(parse_qs(urlparse(self.path).query).get('variant', [result.get('selected_index', 0)])[0])
                    except (ValueError, TypeError):
                        return self.respond({'error': 'Invalid variant'}, 400)
                    if not 0 <= variant < len(variants):
                        return self.respond({'error': 'This result variant is unavailable'}, 400)
                    rows = variants[variant].get('trades', [])
                    flat = [{k: v for k, v in row.items() if not isinstance(v, (list, dict))} for row in rows]
                    for row, exported in zip(rows, flat):
                        for i, leg in enumerate(row.get('legs', []), 1):
                            for key in ('symbol', 'side', 'quantity_btc', 'strike', 'expiry'):
                                exported[f'leg_{i}_{key}'] = leg[key]
                            for key, value in leg['greeks'].items():
                                exported[f'leg_{i}_{key}'] = value
                    out = io.StringIO()
                    if flat:
                        writer = csv.DictWriter(out, fieldnames=list(dict.fromkeys(k for r in flat for k in r)))
                        writer.writeheader()
                        writer.writerows(flat)
                    return self.respond(out.getvalue().encode(), content_type='text/csv', download=f'options-trades-variant-{variant+1}.csv')
                clean = {k: v for k, v in job.items() if k != 'cancel'}
                if job['status']=='running' and job.get('started_at'):
                    clean['elapsed_seconds']=round((datetime.now(timezone.utc)-datetime.fromisoformat(job['started_at'])).total_seconds(),1)
                return self.respond(clean, download=f"{job['id']}.json" if path.endswith('/export') else None)
            static = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/favicon.svg': 'favicon.svg', '/guide': 'guide.html', '/methodology': 'methodology.html'}
            if path in static:
                p = WEB / static[path]
                return self.respond(p.read_bytes(), content_type=mimetypes.guess_type(p.name)[0] or 'text/plain')
            return self.respond({'error': 'Not found'}, 404)
        except Exception as exc:
            self.respond({'error': str(exc)}, 500)

    def do_POST(self):
        # Only the loopback UI can create work. No permissive CORS or arbitrary paths/code.
        origin = self.headers.get('Origin')
        expected_host = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected_host or (origin and origin != f'http://{expected_host}'):
            return self.respond({'error': 'Origin rejected'}, 403)
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.respond({'error': 'JSON required'}, 415)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > 100_000 or length <= 0:
                raise ValueError('Invalid request size')
            payload = json.loads(self.rfile.read(length))
            if self.path in ('/api/runs/delete', '/api/runs/clear'):
                return self.respond(delete_runs(None if self.path.endswith('/clear') else [payload.get('id')]))
            if self.path == '/api/runs':
                from app.options_lab.engine import validate_request
                request = validate_request(payload)
                with LOCK:
                    if any(j['status'] in ('queued', 'running') for j in JOBS.values()):
                        return self.respond({'error': 'A run is active. Cancel or wait before starting another.'}, 409)
                    job = dict(id=uuid.uuid4().hex[:12], created=datetime.now(timezone.utc).isoformat(),
                               status='queued', message='Queued', progress=0, request=request, cancel=threading.Event())
                    JOBS[job['id']] = job
                    persist(job)
                    POOL.submit(worker, job)
                return self.respond({'id': job['id']}, 202)
            if self.path.endswith('/cancel'):
                job = JOBS.get(self.path.split('/')[3])
                if not job:
                    raise ValueError('Unknown run')
                job['cancel'].set()
                return self.respond({'status': 'cancellation requested'})
            self.respond({'error': 'Not found'}, 404)
        except (ValueError, TypeError, KeyError) as exc:
            self.respond({'error': str(exc)}, 400)


def serve(port, data_root):
    global DATA_ROOT
    DATA_ROOT = data_root.resolve()
    RUNS.mkdir(parents=True, exist_ok=True)
    for path in RUNS.glob('*.json'):
        try:
            job = json.loads(path.read_text())
            job['cancel'] = threading.Event()
            if job['status'] in ('queued', 'running'):
                job.update(status='interrupted', message='Server stopped before this run completed; rerun the configuration.')
            JOBS[job['id']] = job
        except (ValueError, KeyError):
            continue
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Options Lab ready at http://127.0.0.1:{port}', flush=True)
    server.serve_forever()
