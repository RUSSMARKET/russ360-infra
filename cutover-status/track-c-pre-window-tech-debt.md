# Track C — Pre-window technical debt

**Status:** done
**Owner chat:** dolgan / 2026-05-21 — 2026-05-22 session
**Last update:** 2026-05-22

## Состав

4 независимых item, каждый = отдельный коммит на main + deploy на prod:

- **C1** — `rusaiauth_reader` PG role вместо superuser в `RUSAIAUTH_DB_*` env rusaifin + rusaisklad. **Critical для cutover gate.**
- **C2** — bibli pipeline fix для rusaisklad_front prod docker build. Желательно.
- **C3** — APP_DEBUG=true rusaifin prod — ADR'ить «остаётся включённым» с обоснованием. Желательно.
- **C4** — duplicate points 66/202 data fix в rusaifin. **Critical для cutover gate.**

## Done
- 2026-05-21 — создан status-файл, проверены memory `oauth_clients`, `rusaisklad_front_bibli_docker_blocker`, `rusaifin_prod_debug_intentional`, `rusaifin_duplicate_points_66_202`.
- **C1 dev**: создан `rusaiauth_reader` role в `rusaiauth_dev` (SELECT only on `identity_users`); `.env` rusaifin/rusaisklad на dev переключены на `rusaiauth_reader` (backup `.env.backup-20260521-175954-c1` на серверах). Sklad-dev контейнер пересоздан с `-p rusaisklad_back_dev`. Smoke зелёный: SELECT count=527, INSERT denied (SQLSTATE 42501), `identity:backfill-user-links --dry-run` отработал на обоих сервисах. Commit `98f825e` (rusaiauth/dev) — SQL setup-скрипт. Runbook: `docs/operations/rusaiauth-reader-role.md`.

- **C1 prod (DONE 2026-05-21)**: merge dev→main в rusaiauth (`285e1be`), pull на prod sso.rusaifin.ru, прогон SQL-скрипта в `rusaiauth_back_prod-db` → роль `rusaiauth_reader` создана. `.env` rusaifin/rusaisklad на prod переключены (backup `.env.backup-20260521-182338-c1`). rusaisklad_back_prod-app-1 пересоздан с `-p rusaisklad_back_prod` через `compose.back.prod.yaml`; после recreate отвалился rusaiauth_back_prod_app-network — re-connected руками. Smoke prod зелёный: count=544 на обоих сервисах, INSERT denied (SQLSTATE 42501), `identity:backfill-user-links --dry-run` зелёный.

- **C4 dev (DONE 2026-05-22)**: SQL-скрипт `rusaifin/database/scripts/dedupe-point-202-into-66.sql` прогон на `fintech_devbase`. Eloquent теперь видит 1 point (id=66) для адреса, 19 agents/2 products сохранены, 202 soft-deleted 2026-05-22 13:22:09. Idempotency verified (повторный прогон не меняет состояние). Commit `bc48542` на rusaifin/dev.

- **C4 prod (DONE 2026-05-22)**: backup `/root/backups/c4/c4-pre-20260522-133700.sql` (project_points + project_point_agents + point_products). Прогон скрипта на `fintech_base` через scp + mysql напрямую — **БЕЗ git pull**, потому что параллельно кто-то влил весь dev в main (`ad2d013 Merge branch 'dev'`), там есть 7 чужих коммитов (Magnit, redirect refactor, миграция redirect_user) — нельзя смешивать в один deploy. Результат: 202 soft-deleted, pivot для 202 пусты, 66 сохранил 20 agents + 2 products. Дублей по (project_id, name) в prod больше нет.

## Blocked / heads-up
- **`origin/main` в rusaifin содержит чужие незадеплоенные на prod коммиты** (8756461..ad2d013): Magnit metrics, ShiftService refactor, redirect refactor + миграция `2026_05_22_000001_add_replaced_code_to_redirect_user_table`. Эти изменения сделал не я. Они **на prod пока не уехали** — при следующем `git pull` на prod подтянутся вместе с миграцией. Нужно с автором этих коммитов согласовать deploy отдельно.

- **C3 (DONE 2026-05-22)**: ADR-0005 `docs/adr/0005-rusaifin-prod-app-debug-on.md` зафиксировал решение оставить `APP_DEBUG=true` на rusaifin prod. README ADR обновлён. Defence-in-depth проверен: nginx 404 на `/.env`, `/.git/*`, `/storage/*`. Никаких prod-операций.

