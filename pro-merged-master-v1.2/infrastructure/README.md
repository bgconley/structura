# Infrastructure artifacts

This directory contains implementation-facing infrastructure planning files.

## Contents

- `zfs/README.md`  
  Explains the storage layout and operational assumptions.
- `zfs/create_datasets.sh`  
  Idempotent ZFS dataset creation script.
- `zfs/dataset_matrix.csv`  
  One-row-per-dataset plan with mountpoints and tuning.
- `runtime_service_matrix.csv`  
  Service topology for the first Docker Compose deployment shape.

These files are intended to reduce ambiguity for an implementation agent. They are deliberately specific enough to code against, while still leaving room for minor operator adjustments during deployment.


Normative v1.3 runtime note: PGMQ is the preferred queue transport profile and Redis is only a documented fallback profile.
