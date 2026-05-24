# Track C — Pre-window technical debt

**Status:** done
**Owner chat:** dolgan / 2026-05-21 — 2026-05-24 session
**Last update:** 2026-05-24

## Состав

4 независимых item, каждый — отдельный коммит на main + deploy на prod:

- **C1** — `rusaiauth_reader` PG role вместо superuser в `RUSAIAUTH_DB_*` env rusaifin + rusaisklad. **Critical для cutover gate.**
- **C2** — bibli pipeline fix для rusaisklad_front prod docker build. Желательно.
- **C3** — APP_DEBUG=true rusaifin prod — ADR'ить «остаётся включённым» с обоснованием. Желательно.
- **C4** — duplicate points 66/202 data fix в rusaifin. **Critical для cutover gate.**

## Track summary

Все 4 item закрыты 2026-05-21 / 2026-05-22.
- C1, C4 — critical, applied на prod через env-update + data fix.
- C3 — documentation only (ADR-0005).
- C2 — vendored bibli, prod docker build теперь воспроизводимый.

Плюс по ходу подсветились и закрылись 2 инфра-проблемы (см. секцию «Bonus fixes»).

## Done

- **2026-05-21 — стартовая разведка.** Создан status-файл, проверены memory `oauth_clients`, `rusaisklad_front_bibli_docker_blocker`, `rusaifin_prod_debug_intentional`, `rusaifin_duplicate_points_66_202`.

### C1 — rusaiauth_reader PG role

- **C1 dev (2026-05-21).** Создан `rusaiauth_reader` в `rusaiauth_dev` (SELECT only on `identity_users`); `.env` rusaifin/rusaisklad на dev переключены на `rusaiauth_reader` (backup `.env.backup-20260521-175954-c1` на серверах). Sklad-dev контейнер пересоздан с `-p rusaisklad_back_dev`. Smoke: SELECT count=527, INSERT denied (SQLSTATE 42501), `identity:backfill-user-links --dry-run` зелёный. Commit `98f825e` (rusaiauth/dev) — SQL setup-скрипт. Runbook: `docs/operations/rusaiauth-reader-role.md`.
- **C1 prod (2026-05-21).** Merge dev→main в rusaiauth (`285e1be`), pull на prod sso.rusaifin.ru, прогон SQL-скрипта в `rusaiauth_back_prod-db`. `.env` rusaifin/rusaisklad на prod переключены (backup `.env.backup-20260521-182338-c1`). rusaisklad_back_prod-app-1 пересоздан с `-p rusaisklad_back_prod`. Smoke prod: count=544 на обоих сервисах, INSERT denied, backfill dry-run зелёный.

### C2 — bibli pipeline fix

- **C2 dev (2026-05-22).** Vendor'нул bibli в `rusaisklad_front/local-bibli/` (1.8 MB, 188 файлов из RUSSMARKET/russ-ui#main). `package.json`: `"bibli": "file:./local-bibli"`. Dockerfile.front.{dev,prod}: `COPY local-bibli`, удалён `UPDATE_BIBLI` ARG, добавлены `ENV NUXT_LOCAL_BIBLI(_PATH)`. `scripts/update-bibli.sh` — refresh upstream main с сохранением shim. `deploy.sh`: `UPDATE_BIBLI=true` (default) теперь запускает `update-bibli.sh` на хосте и предупреждает про несохранённые изменения. `npm install` (не `npm ci`) — package-lock.json не в репо. Commits `5993b80` + `45fd9b1`. Dev deploy зелёный, HTTP 200 на dev.rusaisklad.ru/login, JS-чанк содержит `logoutGlobal`/`logoutLocal`.
- **C2 prod (2026-05-22).** Cherry-pick `5993b80` + `45fd9b1` на `main` → `3333d0d` + `f40a4ac`. Не мерджил dev→main: в dev лежит 5 чужих unrelated коммитов (см. heads-up ниже). На prod `git pull main` + `./deploy/deploy.sh prod`. Image `rusaisklad_front_prod-nuxt-dev` пересобран (`55d5486b0d27`), эфемерный workaround от 2026-05-20 устранён.

### C3 — ADR APP_DEBUG=true

- **C3 (2026-05-22).** ADR-0005 `docs/adr/0005-rusaifin-prod-app-debug-on.md` зафиксировал решение оставить `APP_DEBUG=true` на rusaifin prod. README ADR обновлён. Defence-in-depth подтверждён: nginx 404 на `/.env`, `/.git/*`, `/storage/*`. Prod-операций нет.

