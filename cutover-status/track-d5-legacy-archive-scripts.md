# Track D5 — Legacy archive scripts

**Status:** done
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
- **2026-05-24 — dev dry-run (fintech_devbase, restored prod-shaped, MySQL 8.0.45):**
  - Все 5 таблиц на месте с prod-объёмами: points=247, agents=4896, projects=15,
    supports=6, regional_directors=7.
  - **Найден privilege-блокер 1419** (см. ниже) — миграция под app-юзером падает.
  - Триггеры созданы под MySQL root (auth_socket, имеет SUPER) из `d5_lock.sql`.
    **15/15** write-путей отбиты `errno=1644 sqlstate=45000` на реальных данных;
    чтение всех 5 таблиц работает.
  - Откат через `unlock-legacy-tables.sql` → 0 триггеров, запись разблокирована,
    `migrations` чист. Temp-файлы на dev и локально удалены.

## ⚠️ Cutover prerequisite (находка dev dry-run)

**На dev/prod `log_bin=ON`, а app-юзер БД (на dev `fintech_devuser`) не имеет `SUPER`** →
`CREATE TRIGGER` падает с `SQLSTATE[HY000] 1419 You do not have the SUPER privilege and
binary logging is enabled`. Локально это не воспроизводится (binlog off), поэтому ловится
только на dev. `log_bin_trust_function_creators` на dev = `OFF`.

**Решение (выбрано автором): pre-step `SET GLOBAL` в cutover-окне.** Привилегированный
оператор (MySQL root через auth_socket) в окне, ДО `php artisan migrate --path=...`:

1. Запомнить исходное значение: `SHOW GLOBAL VARIABLES LIKE 'log_bin_trust_function_creators';` (на dev было `OFF`).
2. `SET GLOBAL log_bin_trust_function_creators = 1;`
3. Прогнать cutover-миграции (включая lock-триггеры).
4. Восстановить: `SET GLOBAL log_bin_trust_function_creators = 0;` (или исходное).

Этот prerequisite продублирован в docblock'е миграции. Должен попасть в Track F runbook
(перед шагом migrate) и в Track E rehearsal-чеклист. Альтернатива на случай проблем —
прогнать `d5_lock.sql` напрямую под MySQL root (минуя artisan), как делали в dev dry-run
и как деплоили C4 на prod.

## Next

- На prod НИЧЕГО не катить — миграция применяется только в cutover-окне (Track F),
  с pre-step выше.
- **Track F runbook / Track E rehearsal:** внести `SET GLOBAL
  log_bin_trust_function_creators` как шаг перед `migrate --path=cutover`.
- Post-acceptance (после D7): рассмотреть rename `*_legacy` отдельным cleanup.
- Push `cutover-final` (rusaifin) — по команде автора (по умолчанию не пушу).

## Artifacts

- rusaifin (ветка `cutover-final`, локальные коммиты, без push):
  - `database/migrations/cutover/2026_05_24_000000_lock_legacy_tables_read_only.php`
    (commit `e79c2ef` + docblock-prereq правка)
  - `database/scripts/cutover/unlock-legacy-tables.sql`
- root repo (main): этот status-файл.
- Local dry-run: findatabase @ rusaifin_local-app-1, MySQL 8.0.45.
- Dev dry-run: fintech_devbase @ 82.146.57.149 (host php-fpm, не docker), MySQL 8.0.45.
