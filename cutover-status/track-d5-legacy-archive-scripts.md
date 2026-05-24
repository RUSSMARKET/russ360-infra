# Track D5 — Legacy archive scripts

**Status:** in-progress
**Owner chat:** dolgan / 2026-05-24 session
**Last update:** 2026-05-24

Делает legacy-таблицы rusaifin read-only в момент cutover'а через BEFORE-триггеры,
которые отбивают любые INSERT/UPDATE/DELETE понятным сообщением. После writer-switch
(D4) authoritative-источник этих доменов — rusaicore; legacy-таблицы остаются только
для чтения, пока их не выпилят отдельным post-acceptance cleanup.

Скрипты лежат в `cutover/` и **не запускаются** обычным `php artisan migrate` —
только в окне через `--path=database/migrations/cutover`.

## Plan deviations

Отклонения от kickoff-промпта / sprint-плана, согласованы в сессии 2026-05-24:

1. **`project_user` в rusaifin не существует.** Ни в миграциях, ни в коде, ни в схеме
   (единственное совпадение — имя тест-метода `test_..._single_project_user`).
   user↔project pivots в rusaifin реализованы как:
   - `project_supports` — пивот user↔project (роль support);
   - `project_regional_directors` — пивот РД↔project, появился 2025-12-25 из миграции
     `2025_12_25_143742_migrate_regional_directors_to_pivot_table`.
   Решение: вместо несуществующего `project_user` под триггеры берём **оба** реальных
   пивота — Core memberships станут authoritative после cutover, значит legacy-пивоты
   обязаны стать read-only. Итоговый скоуп — **5 таблиц** (а не 4).
2. **`RAISE EXCEPTION` из kickoff-промпта неприменим.** rusaifin на MySQL 8.0.45
   (Laravel-коннекшен назван `mariadb`), а `RAISE EXCEPTION` — синтаксис PostgreSQL.
   Используем `SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '...'` (errno 1644).
3. **Rename в `*_legacy` — НЕ делаем** (взвешено с D2/D3/D4):
   - D5 идёт параллельно с reader/writer switch. Read-only триггер блокирует только
     запись, а чтение продолжает работать — пропущенная в D2 ссылка деградирует мягко
     («запись отбита понятным message»), а не падает «table not found».
   - На таблицах есть FK — rename усложняется и расширяет blast radius.
   - Rename отложен в отдельный cleanup ПОСЛЕ того, как D7 докажет отсутствие ссылок.
4. **Таблицу `users` не трогаем** — остаётся read-write (логин через guard,
   `online_in` обновляется и т.д.).

## Скоуп (5 таблиц)

| Таблица | Домен в Core (authoritative после cutover) |
|---|---|
| `project_points` | operational_locations |
| `project_point_agents` | operational_location_assignments |
| `projects` | projects |
| `project_supports` | project_memberships |
| `project_regional_directors` | project_memberships |

По 3 триггера на таблицу (`BEFORE INSERT/UPDATE/DELETE`; MySQL не даёт один триггер
на несколько событий) = **15 триггеров**. Имя: `trg_ro_<table>_<ins|upd|del>`.

## Done

- **2026-05-24 — разведка.** Прочитан track-c status, ADR-0003, memory
  `cutover_stage_2_branch` / `m2_prod_cutover_done`. Подтверждён движок (MySQL 8.0.45),
  наличие 4 из 5 таблиц локально (`project_user` отсутствует — см. deviations).
- **2026-05-24 — ветка.** Создана `cutover-final` в rusaifin от `main`. **В main не
  мерджить до D7.**
- **2026-05-24 — скрипты написаны:**
  - `rusaifin/database/migrations/cutover/2026_05_24_000000_lock_legacy_tables_read_only.php`
    — up() создаёт 15 триггеров (SIGNAL 45000), down() дропает их.
  - `rusaifin/database/scripts/cutover/unlock-legacy-tables.sql` — аварийный
    ручной rollback (`mysql <db> < unlock-legacy-tables.sql`), зеркало down(),
    идемпотентен (`DROP TRIGGER IF EXISTS`).
- **2026-05-24 — local dry-run (findatabase, изолированно через временный `--path`,
  чтобы не зацепить 2 drop-миграции из cutover/):**
  - up() → 15 триггеров создано.
  - **15/15** write-путей (INSERT/UPDATE/DELETE × 5 таблиц) отбиты `errno=1644
    sqlstate=45000` с message `…is READ-ONLY post-cutover…`. Тест в rolled-back
    транзакциях по реальным колонкам/строкам — данные не тронуты.
  - Чтение работает: points=178, projects=6, agents=352.
  - Rollback path A (raw `.sql` через PDO) → 0 триггеров, запись разблокирована.
  - Rollback path B (`migrate:rollback` → down()) → 0 триггеров, запись в
    `migrations` снята. БД оставлена в исходном состоянии, temp-dir удалён.

## In progress

- Коммит скриптов на `cutover-final` (rusaifin) + статуса (root repo). Без push.

## Blocked

- Нет блокеров.

## Next

- **Dev dry-run на restored prod dump** — только после явного «иди на dev». На dev
  важно проверить, что `project_supports` / `project_regional_directors` содержат
  данные (локально 8 / 7 строк) и что триггеры не конфликтуют с реальными FK.
- На prod НИЧЕГО не катить — миграция применяется только в cutover-окне (Track F).
- Post-acceptance (после D7): рассмотреть rename `*_legacy` отдельным cleanup.

## Artifacts

- rusaifin (ветка `cutover-final`):
  - `database/migrations/cutover/2026_05_24_000000_lock_legacy_tables_read_only.php`
  - `database/scripts/cutover/unlock-legacy-tables.sql`
- Local dry-run: findatabase @ rusaifin_local-app-1, MySQL 8.0.45.