### C4 — duplicate points 66/202

- **C4 dev (2026-05-22).** SQL-скрипт `rusaifin/database/scripts/dedupe-point-202-into-66.sql` прогон на `fintech_devbase`. Eloquent видит 1 point (id=66), 19 agents / 2 products сохранены, 202 soft-deleted 2026-05-22 13:22:09. Idempotency verified. Commit `bc48542` на rusaifin/dev.
- **C4 prod (2026-05-22).** Backup `/root/backups/c4/c4-pre-20260522-133700.sql`. Прогон скрипта на `fintech_base` через scp + mysql напрямую — **без git pull** (в main застряли чужие коммиты, см. heads-up). Результат: 202 soft-deleted, pivot для 202 пусты, 66 сохранил 20 agents + 2 products. Дублей по (project_id, name) в prod больше нет.

## Bonus fixes

### Bonus 1: декларативная rusaiauth-net в sklad/core compose (2026-05-22)

- **Симптом.** При `docker compose ... up -d --force-recreate app` контейнер терял руками-присоединённую `rusaiauth_back_{env}_app-network`, и connection rusaifin/sklad → identity_users падал «could not translate host name 'auth-db'».
- **Fix.** В `rusaisklad_back/compose.back.{dev,prod}.yaml` и `rusaicore/compose.back.{dev,prod}.yaml` объявлена external `rusaiauth-net` (name = `rusaiauth_back_{env}_app-network`), сервис `app` подключён к ней постоянно.
- **Commits.** rusaisklad_back dev `2fa4c17` / main `7ab14b9`. rusaicore dev `fe583be` / main `fdec160`.
- **Smoke.** sklad dev/prod: count=527/546 после recreate без ручного connect. core dev: count=527. core prod: сети присоединены, но `RUSAIAUTH_DB_HOST` env пустой (backfill через DB-link там никогда не настраивали) — fix declarative-ready, реальной БД не дёргает.
- **Memory.** `m2_dev_cutover_done` обновлён: пункт 6 (runtime `docker network connect`) помечен как устаревший.

### Bonus 2: nginx healthcheck IPv4 (2026-05-22)

- **Симптом.** Все 6 nginx-контейнеров (rusaiauth, rusaicore, rusaisklad_back × dev/prod) висели `(unhealthy)` 5+ недель. Трафик шёл, статус был unhealthy.
- **Root cause.** Alpine `wget` резолвит `localhost` в IPv6 `::1`, а nginx слушает только `0.0.0.0:80`. Healthcheck падал «connection refused» на `[::1]:80`.
- **Fix.** В `compose.back.{dev,prod}.yaml` каждого репо заменено `http://localhost/...` → `http://127.0.0.1/...` (1-строчный diff на файл).
- **Commits.** rusaiauth dev `40ec18d` / main `fd5bd96`. rusaicore dev `47ec28f` / main `a3fef87`. rusaisklad_back dev `1a2d4bc` / main `f1ad117`.
- **Deploy.** `docker compose ... up -d --force-recreate nginx` на всех 6 серверах. Все 6 теперь `(healthy)` спустя ~30 сек.

## Heads-up / follow-ups

- **rusaifin `origin/main` содержит чужие коммиты, не задеплоенные на prod** (диапазон `8756461..ad2d013`): Magnit metrics, ShiftService refactor, redirect refactor + миграция `2026_05_22_000001_add_replaced_code_to_redirect_user_table`. На prod пока не уехало — при следующем `git pull` на prod подтянутся вместе с миграцией. С автором этих коммитов согласовать deploy отдельно.
- **rusaisklad_front `origin/dev` содержит 5 чужих коммитов поверх main** (`9f7c158` revoke tokens, `8d7ff63` auth layout refactor, `4006128` session handling, `1ad7cd4`, merge-коммиты). Не вёл их через cherry-pick в main для C2 — пусть автор деплоит сам.
- **rusaicore deploy от root падает по SSH** (`Permission denied (publickey)`), потому что deploy-key висит у user'а `Rusaicore`. Текущий workaround — `runuser -u Rusaicore -- git pull ...`. Если хочется убрать ручной шаг — настроить SSH-agent forwarding для root или скопировать deploy-key в root's authorized.
- **rusaicore prod `RUSAIAUTH_DB_HOST` env пустой.** Если когда-нибудь понадобится прогнать `core:backfill-identity-user-links` на prod — сначала прописать `RUSAIAUTH_DB_*` в `.env`, потом recreate (сеть подключится декларативно через Bonus 1).
