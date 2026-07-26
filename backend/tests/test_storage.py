import subprocess

import pytest

from backend import storage


def test_migrate_storage_raises_when_rsync_fails(monkeypatch, tmp_path):
    old_path = tmp_path / "old"
    new_path = tmp_path / "new"
    old_path.mkdir()
    monkeypatch.setattr(storage, "ALLOWED_STORAGE_ROOTS", (str(tmp_path),))

    def fail_rsync(*args, **kwargs):
        raise subprocess.CalledProcessError(23, args[0])

    monkeypatch.setattr(storage.subprocess, "run", fail_rsync)

    with pytest.raises(subprocess.CalledProcessError):
        storage.migrate_storage(str(old_path), str(new_path))
