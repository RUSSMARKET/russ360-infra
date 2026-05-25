# Track D4 — rusaifin writer switch

**Status:** ✅ DONE (writer-switch завершён; idempotency-инфра на Core). НЕ мерджить в dev/main до D7.
**Owner chat:** dolgan / 2026-05-25 session
**Last update:** 2026-05-25

## Цель

Перевести все WRITE-точки rusaifin по Core-домену (assignments + memberships + project/
point entities) на запись **только в Core** через gateways. Legacy-таблицы — read-only по
факту (триггеры D5 в окне). Ошибки больше не молчат: HTTP-fail → raise, без silent fallback
в legacy. Каждый write в Core несёт **idempotency-key**. Всё на ветке `cutover-final`
(rusaifin + rusaicore), без push, без merge до D7.

## Решения при старте

- **Idempotency = PG-таблица в rusaicore (НЕ Redis).** У core/fin/auth нет Redis-контейнера;
  добавлять — против ADR-0004 (минимизируем обвязку). PG-таблица работает на existing infra.
  См. [[redis_future_use_cases]] (use case #2 прямо допускает PG-вариант).
- **Anchor-конфликт (Группа 3) → Вариант A** (подтверждён автором). `projects`/`project_points`
  остаются read-write как FK-якорь для локальных shifts/products/inventory; D5 сужен — морозит
  только relationship-данные. См. `track-d5-legacy-archive-scripts.md` §Narrowing.

## Idempotency-инфра (Core)

- Миграция `idempotency_keys` (forward, НЕ в cutover/): key uuid unique, request_fingerprint
  (sha256 method+path+body), response_status, response_body, created_at.
- Middleware `EnsureIdempotency` на всех `/v1` write-роутах: повтор с тем же ключом+payload →
  реплей сохранённого 2xx (header `Idempotency-Replayed`); тот же ключ с другим payload → 409;
  read / запрос без ключа → no-op. Не-2xx не кешируются (retry может пройти).
- Команда `idempotency:prune` (TTL 24h) + `Schedule::daily()`.
- rusaifin `CoreApiClient::{post,patch,delete}Resource` → каждый write шлёт `Idempotency-Key`
  (UUID v4 на логический write, стабилен поверх внутреннего `->retry()`).

## Реестр переключённых writes

| Группа | Точки | Стало |
|---|---|---|
| 1 assignments | `PointService::{addAgent,deleteAgent,setGroupLeader,delete}`, `PointController::{addProductPointAgents,deleteProductPointAgents}` (bulk) | Core OL-assignments only; 409 (already assigned) = идемпотентный no-op; raise на прочее |
| 2 memberships | `ProjectService::{setProjectManager,add/delete/setRegionalDirector(s),add/deleteSupport}`, `ProjectController::setProjectSupport`, `UserService::detachFromProjectsAndPoints` | Core project-memberships only |
| 3 entities | `ProjectController::{createProject,updateProject,deleteProject,activate/deactivateProject}`, `PointService::{create,delete}`, `PointController::updateProjectPoint` | local anchor (FK-якорь) + Core authoritative по domain-атрибутам; leader/PM — через Core, не во frozen-колонки |
| 4 products | `*::addProduct/deleteProduct`, SystemController product-sync | **остались локальными** (товаров в Core нет) — по плану |
| 5 history-bridge | `PointController:542/618` (`Project::find` для имени) | `CoreScopeResolver::projectByLocalId(...)->name` |

**Quirk:** в Core **нет DELETE-роутов** — удаление сущности = PATCH status (`archived` для
delete project/point; `inactive`/`active` для deactivate/activate). См. [[stage2_put_to_patch_bugfix]].

## Тесты

- `tests/Unit/Project/PointServiceWriterTest` (6): addAgent (Core POST + idempotency-key, нет
  legacy pivot), deleteAgent (PATCH ended), setGroupLeader (end прежнего leader + create),
  raise на 500, swallow 409, create (anchor без group_leader + Core location + bridge).
- `tests/Unit/Project/MembershipWriterTest` (7): addSupport/deleteSupport, setProjectManager
  (end+create), addRegionalDirector max-3, setRegionalDirectors replace, detach agent/support.
- **rusaifin full suite: 150/150** (137 D2 + 13 D4). Pint clean.
- **rusaicore: `IdempotencyApiTest` (3); full suite 82/82.** Pint clean.

## Acceptance D4 — выполнено

- ✅ В `PointService`/`ProjectService` нет legacy Eloquent в write-методах.
- ✅ Все domain-writes идут через Core gateway; ошибки raise (no silent fallback).
- ✅ Acceptance-grep по `app/`: **0 legacy relationship-WRITES** (`DB::table(pivot)->insert/update/delete`,
  `->agents()/supports()/regional_directors()->sync|attach|detach`, FK-колонки) — все на Core.
- ✅ Feature-тесты зелёные (rusaifin 150, rusaicore 82).

## Known issues (вне scope D4 — НЕ лечил)

- **D2 read-residue:** `app/Models/User/User.php:170` — `DB::table('project_regional_directors')->pluck`
  (visibility-чтение в `User::points()` для РД). Это READ, проскочил мимо D2 grep'а (тот искал
  `Project::`/`Point::`, не `DB::table(pivot)`). Не writer — на D4 не влияет. Передать в D2-добивку
  или Phase 5.
- **D6-residue:** `Console/Commands/Core/CutoverMetricsSnapshotCommand` считает legacy-пивоты
  (`->count()`) для dual-write мониторинга — это удалит D6.
- **D5 dev re-dry-run:** старый dry-run был на 15 full-freeze триггерах; после сужения (13, с
  column-guard) нужен повторный прогон на dev — внести в Track E rehearsal.

## ⚠ Инцидент рабочего дерева (2026-05-25) — урок для параллельных чатов

Параллельный Track B-чат (observability instrumentation) работал в **тех же git-checkout'ах**
`rusaifin`/`rusaicore` и переключал ветки/стэшил в общем дереве, пока у меня были незакоммиченные
D4-правки на `cutover-final`. Дерево «плыло» между командами; часть D4-WIP оказалась в stash
(Track B его сохранил), часть — loose в working tree. Восстановлено через stash + снапшот в
`/home/dolgan/russ360/.cutover-backup/` + повторное применение 2 правок. **Урок:** два чата НЕ
должны делить один working dir — сериализовать по репо или использовать отдельные git worktree.
После инцидента вся D4-работа закоммичена локально сразу (защита от повторения).

## Next

- D4 завершён. `cutover-final` (rusaifin + rusaicore) — НЕ мерджить в dev/main до D7.
- Дальше: **D6** (drop dual-write) → **D7** (acceptance suite). См. sprint-план.

## Artifacts

- rusaicore `cutover-final`: `30d95c2` (idempotency infra).
- rusaifin `cutover-final`: `846754d` (D5 narrow), `7c2853d` (D4 writers).
- Бэкап инцидента: `/home/dolgan/russ360/.cutover-backup/` (можно удалить после подтверждения).
- `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 2, D4).
