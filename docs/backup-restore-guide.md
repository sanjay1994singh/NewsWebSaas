# Backup and Restore Guide

Back up:

- MySQL database with `mysqldump` or physical backups.
- Media storage directory.
- Production `.env` through a secure secrets manager.

Restore:

1. Provision the same application version.
2. Restore `.env` secrets securely.
3. Restore MySQL.
4. Restore media files.
5. Run migrations.
6. Run integrity checks and tenant isolation smoke tests.

Retention should include daily short-term backups and longer weekly/monthly retention based on business policy.
