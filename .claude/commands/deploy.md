Review all uncommitted changes, commit them with a clear message, and push to GitHub.

After pushing, remind the user to run these commands on the Linux server:

```bash
cd /folio/folio_migration_web
git pull
sudo systemctl restart folio-migration-web
```

Also remind them to check the service status with:
```bash
sudo systemctl status folio-migration-web
```
