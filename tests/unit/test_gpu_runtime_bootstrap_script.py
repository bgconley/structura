from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path


def _write_fake_zfs(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls.log"
    zfs = fake_bin / "zfs"
    zfs.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            echo "$@" >> {calls}
            if [[ "$1 $2 $3 $4" == "list -H -o name" ]]; then
              echo "$5"
              exit 0
            fi
            if [[ "$1 $2 $3 $4" == "get -H -o value" ]]; then
              case "$5" in
                mountpoint) echo "/srv/structura" ;;
                recordsize) echo "128K" ;;
                compression) echo "lz4" ;;
                atime) echo "off" ;;
                sync) echo "standard" ;;
                mounted) echo "yes" ;;
                *) echo "-" ;;
              esac
              exit 0
            fi
            exit 0
            """
        )
    )
    zfs.chmod(0o755)
    return fake_bin, calls


def test_gpu_runtime_bootstrap_does_not_reapply_current_mountpoint(tmp_path: Path) -> None:
    fake_bin, calls = _write_fake_zfs(tmp_path)
    script = Path("infrastructure/zfs/create_gpu_runtime_datasets.sh").resolve()
    command = f"source {script}; create_or_update_ds tank/structura /srv/structura 128K lz4"

    subprocess.run(
        ["bash", "-lc", command],
        check=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "STRUCTURA_ZFS_BOOTSTRAP_SOURCE_ONLY": "1",
        },
        text=True,
        capture_output=True,
    )

    recorded_calls = calls.read_text()
    assert "set mountpoint=/srv/structura tank/structura" not in recorded_calls
    assert "mount tank/structura" not in recorded_calls


def test_gpu_runtime_bootstrap_prints_dataset_tree_without_shell_glob(tmp_path: Path) -> None:
    fake_bin, calls = _write_fake_zfs(tmp_path)
    script = Path("infrastructure/zfs/create_gpu_runtime_datasets.sh").resolve()
    command = f"source {script}; print_result"

    subprocess.run(
        ["bash", "-lc", command],
        check=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "STRUCTURA_ZFS_BOOTSTRAP_SOURCE_ONLY": "1",
        },
        text=True,
        capture_output=True,
    )

    recorded_calls = calls.read_text()
    assert "tank/structura/*" not in recorded_calls
    assert (
        "list -r -d 1 -o name,mountpoint,recordsize,compression,atime,sync tank/structura"
        in recorded_calls
    )
