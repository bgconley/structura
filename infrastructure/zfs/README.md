# ZFS deployment notes

This application is sensitive to both data integrity and performance. The storage layout therefore separates database, object storage, staging, cache, models, logs, backups, and optional local virtual environments into distinct datasets.

## Goals

- tune record sizes by workload rather than using one-size-fits-all defaults
- snapshot and replicate data classes independently
- avoid mixing mutable caches with durable source-of-truth data
- preserve canonical document bytes separately from derived artifacts
- keep Postgres on a small-record dataset aligned with database page behavior

## Default mountpoint root

`/srv/structura`

## Recommended operator policy

- enable ZFS native encryption if the pool is not already encrypted
- keep `atime=off`
- keep `sync=standard`; do not use `sync=disabled` for Postgres
- snapshot durable datasets on a regular schedule
- back up `postgres`, `objects-canonical`, `objects-derived`, `config`, and `repo`
- do not treat `cache` or `tmp` as backup targets
- use quotas later if multi-user support is added

## Files in this directory

- `create_datasets.sh` creates the datasets
- `create_gpu_runtime_datasets.sh` creates the GPU-node runtime dataset tree under `/srv/structura` while preserving the host convention of `/tank/repos/structura` for source and `/tank/venvs` for virtualenvs; writable API/worker/model paths are owned by container UID `10001` with host group `bgconley`
- `dataset_matrix.csv` documents the dataset plan in tabular form
