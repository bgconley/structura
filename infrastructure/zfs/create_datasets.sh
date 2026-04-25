#!/usr/bin/env bash
set -euo pipefail

POOL="${1:-tank}"
ROOT="${2:-/srv/structura}"
BASE_DATASET="${POOL}/structura"

create_ds() {
  local dataset="$1"
  local mountpoint="$2"
  shift 2

  if zfs list -H "${dataset}" >/dev/null 2>&1; then
    echo "exists  ${dataset}"
  else
    echo "create  ${dataset}"
    zfs create -o "mountpoint=${mountpoint}" "$@" "${dataset}"
  fi
}

echo "Using pool: ${POOL}"
echo "Using root mountpoint: ${ROOT}"

create_ds "${BASE_DATASET}" "${ROOT}"   -o compression=lz4   -o atime=off

create_ds "${BASE_DATASET}/postgres" "${ROOT}/postgres"   -o recordsize=8K   -o compression=lz4   -o atime=off   -o sync=standard

# Optional fallback profile only:
# create_ds "${BASE_DATASET}/redis" "${ROOT}/redis"   -o recordsize=16K   -o compression=lz4   -o atime=off

create_ds "${BASE_DATASET}/objects-canonical" "${ROOT}/objects/canonical"   -o recordsize=1M   -o compression=zstd-3   -o atime=off

create_ds "${BASE_DATASET}/objects-derived" "${ROOT}/objects/derived"   -o recordsize=1M   -o compression=zstd-3   -o atime=off

create_ds "${BASE_DATASET}/objects-exports" "${ROOT}/objects/exports"   -o recordsize=1M   -o compression=zstd-6   -o atime=off

create_ds "${BASE_DATASET}/models" "${ROOT}/models"   -o recordsize=1M   -o compression=zstd-1   -o atime=off

create_ds "${BASE_DATASET}/staging" "${ROOT}/staging"   -o recordsize=1M   -o compression=lz4   -o atime=off

create_ds "${BASE_DATASET}/cache" "${ROOT}/cache"   -o recordsize=128K   -o compression=lz4   -o atime=off

create_ds "${BASE_DATASET}/repo" "${ROOT}/repo"   -o recordsize=128K   -o compression=zstd-1   -o atime=off

create_ds "${BASE_DATASET}/venv" "${ROOT}/venv"   -o recordsize=128K   -o compression=zstd-1   -o atime=off

create_ds "${BASE_DATASET}/config" "${ROOT}/config"   -o recordsize=128K   -o compression=zstd-1   -o atime=off

create_ds "${BASE_DATASET}/logs" "${ROOT}/logs"   -o recordsize=128K   -o compression=lz4   -o atime=off

create_ds "${BASE_DATASET}/backups" "${ROOT}/backups"   -o recordsize=1M   -o compression=zstd-6   -o atime=off

create_ds "${BASE_DATASET}/observability" "${ROOT}/observability"   -o recordsize=128K   -o compression=lz4   -o atime=off

create_ds "${BASE_DATASET}/tmp" "${ROOT}/tmp"   -o recordsize=128K   -o compression=lz4   -o atime=off

echo
echo "ZFS datasets prepared under ${BASE_DATASET}"
echo "Recommended next steps:"
echo "  1. Consider enabling or confirming pool/dataset encryption."
echo "  2. Set snapshot schedules for postgres, objects-canonical, objects-derived, config, and repo."
echo "  3. Mount these paths into Docker Compose services."
echo "  4. Keep sync=standard for Postgres."
