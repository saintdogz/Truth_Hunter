# Backup and Restore Runbook

Truth Hunter backups are PostgreSQL custom-format dumps encrypted with
AES-256-GCM before any dump bytes reach disk. The encryption key is derived with
PBKDF2-HMAC-SHA256 using a unique random salt for every backup. The authenticated
format rejects an incorrect key, corruption, and tampering.

## One-time configuration

Generate a unique key of at least 32 characters in PowerShell:

```powershell
$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToBase64String($bytes)
```

Copy the result into the private `.env` file:

```dotenv
BACKUP_ENCRYPTION_KEY=PASTE_THE_GENERATED_VALUE_HERE
BACKUP_RETENTION_DAYS=14
BACKUP_DIRECTORY=./backups
```

Store a second copy of `BACKUP_ENCRYPTION_KEY` in a password manager or other
offline secret store. Losing this key makes every encrypted backup permanently
unrecoverable. Never commit the key or paste it into logs, issues, or chat.

The default `backups` directory is excluded from Git and Docker build context.
Encrypted backups should also be copied to storage outside the server so a disk
failure or ransomware incident cannot destroy both the database and its backups.

## Create a backup

From `C:\OPENAI\Truth_Hunter`:

```powershell
.\scripts\backup.ps1
```

The command writes a file such as
`backups\truthhunter-20260827T175216Z.dump.enc`. It never writes a plaintext dump.
Only matching encrypted backup files older than `BACKUP_RETENTION_DAYS` are
pruned.

## Verify restoration

Verify the newest backup:

```powershell
.\scripts\verify-restore.ps1
```

Or select a specific filename:

```powershell
.\scripts\verify-restore.ps1 -BackupFile truthhunter-20260827T175216Z.dump.enc
```

The verifier refuses any target that does not end in `_restore_test`. It restores
into `truthhunter_restore_test`, compares user and investigation counts with the
live database, and removes the disposable database after success. It never
overwrites the production `truthhunter` database.

## Schedule daily backups on Windows

After a manual backup and restore verification both succeed, open PowerShell as
Administrator and register a daily 03:00 task:

```powershell
$taskName = "Truth Hunter Database Backup"
$script = "C:\OPENAI\Truth_Hunter\scripts\backup.ps1"
$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
  -WorkingDirectory "C:\OPENAI\Truth_Hunter"
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask `
  -TaskName $taskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Create the encrypted Truth Hunter PostgreSQL backup" `
  -RunLevel Highest
```

Confirm the task without waiting until 03:00:

```powershell
Start-ScheduledTask -TaskName "Truth Hunter Database Backup"
Start-Sleep -Seconds 30
Get-ScheduledTaskInfo -TaskName "Truth Hunter Database Backup"
Get-ChildItem .\backups\truthhunter-*.dump.enc |
  Sort-Object LastWriteTimeUtc -Descending |
  Select-Object -First 3 Name, Length, LastWriteTimeUtc
```

`LastTaskResult` should be `0`, and a new non-empty encrypted file should exist.

## Monthly recovery drill

At least monthly:

1. Confirm the scheduled task has recent successful runs.
2. Run `verify-restore.ps1` against the newest backup.
3. Confirm a recent encrypted copy exists outside this server.
4. Record the date, backup filename, and successful count comparison without
   recording the encryption key or personal data.

## Production disaster recovery

The automated verifier intentionally cannot overwrite production. In a real
disaster, preserve the failed database volume, create a fresh PostgreSQL target,
restore and verify the encrypted backup there, and only then switch application
traffic. Do not modify the restore safety suffix during an incident without a
separate reviewed recovery plan.
