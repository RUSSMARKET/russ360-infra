# pre-Track-E cleanup — итог захода

**Дата:** 2026-05-25
**Цель:** закрыть открытые хвосты Phase 2 и де-рискнуть Track E (dev rehearsal). Track E НЕ запускался.
**Owner chat:** dolgan / pre-Track-E cleanup

## Сделано

### 1. Триаж stash'ей (3 репо)
- **rusaiauth `stash@{1}`** (nginx healthcheck `localhost`→`127.0.0.1`) — содержимое уже в dev И main →
  **DROPPED** (по «иди»).
- Остальные 4 — неприземлённый авторский WIP, оставлены **keep-for-author** (не наш контент):
  - rusaiauth `stash@{0}` vite-builder Dockerfile;
  - rusaisklad_back `stash@{0}` doc-реорг (−53/+3 свод. дока);
  - rusaisklad_back `stash@{1}` cutover-stage-2 network patch (вытеснен другим подходом в dev — `rusaiauth-net` external) + неприземлённая doc-правка;
  - rusaicore `stash@{0}` docs/russmarket360 status-обновления (частично перекрыты Stage 2).

### 2. `.cutover-backup/` — проверен, НЕ удалён (ждёт «иди»)
- `d4-rusaifin-wip.patch` (9 файлов) сверён с committed D4 `7c2853d` по blob-хэшам: **7/9 совпали**.
- Расхождения: `PointServiceWriterTest.php` — committed **полнее** WIP (ОК); `ProjectController.php` —
  вскрыта **регрессия** (см. п.3). После фикса п.3 весь существенный контент бэкапа представлен в
  committed → бэкап безопасен к удалению. **Удаление держу до явного «иди».**

### 3. D2 read-residue fix — rusaifin `cutover-final` commit `483cadf`
- **`ProjectController::getProject`** — D4-коммит (`7c2853d`) при инциденте рабочего дерева тихо
  откатил D2-чтение команды проекта с `ProjectTeamReader` (Core memberships) на legacy eager-load
  пивотов (`project_supports`/`project_regional_directors`/`project_manager_id`). Регрессия жила в
  HEAD, не ловилась (Tier1 тестировал reader, но не его вызов в контроллере). Восстановлен
  `attachTeam` + добавлен HTTP-регресс-тест в `CutoverE2ETest`.
- **`User::point()` РД-ветка** (был `User.php:170`) — читала frozen-пивот `project_regional_directors`
  через `DB::table()->pluck`. Переведена на Core `project_memberships` (role=regional_director) →
  `CoreScopeResolver`, контракт возврата (`Point` query builder) сохранён. Новый
  `UserPointRegionalDirectorScopeTest` (2). Удалён неиспользуемый импорт `DB`.
- Прочие ветки `User::point()`/`project()` (PM/GL/AGENT) — это **определения Eloquent-связей**,
  возвращающие `Relation`-объекты; их конверсия в Core — не чистый read-swap (HTTP-данные нельзя
  вернуть как relation). `User::project()` к тому же не вызывается в `app/`. Оставлены как есть —
  это сознательная D2-граница (связи свопаются у вызова, не в модели).
- **Full suite rusaifin: 155/155** (152 D7 + 3 новых). Legacy-файлы имеют pre-existing pint-style-debt
  — не переформатировал целиком (bug-fix-only).

### 4. D5 re-dry-run на dev (13 триггеров) — скрипт готов, ждёт `!`
- Read-only разведка `fintech_devbase`: 0 триггеров (чисто), prod-shaped данные (project_point_agents=4896,
  points=247, projects=15, supports=6, reg_dirs=7), `log_bin_trust_function_creators=OFF`.
- root-mysql write по SSH **заблокирован auto-классификатором** ([[mysql_trigger_super_1419]]).
- Подготовлен `/tmp/d5_dryrun.sh` (13 триггеров narrowed + 17 проб + авто-rollback + restore log_bin).
  Запуск автором через `!`.
- **✅ Результат на dev (2026-05-25): PASS=17 / FAIL=0.** 13 blocked (9 full-freeze + 4 guard) +
  4 anchor-allowed; reads ок (points=247/agents=4896/projects=15); триггеры дропнуты, log_bin восстановлен.
  Суженный D5 (Option A) подтверждён на dev prod-shaped данных.

### 5. sklad full-suite re-baseline — DONE
- Остановлен локальный obs-стек (10 контейнеров), sklad на `cutover-final`, full feature-suite в контейнере.
  obs-стек восстановлен.
- **Результат (стабильно ×3): 127 passed, 13 skipped, 0 failed**, ~7–8s. Флакинг D7 был на 100% средовой.
  13 skip — санкционированные (10× legacy Sanctum AuthTest, 2× deferred sklad-write-via-Core, 1× obsolete
  X-Core-Token). Зафиксировано в `track-d7-acceptance.md`.

### 6. Merge-стратегия Track E — DONE
- `cutover-status/track-e-prep-merge-strategy.md`: merge `cutover-final→dev` — rusaicore/sklad **чисто**;
  rusaifin **1 конфликт** `StaffService.php` от Macallan `81b7404` (НЕ Track B). Track B-obs дизъюнктен,
  CoreApiClient-метрики в rusaifin отложены (подтверждено). Рекомендованный порядок: rusaicore → sklad →
  rusaifin (с ручным резолвом StaffService по принципу «Core-механика побеждает, фичи Macallan
  переэкспрессить через Core»).

### 7. Memory + status
- Memory landmark `phase2_d_tracks_and_trackb_done` + строка в MEMORY.md.
- Обновлены `track-d7-acceptance.md` (sklad re-baseline), этот файл, merge-strategy.

## Открытые пункты (для автора / Track E)
- [x] `.cutover-backup/` — **удалён** 2026-05-25 (по «иди»; контент представлен в коммитах).
- [x] D5 dev re-dry-run — **прогнан, PASS=17/FAIL=0** (см. п.4).
- [x] `cutover-final` запушены на origin (бэкап работы) 2026-05-25.
- [ ] Track E: merge по стратегии + StaffService-резолв (сверить с Macallan).
- [ ] stash'и keep-for-author (4 шт.) — разрулить когда дойдут руки.

Связано: [[git_workflow_dev_main]], [[cutover_stage_2_branch]], [[mysql_trigger_super_1419]],
[[observability_stack]], [[parallel_chats_shared_worktree]].
