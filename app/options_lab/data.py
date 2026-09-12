"""Bounded-memory CSV ingestion into source-fingerprinted daily partitions."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = 2
OPTION_RE = r'^([CP])-BTC-(\d+)-(\d{6})$'


def index_source(path: Path, cache: Path, progress):
    stat = path.stat()
    identity = dict(path=str(path.resolve()), bytes=stat.st_size, mtime_ns=stat.st_mtime_ns,
                    schema_version=SCHEMA_VERSION)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    dest = cache / key
    if (dest / 'manifest.json').exists():
        return dest, json.loads((dest / 'manifest.json').read_text())
    stage = cache / (key + '.building')
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    writers = {}
    quality = dict(raw_rows=0, valid_rows=0, invalid_rows=0, duplicate_rows=0,
                   duplicate_policy='Identical timestamp/symbol/price/size/role rows deduplicated within UTC day; no trade IDs supplied.')
    option = path.name.startswith('BTC_')
    try:
        # Categorical symbol strings are converted to plain Arrow strings for consistent batches.
        for chunk in pd.read_csv(path, chunksize=200_000, usecols=['timestamp','product_symbol','price','size','buyer_role']):
            progress(f'Indexing {path.name}: {quality["raw_rows"]:,} ticks read')
            quality['raw_rows'] += len(chunk)
            ts = pd.to_datetime(chunk.timestamp, format='mixed', utc=True, errors='coerce').astype('datetime64[ns, UTC]')
            price = pd.to_numeric(chunk.price, errors='coerce')
            size = pd.to_numeric(chunk['size'], errors='coerce')
            valid = ts.notna() & np.isfinite(price) & np.isfinite(size) & (price > 0) & (size > 0) & chunk.buyer_role.isin(['maker','taker'])
            if option:
                valid &= chunk.product_symbol.str.match(OPTION_RE, na=False)
            else:
                valid &= chunk.product_symbol.eq('BTCUSD')
            quality['invalid_rows'] += int((~valid).sum())
            frame = pd.DataFrame(dict(timestamp_ns=ts[valid].astype('int64'), symbol=chunk.product_symbol[valid].astype(str),
                                      price=price[valid].astype(float), size=size[valid].astype(float), role=chunk.buyer_role[valid].astype(str)))
            quality['valid_rows'] += len(frame)
            frame['day'] = ts[valid].dt.strftime('%Y-%m-%d')
            for day, rows in frame.groupby('day'):
                table = pa.Table.from_pandas(rows.drop(columns='day'), preserve_index=False)
                if day not in writers:
                    writers[day] = pq.ParquetWriter(stage / f'{day}.parquet', table.schema, compression='zstd')
                writers[day].write_table(table)
        for writer in writers.values():
            writer.close()
        writers.clear()
        coverage = []
        for p in sorted(stage.glob('*.parquet')):
            progress(f'Validating {path.name}: {p.stem}')
            frame = pd.read_parquet(p)
            count = len(frame)
            frame = frame.drop_duplicates().sort_values('timestamp_ns', kind='stable')
            quality['duplicate_rows'] += count - len(frame)
            frame.to_parquet(p, index=False, compression='zstd')
            coverage.append(dict(date=p.stem, rows=len(frame), first_ns=int(frame.timestamp_ns.min()), last_ns=int(frame.timestamp_ns.max())))
        digest = hashlib.sha256()
        with path.open('rb') as f:
            while block := f.read(8 * 1024 * 1024):
                digest.update(block)
                progress(f'Fingerprinting {path.name}')
        after = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f'{path.name} changed during ingestion; retry when the source is stable.')
        manifest = dict(**identity, sha256=digest.hexdigest(), quality=quality, days=coverage)
        (stage / 'manifest.json').write_text(json.dumps(manifest))
        if dest.exists():
            shutil.rmtree(dest)
        stage.rename(dest)
        return dest, manifest
    except BaseException:
        for writer in writers.values():
            writer.close()
        shutil.rmtree(stage, ignore_errors=True)
        raise


def load_day(folder, day):
    path = folder / f'{day}.parquet'
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()