- **C2 dev (DONE 2026-05-22)**: vendor'нул bibli в `rusaisklad_front/local-bibli/` (1.8 MB, 188 файлов из RUSSMARKET/russ-ui#main). `package.json`: `"bibli": "file:./local-bibli"`. Dockerfile.front.{dev,prod}: `COPY local-bibli`, удалён `UPDATE_BIBLI` ARG, добавлены `ENV NUXT_LOCAL_BIBLI(_PATH)`. `scripts/update-bibli.sh` — refresh upstream main с сохранением shim'а. `deploy.sh`: `UPDATE_BIBLI=true` (default) теперь запускает `update-bibli.sh` НА ХОСТЕ и предупреждает про несохранённые изменения. Также: `npm install` (не `npm ci`) — package-lock.json не в репо. Commits: `5993b80` + `45fd9b1`. Dev deploy через `bash ./deploy/deploy.sh dev` отработал штатно, HTTP 200 на dev.rusaisklad.ru/login, JS-чанк содержит `logoutGlobal`/`logoutLocal` — vendored bibli работает.

- **C2 prod (DONE 2026-05-22)**: cherry-pick'ed `5993b80` + `45fd9b1` на `main` (теперь `3333d0d` + `f40a4ac`), пушнул в `origin/main`. Не мерджил dev→main, потому что в dev лежит 5 чужих unrelated коммитов (auth refactor, session handling) — их пусть автор деплоит отдельно. На prod: `git pull main` + `./deploy/deploy.sh prod` отработали штатно. Image `rusaisklad_front_prod-nuxt-dev` пересобран с vendored bibli (`Successfully built 55d5486b0d27`). HTTP 200 на rusaisklad.ru, A5 logout-fix (`logoutGlobal`/`logoutLocal`) теперь в bundle штатным путём — эфемерный workaround от 2026-05-20 устранён.

## Track summary
- **Status: DONE** (все 4 item закрыты 2026-05-21 / 2026-05-22).
- C1, C4 — critical, applied на prod через env-update + data fix.
- C3 — documentation only (ADR-0005).
- C2 — vendored bibli, prod docker build теперь воспроизводимый.

## Bonus 1: устранён ручной `docker network connect` для sklad/core ↔ rusaiauth
- **rusaisklad_back** compose.back.{dev,prod}.yaml: `rusaiauth-net` объявлена как external с фиксированным именем (`rusaiauth_back_{env}_app-network`), `app` сервис теперь декларативно подключён. Commit dev `2fa4c17` → cherry-pick на main `7ab14b9`. Smoke: dev count=527, prod count=546 без ручного connect'а.
- **rusaicore** compose.back.{dev,prod}.yaml — симметричный fix. Commit dev `fe583be` → cherry-pick на main `fdec160`. Smoke dev: `count=527`. Prod: сети присоединены декларативно, но `RUSAIAUTH_DB_HOST` на core prod env пустой (там backfill через DB-link никогда не настраивали) — fix declarative-ready, реальной БД не дёргает.
- Memory `m2_dev_cutover_done` обновлен: пункт 6 (runtime `docker network connect`) помечен как устаревший.

## Bonus 2: nginx healthcheck IPv6/IPv4 fix (2026-05-22)
- **Симптом:** все 6 nginx-контейнеров (rusaiauth, rusaicore, rusaisklad_back на dev и prod) висели `(unhealthy)` 5+ недель. Trafic шёл, статус был unhealthy.
- **Root cause:** alpine `wget` резолвит `localhost` в `::1` (IPv6), а nginx слушает только `0.0.0.0:80`. Healthcheck падал «connection refused» на `[::1]:80`.
- **Fix:** в compose.back.{dev,prod}.yaml каждого репо заменено `http://localhost/...` → `http://127.0.0.1/...` (форсит IPv4). 1-строчный diff на файл.
- **Commits:** rusaiauth dev `40ec18d` / main `fd5bd96`; rusaicore dev `47ec28f` / main `a3fef87`; rusaisklad_back dev `1a2d4bc` / main `f1ad117`.
- **Deploy:** `docker compose ... up -d --force-recreate nginx` (или `auth-nginx`) на всех 6 серверах. Smoke: все 6 контейнеров теперь `(healthy)` спустя 30 секунд.

## In progress
—

## Blocked
- —

## Next
- Презентовать план по каждому item автору, ждать «иди» поштучно.

## Artifacts
- Память: см. выше.
- План: `docs/final-stage-cutover-cleanup-sprint-plan.md` § Phase 1 / Track C.
