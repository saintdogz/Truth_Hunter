"""Encrypted backup format and retention safety tests."""

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from tools.backup_tool import BackupError, decrypt_stream, encrypt_stream, prune_backups


def test_encrypted_stream_round_trip_hides_plaintext() -> None:
    plaintext = b"private truth hunter database content" * 100
    encrypted = io.BytesIO()

    encrypt_stream(io.BytesIO(plaintext), encrypted, b"a-secure-test-key-with-32-characters")

    assert plaintext not in encrypted.getvalue()
    decrypted = io.BytesIO()
    encrypted.seek(0)
    decrypt_stream(encrypted, decrypted, b"a-secure-test-key-with-32-characters")
    assert decrypted.getvalue() == plaintext


def test_tampered_backup_is_rejected() -> None:
    encrypted = io.BytesIO()
    secret = b"a-secure-test-key-with-32-characters"
    encrypt_stream(io.BytesIO(b"important"), encrypted, secret)
    damaged = bytearray(encrypted.getvalue())
    damaged[-17] ^= 1

    with pytest.raises(InvalidTag):
        decrypt_stream(io.BytesIO(damaged), io.BytesIO(), secret)


def test_retention_only_removes_matching_old_backups(tmp_path: Path) -> None:
    keep = tmp_path / "truthhunter-20260827T120000Z.dump.enc"
    old = tmp_path / "truthhunter-20260101T120000Z.dump.enc"
    unrelated = tmp_path / "notes.txt"
    for path in (keep, old, unrelated):
        path.write_bytes(b"data")
    old_time = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
    old.touch()
    import os

    os.utime(old, (old_time, old_time))

    assert prune_backups(tmp_path, 14, keep=keep) == 1
    assert keep.exists()
    assert unrelated.exists()
    assert not old.exists()


def test_restore_database_name_must_be_disposable(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.backup_tool import restore_backup

    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", "x" * 32)
    with pytest.raises(BackupError, match="_restore_test"):
        restore_backup(Path("truthhunter-20260827T120000Z.dump.enc"), "truthhunter")
