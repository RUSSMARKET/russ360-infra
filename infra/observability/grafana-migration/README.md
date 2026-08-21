# Grafana SQLite → PostgreSQL

The production migration was rehearsed against a consistent SQLite snapshot
before cutover. The migrator is pinned to commit
`4cad6353cd3bc0056c50b1c407218dcba3bae445` and patched because upstream replaced
LogQL backticks inside `alert_rule.data`, producing invalid JSON while still
reporting a successful migration. `sanitize_test.go` prevents that regression.

The old `grafana_data` volume and timestamped SQLite snapshot under
`../.backups/` are deliberately retained. To roll back without deleting
PostgreSQL data:

```bash
docker compose -f compose.yml -f compose.scrape.yml \
  -f compose.sqlite-rollback.yml up -d --no-deps grafana
```

After migration verify at minimum:

- `/api/health` reports `database: ok`;
- provisioning logs contain `finished to provision alerting`;
- SQLite and PostgreSQL counts match for `annotation`, `alert_rule`,
  `alert_rule_version`, `dashboard`, `data_source`, and `user`;
- all `alert_rule.data` values are valid JSON;
- all Prometheus targets are up and the Telegram bot sees only one lifecycle
  for each active alert.
