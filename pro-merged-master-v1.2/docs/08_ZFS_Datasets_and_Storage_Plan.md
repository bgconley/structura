# ZFS datasets and storage plan

## 1. Storage principles

- separate database files from object artifacts
- separate mutable runtime state from reproducible code
- use recordsize appropriate to workload
- turn atime off
- prefer compression on all datasets unless there is a strong reason not to
- avoid dangerous shortcuts like `sync=disabled` on durable data

## 2. Recommended root

Assume a pool name such as `tank` and application root `tank/structura`.

Mount root dataset at `/srv/structura`.

## 3. Recommended datasets

### `tank/structura/postgres`
Purpose: PostgreSQL data  
Mountpoint: `/srv/structura/postgres`  
Recommended properties:
- recordsize=8K
- compression=lz4
- atime=off

### `tank/structura/objects-canonical`
Purpose: immutable original document bytes  
Mountpoint: `/srv/structura/objects/canonical`  
Recommended properties:
- recordsize=1M
- compression=zstd-3
- atime=off

### `tank/structura/objects-derived`
Purpose: Docling JSON, markdown, HTML, page renders, thumbnails, and normalized extraction artifacts  
Mountpoint: `/srv/structura/objects/derived`  
Recommended properties:
- recordsize=1M
- compression=zstd-3
- atime=off

### `tank/structura/objects-exports`
Purpose: user export bundles and ad hoc packages  
Mountpoint: `/srv/structura/objects/exports`  
Recommended properties:
- recordsize=1M
- compression=zstd-6
- atime=off

### `tank/structura/models`
Purpose: downloaded local models and quantizations  
Mountpoint: `/srv/structura/models`  
Recommended properties:
- recordsize=1M
- compression=zstd-1
- atime=off

### `tank/structura/staging`
Purpose: temporary ingest and conversion workspace  
Mountpoint: `/srv/structura/staging`  
Recommended properties:
- recordsize=1M
- compression=lz4
- atime=off

### `tank/structura/cache`
Purpose: thumbnails, transient page renders, queue caches, temporary artifacts  
Mountpoint: `/srv/structura/cache`  
Recommended properties:
- recordsize=128K
- compression=lz4
- atime=off

### `tank/structura/repo`
Purpose: local git checkout if stored on the pool  
Mountpoint: `/srv/structura/repo`  
Recommended properties:
- recordsize=128K
- compression=zstd-1
- atime=off

### `tank/structura/config`
Purpose: runtime config, env files, local scripts  
Mountpoint: `/srv/structura/config`  
Recommended properties:
- recordsize=128K
- compression=zstd-1
- atime=off

### `tank/structura/logs`
Purpose: application logs  
Mountpoint: `/srv/structura/logs`  
Recommended properties:
- recordsize=128K
- compression=lz4
- atime=off

### `tank/structura/backups`
Purpose: DB dumps, bundle exports, backup copies  
Mountpoint: `/srv/structura/backups`  
Recommended properties:
- recordsize=1M
- compression=zstd-6
- atime=off

### `tank/structura/redis` (optional fallback only)
Purpose: Redis persistence if the fallback queue profile is enabled  
Mountpoint: `/srv/structura/redis`  
Recommended properties:
- recordsize=16K
- compression=lz4
- atime=off

### `tank/structura/observability`
Purpose: Prometheus, Grafana, Loki data if used  
Mountpoint: `/srv/structura/observability`  
Recommended properties:
- recordsize=128K
- compression=lz4
- atime=off

## 4. Optional datasets

- `tank/structura/minio` if an S3-compatible object store is used later
- `tank/structura/venv` if local non-container Python environments are desired
- `tank/structura/notebooks` if private local evaluation notebooks are used

## 5. Snapshot policy suggestion

- frequent snapshots for `postgres`
- less frequent but regular snapshots for `objects-canonical`, `objects-derived`, and `objects-exports`
- daily or weekly snapshots for `models`
- backup retention tuned to actual available space

A simple starting point:
- `postgres`: hourly for 48h, daily for 30d, weekly for 8w
- `objects-canonical`: daily for 30d, weekly for 12w
- `objects-derived`: daily for 30d, weekly for 12w
- `objects-exports`: daily for 14d, weekly for 8w, or lifecycle-managed per export policy
- `config`: daily for 30d
- `backups`: as capacity allows

## 6. Object storage layout recommendation

Use content-addressed directory structures under the purpose-specific object roots:

```text
/srv/structura/objects/canonical/sha256/ab/cd/<hash>/...
/srv/structura/objects/derived/sha256/ab/cd/<hash>/...
/srv/structura/objects/exports/<export-id>/...
```

Within each content hash directory, store files by role. Original bytes belong under `objects/canonical`; derivatives belong under `objects/derived`; exports belong under `objects/exports`.

Immutable original files include:
- original PDF

Derivative files include:
- normalized PDF
- page images
- thumbnails
- docling.json
- extraction JSON

Export files include:
- export bundles

The DB remains the catalog. The filesystem remains the blob store.

## 7. Encryption note

Because the dataset may contain medical, financial, and legal records, ZFS native encryption or full-disk encryption is strongly recommended if operationally feasible.

## 8. Runtime mounts

Mount these datasets directly into containers rather than writing durable data to anonymous volumes.

See:
- `infrastructure/zfs/create_datasets.sh`
- `infrastructure/zfs/dataset_matrix.csv`
