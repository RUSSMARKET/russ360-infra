# Rusaifin transport diagnostics

Production-only diagnostics for intermittent Safari/iOS loading failures on
`fintech.rusaifin.ru`. The API vhost `server.rusaifin.ru` is included for
same-session correlation. Other sites on the shared host do not opt in.

## What is collected

- Structured nginx access records without query strings or referrers.
- Rolling five-minute Prometheus aggregates via node_exporter textfile collector.
- Up to 50 client-IP-scoped packet captures after an iPhone/iPad HTML navigation.
- A pre-Nuxt iOS bootstrap signal for a same-origin Nuxt resource error or an
  eight-second mount timeout.

The bootstrap signal posts to one of two fixed, bodyless paths. It never sends
the page URL, query string, failed resource name, browser-storage contents or a
user identifier. At most one pending event is kept in local storage for 24
hours so a failed same-origin delivery can be retried after the next reload.

Packet captures use snaplen 96 and TLS remains encrypted. The capture watcher
never starts from traffic on another vhost: it learns the client IP from a
completed `fintech.rusaifin.ru` HTML access record. It captures for 90 seconds,
has a five-minute per-IP cooldown and a maximum of four concurrent captures.
There is no automatic deletion; review and explicitly remove captures later.

## Production paths

- `/etc/nginx/conf.d/rusaifin-netdiag-log-format.conf`
- `/home/fintech/conf/web/fintech.rusaifin.ru/nginx.ssl.conf_rusaifin_netdiag`
- `/home/fintech/conf/web/server.rusaifin.ru/nginx.ssl.conf_rusaifin_netdiag`
- `/home/fintech/conf/web/fintech.rusaifin.ru/nginx.ssl.conf_rusaifin_bootstrap_netdiag`
- `/var/log/rusaifin-netdiag/access.jsonl`
- `/var/log/rusaifin-netdiag/error.log`
- `/var/log/rusaifin-netdiag/pcap/`
- `/usr/local/sbin/rusaifin-netdiag-metrics`
- `/usr/local/sbin/rusaifin-iphone-capture`

The persistent fintech `nginx.ssl.conf_nuxt` include contains an additional
diagnostic `access_log` directive because a location-level access log does not
inherit the server-level diagnostic log.

## Runtime checks

```bash
systemctl status rusaifin-netdiag-metrics.timer
systemctl status rusaifin-iphone-capture.service
curl -s http://127.0.0.1:9090/api/v1/query \
  --get --data-urlencode 'query=rusaifin_netdiag_requests_window'
docker logs --since 5m obs-promtail
```

The capture watcher exits successfully after 50 captures. The state is stored
in `/var/lib/rusaifin-netdiag-capture/state.json`.

## Rollback

The deployment records its backup directory in
`/root/rusaifin-netdiag-current-backup`. Restore the copied configs, run
`nginx -t`, reload nginx, stop/disable the two `rusaifin-*` units and recreate
Promtail/Grafana from the restored observability files. Do not delete diagnostic
logs or pcaps without explicit confirmation.
