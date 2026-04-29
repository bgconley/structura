#!/usr/bin/env bash
set -euo pipefail

# GPU-node Structura runtime dataset bootstrap.
#
# This script intentionally creates only the application runtime datasets under
# /srv/structura. It does not create tank/structura/repo or tank/structura/venv
# because the active GPU-node convention is:
#
#   source checkout: /tank/repos/structura
#   virtualenv root: /tank/venvs
#
# Run on the GPU node with sudo:
#
#   sudo infrastructure/zfs/create_gpu_runtime_datasets.sh
#
# Optional arguments:
#
#   sudo infrastructure/zfs/create_gpu_runtime_datasets.sh tank /srv/structura bgconley 10001

POOL="${1:-tank}"
ROOT="${2:-/srv/structura}"
HOST_GROUP="${3:-bgconley}"
APP_UID="${4:-10001}"
BASE_DATASET="${POOL}/structura"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "error: run this script with sudo or as root" >&2
    exit 1
  fi
}

require_pool() {
  if ! zpool list -H -o name "${POOL}" >/dev/null 2>&1; then
    echo "error: ZFS pool '${POOL}' does not exist" >&2
    exit 1
  fi
}

create_or_update_ds() {
  local dataset="$1"
  local mountpoint="$2"
  local recordsize="$3"
  local compression="$4"

  if zfs list -H -o name "${dataset}" >/dev/null 2>&1; then
    echo "exists  ${dataset}"
  else
    echo "create  ${dataset}"
    zfs create -p "${dataset}"
  fi

  zfs set "mountpoint=${mountpoint}" "${dataset}"
  zfs set "recordsize=${recordsize}" "${dataset}"
  zfs set "compression=${compression}" "${dataset}"
  zfs set "atime=off" "${dataset}"
  zfs set "sync=standard" "${dataset}"
  zfs mount "${dataset}" >/dev/null 2>&1 || true
}

create_app_dirs() {
  install -d -m 0755 \
    "${ROOT}/objects" \
    "${ROOT}/config/api" \
    "${ROOT}/config/web" \
    "${ROOT}/logs/api" \
    "${ROOT}/logs/workers" \
    "${ROOT}/logs/models" \
    "${ROOT}/logs/observability" \
    "${ROOT}/observability/prometheus" \
    "${ROOT}/observability/grafana"

  # API, worker, and model containers run as UID 10001 from apps/api/Dockerfile.
  # Keep bgconley as the group so the operator can inspect and repair files.
  chown -R "${APP_UID}:${HOST_GROUP}" \
    "${ROOT}/objects" \
    "${ROOT}/models" \
    "${ROOT}/staging" \
    "${ROOT}/cache" \
    "${ROOT}/logs" \
    "${ROOT}/tmp"
  chmod -R u+rwX,g+rwX,o-rwx \
    "${ROOT}/objects" \
    "${ROOT}/models" \
    "${ROOT}/staging" \
    "${ROOT}/cache" \
    "${ROOT}/logs" \
    "${ROOT}/tmp"
  find \
    "${ROOT}/objects" \
    "${ROOT}/models" \
    "${ROOT}/staging" \
    "${ROOT}/cache" \
    "${ROOT}/logs" \
    "${ROOT}/tmp" \
    -type d -exec chmod g+s {} +

  chown -R "bgconley:${HOST_GROUP}" \
    "${ROOT}/config" \
    "${ROOT}/observability"
}

print_existing_state() {
  echo "Preflight state:"
  zpool list "${POOL}"
  echo
  zfs list -r "${POOL}" || true
  echo
}

print_result() {
  echo
  echo "Structura runtime datasets:"
  zfs list -o name,mountpoint,recordsize,compression,atime,sync "${BASE_DATASET}" "${BASE_DATASET}"/*
  echo
  echo "Host convention preserved:"
  echo "  repo checkout: /tank/repos/structura"
  echo "  venv root:     /tank/venvs"
  echo
  echo "Docker image storage was not changed. Existing Docker root should be verified with:"
  echo "  docker info --format '{{.DockerRootDir}}'"
}

require_root
require_pool
print_existing_state

echo "Using pool: ${POOL}"
echo "Using runtime root: ${ROOT}"
echo "Using app container UID for writable runtime dirs: ${APP_UID}"
echo "Using host operator group for writable runtime dirs: ${HOST_GROUP}"
echo

create_or_update_ds "${BASE_DATASET}" "${ROOT}" 128K lz4
create_or_update_ds "${BASE_DATASET}/postgres" "${ROOT}/postgres" 8K lz4
create_or_update_ds "${BASE_DATASET}/redis" "${ROOT}/redis" 16K lz4
create_or_update_ds "${BASE_DATASET}/objects-canonical" "${ROOT}/objects/canonical" 1M zstd-3
create_or_update_ds "${BASE_DATASET}/objects-derived" "${ROOT}/objects/derived" 1M zstd-3
create_or_update_ds "${BASE_DATASET}/objects-exports" "${ROOT}/objects/exports" 1M zstd-6
create_or_update_ds "${BASE_DATASET}/models" "${ROOT}/models" 1M zstd-1
create_or_update_ds "${BASE_DATASET}/staging" "${ROOT}/staging" 1M lz4
create_or_update_ds "${BASE_DATASET}/cache" "${ROOT}/cache" 128K lz4
create_or_update_ds "${BASE_DATASET}/config" "${ROOT}/config" 128K zstd-1
create_or_update_ds "${BASE_DATASET}/logs" "${ROOT}/logs" 128K lz4
create_or_update_ds "${BASE_DATASET}/backups" "${ROOT}/backups" 1M zstd-6
create_or_update_ds "${BASE_DATASET}/observability" "${ROOT}/observability" 128K lz4
create_or_update_ds "${BASE_DATASET}/tmp" "${ROOT}/tmp" 128K lz4

create_app_dirs
print_result
