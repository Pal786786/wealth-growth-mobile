# My Funding Bank — Backup & Restore Guide

---

## 1. What is backed up

- Full MongoDB dump of the primary DB (`MONGO_DB_NAME`, default `mfb_prod`).
- Compressed via `gzip` (mongodump native + tar).
- Optionally encrypted with GPG symmetric AES-256.
- Uploaded to S3-compatible storage if configured.

Excluded by default (add to a separate playbook):
- Server-side `.env` files (secrets manager instead).
- Static assets under `/app/backend/static/` (rebuilt from images).

---

## 2. Schedule

- Default cron: `0 2 * * *` (02:00 UTC daily).
- Change via env `BACKUP_CRON` on the `backup` container.
- Retention: `BACKUP_RETENTION_DAYS` (default 30).

---

## 3. Storage locations

| Storage    | Configure                                                 |
|------------|----------------------------------------------------------|
| Local      | `BACKUP_STORAGE=local` (default) → files in `/backups`   |
| S3-compat  | `BACKUP_STORAGE=s3` + `S3_ENDPOINT`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_PREFIX` |

Works with: **AWS S3, Cloudflare R2, MinIO, DigitalOcean Spaces, Wasabi, Backblaze B2**.
If S3 credentials are missing while `BACKUP_STORAGE=s3`, the script logs a warning and keeps local backups — it does **not** fail.

---

## 4. Encryption

Set `BACKUP_ENCRYPT=true` and provide `BACKUP_ENCRYPT_PASSPHRASE` (≥32 chars). Files are written as `.tar.gz.gpg`.

---

## 5. Manual backup

```bash
docker compose -f deploy/docker-compose.prod.yml exec backup \
  /usr/local/bin/mongo_backup.sh
```

Or via the Admin panel (Sprint 12.3 provider dashboard has a **“Run Backup Now”** button that hits `POST /api/admin/backups/run`; wire it into the container by exec’ing this script server-side).

---

## 6. Restore

### From local file
```bash
docker compose -f deploy/docker-compose.prod.yml exec backup \
  /usr/local/bin/mongo_restore.sh /backups/mfb_mfb_prod_20260714T020000Z.tar.gz
```

### From S3
```bash
docker compose -f deploy/docker-compose.prod.yml exec backup \
  /usr/local/bin/mongo_restore.sh s3://mfb-backups/mfb-backups/mfb_mfb_prod_20260714T020000Z.tar.gz.gpg
```

### Danger mode (overwrite the target DB)
Only if you know what you’re doing:
```bash
docker compose -f deploy/docker-compose.prod.yml exec \
  -e DROP_BEFORE_RESTORE=true backup \
  /usr/local/bin/mongo_restore.sh /backups/<file>
```

---

## 7. Restore validation drill (quarterly)

1. Take the latest backup.
2. Restore into a scratch DB name: `RESTORE_DB_NAME=mfb_restore_check`.
3. Run these sanity checks:

```bash
mongosh mongodb://...:27017/mfb_restore_check --quiet --eval '
   const c = db.getCollectionNames();
   print("collections:", c.length);
   print("users:", db.users.estimatedDocumentCount());
   print("finance_journal:", db.finance_journal.estimatedDocumentCount());
'
```

4. Compare with production counts (delta < 5%).
5. Drop the scratch DB when done.

---

## 8. Backup manifest

Each successful run writes `/backups/latest.json`:

```json
{
  "timestamp": "20260714T020000Z",
  "db": "mfb_prod",
  "file": "mfb_mfb_prod_20260714T020000Z.tar.gz.gpg",
  "size": "1.4G",
  "encrypted": true,
  "storage": "s3"
}
```

Use this in the Admin backup history widget.

---

## 9. Troubleshooting

| Symptom                         | Fix                                                         |
|---------------------------------|-------------------------------------------------------------|
| `mongodump: authentication failed` | Verify `MONGO_URL` includes `?authSource=admin`         |
| `gpg: no valid OpenPGP data`     | Wrong passphrase / not encrypted – try without `.gpg`      |
| `aws s3 cp` denied               | Bucket policy or endpoint URL mismatch (R2 requires `--endpoint-url`) |
| Disk fills up                    | Reduce `BACKUP_RETENTION_DAYS` or enable S3 offload        |
| Cron not firing                  | `docker compose logs backup` — check `/etc/cron.d/mfb_backup` |
