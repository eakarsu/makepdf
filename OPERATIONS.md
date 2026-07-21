# Operations runbook

## Deploy

1. Provision an encrypted durable volume and secret-manager values from
   `.env.example`. Set exact hosts/origins and production malware scanning.
2. Build and scan the pinned image. Run `./start.sh check` in the release image.
3. Start the worker and API. `/ready` becomes healthy after a recent worker
   heartbeat. Keep at least two API processes and monitor queue age/retries.
4. Create rotating stored user keys with the bootstrap administrator, verify
   roles, then remove or vault the bootstrap credential.

## Backup and restore

Use SQLite's online backup API, never a plain copy of a live WAL database:

```sh
scripts/backup.sh /encrypted-backups/makepdf-YYYYMMDD.sqlite3
scripts/restore-verify.sh /restore-drill/makepdf.sqlite3
```

The backup command refuses overwrite and produces a checksum manifest. Restore
verification checks SQLite integrity, required tables, and the entire audit
hash chain. A real drill must also restore the matching object volume, compare
stored source/result checksums, boot an isolated API/worker pair, download a
representative result, record RPO/RTO, and destroy the drill copy. Schedule a
monthly automated backup and quarterly witnessed restore.

## Incident response

Disable intake, revoke affected API/provider keys, retain database/object/log
evidence under documented legal authority, and record the affected tenants and
time range. Do not delete held evidence. Patch and validate in an isolated
environment, rotate download signing keys if exposure is suspected, notify the
designated privacy/security owners, and restore only after audit-chain and
object-checksum verification.

## Retention and deletion

The default result retention is 24 hours and document retention is seven days.
Tenant administrators can apply legal hold. Deletion cancels associated work,
removes source/result objects, and leaves non-content audit evidence. Storage
media sanitization and backup expiry are infrastructure responsibilities.
