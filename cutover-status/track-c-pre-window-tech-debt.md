# Track C — Pre-window technical debt

**Status:** in-progress
**Owner chat:** dolgan / 2026-05-21 session
**Last update:** 2026-05-21

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

## In progress
- C3 закрыт. Остаётся C2 (bibli pipeline) — единственный нерешённый item трека.

## Blocked
- —

## Next
- Презентовать план по каждому item автору, ждать «иди» поштучно.

## Artifacts
- Память: см. выше.
- План: `docs/final-stage-cutover-cleanup-sprint-plan.md` § Phase 1 / Track C.
