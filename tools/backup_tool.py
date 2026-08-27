"""Encrypted PostgreSQL backup and disposable restore tooling."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"THBK1"
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
KDF_ITERATIONS = 600_000
CHUNK_BYTES = 1024 * 1024
BACKUP_PATTERN = re.compile(r"^truthhunter-\d{8}T\d{6}Z\.dump\.enc$")
RESTORE_DATABASE_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*_restore_test$")


class BackupError(RuntimeError):
    """Raised when backup or restore cannot complete safely."""


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise BackupError(f"{name} is required")
    return value


def _encryption_key() -> bytes:
    value = _required_env("BACKUP_ENCRYPTION_KEY")
    if len(value) < 32:
        raise BackupError("BACKUP_ENCRYPTION_KEY must contain at least 32 characters")
    return value.encode("utf-8")


def _derive_key(secret: bytes, salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=KDF_ITERATIONS
    ).derive(secret)


def encrypt_stream(source: BinaryIO, destination: BinaryIO, secret: bytes) -> None:
    """Encrypt a stream with AES-256-GCM and an authenticated format header."""
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    header = MAGIC + salt + nonce
    encryptor = Cipher(algorithms.AES(_derive_key(secret, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    destination.write(header)
    while chunk := source.read(CHUNK_BYTES):
        destination.write(encryptor.update(chunk))
    destination.write(encryptor.finalize())
    destination.write(encryptor.tag)


def decrypt_stream(source: BinaryIO, destination: BinaryIO, secret: bytes) -> None:
    """Authenticate and decrypt a Truth Hunter backup stream."""
    header_size = len(MAGIC) + SALT_BYTES + NONCE_BYTES
    header = source.read(header_size)
    if len(header) != header_size or not header.startswith(MAGIC):
        raise BackupError("Backup format is invalid")
    salt = header[len(MAGIC) : len(MAGIC) + SALT_BYTES]
    nonce = header[-NONCE_BYTES:]
    source.seek(0, os.SEEK_END)
    total_size = source.tell()
    if total_size < header_size + TAG_BYTES:
        raise BackupError("Backup is truncated")
    source.seek(total_size - TAG_BYTES)
    tag = source.read(TAG_BYTES)
    source.seek(header_size)
    remaining = total_size - header_size - TAG_BYTES
    decryptor = Cipher(algorithms.AES(_derive_key(secret, salt)), modes.GCM(nonce, tag)).decryptor()
    decryptor.authenticate_additional_data(header)
    while remaining:
        chunk = source.read(min(CHUNK_BYTES, remaining))
        if not chunk:
            raise BackupError("Backup is truncated")
        remaining -= len(chunk)
        destination.write(decryptor.update(chunk))
    destination.write(decryptor.finalize())


def _connection_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PGPASSWORD"] = _required_env("POSTGRES_PASSWORD")
    return environment


def _database_args(database: str) -> list[str]:
    return [
        "--host",
        os.environ.get("DB_HOST", "postgres"),
        "--port",
        os.environ.get("DB_PORT", "5432"),
        "--username",
        os.environ.get("POSTGRES_USER", "truthhunter"),
        "--dbname",
        database,
    ]


def prune_backups(directory: Path, retention_days: int, *, keep: Path) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    for candidate in directory.iterdir():
        if (
            candidate == keep
            or not candidate.is_file()
            or not BACKUP_PATTERN.fullmatch(candidate.name)
        ):
            continue
        modified = datetime.fromtimestamp(candidate.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            candidate.unlink()
            removed += 1
    return removed


def create_backup(directory: Path, retention_days: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = directory / f"truthhunter-{timestamp}.dump.enc"
    partial = destination.with_suffix(destination.suffix + ".partial")
    database = os.environ.get("POSTGRES_DB", "truthhunter")
    command = [
        "pg_dump",
        *_database_args(database),
        "--format=custom",
        "--no-owner",
        "--no-privileges",
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_connection_environment()
    )
    assert process.stdout is not None
    try:
        with partial.open("wb") as encrypted:
            encrypt_stream(process.stdout, encrypted, _encryption_key())
        stderr = process.communicate()[1]
        if process.returncode:
            raise BackupError(stderr.decode("utf-8", errors="replace").strip())
        partial.replace(destination)
    except Exception:
        process.kill()
        process.wait()
        partial.unlink(missing_ok=True)
        raise
    removed = prune_backups(directory, retention_days, keep=destination)
    print(f"Created encrypted backup: {destination.name}; pruned: {removed}")
    return destination


def restore_backup(source: Path, target_database: str) -> None:
    if not RESTORE_DATABASE_PATTERN.fullmatch(target_database):
        raise BackupError("Restore target must end with _restore_test")
    if not BACKUP_PATTERN.fullmatch(source.name) or not source.is_file():
        raise BackupError("Select an existing Truth Hunter encrypted backup")
    source_database = os.environ.get("POSTGRES_DB", "truthhunter")
    if target_database == source_database:
        raise BackupError("Refusing to overwrite the source database")
    environment = _connection_environment()
    admin_args = _database_args("postgres")
    subprocess.run(
        ["dropdb", *admin_args[:-2], "--if-exists", "--force", target_database],
        check=True,
        env=environment,
    )
    subprocess.run(["createdb", *admin_args[:-2], target_database], check=True, env=environment)
    restore = subprocess.Popen(
        [
            "pg_restore",
            *_database_args(target_database),
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    assert restore.stdin is not None
    try:
        with source.open("rb") as encrypted:
            decrypt_stream(encrypted, restore.stdin, _encryption_key())
        restore.stdin.close()
        stderr = restore.stderr.read() if restore.stderr is not None else b""
        return_code = restore.wait()
        if return_code:
            raise BackupError(stderr.decode("utf-8", errors="replace").strip())
    except Exception:
        restore.kill()
        restore.wait()
        subprocess.run(
            ["dropdb", *admin_args[:-2], "--if-exists", "--force", target_database],
            check=False,
            env=environment,
        )
        raise
    print(f"Restored and authenticated backup into: {target_database}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("--directory", type=Path, default=Path("/backups"))
    backup.add_argument(
        "--retention-days",
        type=int,
        default=int(os.environ.get("BACKUP_RETENTION_DAYS", "14")),
    )
    restore = subparsers.add_parser("restore")
    restore.add_argument("source", type=Path)
    restore.add_argument("--target-database", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.command == "backup":
            if args.retention_days < 1 or args.retention_days > 365:
                raise BackupError("Retention must be between 1 and 365 days")
            create_backup(args.directory, args.retention_days)
        else:
            restore_backup(args.source, args.target_database)
    except (BackupError, OSError, subprocess.SubprocessError) as exc:
        print(f"Backup operation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
