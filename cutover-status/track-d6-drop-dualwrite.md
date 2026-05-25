# Track D6 — Drop dual-write

**Status:** ✅ DONE. НЕ мерджить в dev/main до D7.
**Owner chat:** dolgan / 2026-05-25 session (после D4)
**Last update:** 2026-05-25

## Цель

Удалить best-effort dual-write код, оставшийся от Stage 2 α (dual-write был live на prod
с 2026-05-18, см. [[stage2_partial_predeploy_prod]]). Ветка `cutover-final`.

## Ключевой факт

**D4 уже сделал бóльшую часть D6.** Writer switch (D4) заменил best-effort dual-write на
Core-only во всех write-путях (PointService/ProjectService/UserService/контроллеры): убрал
try/catch с проглатыванием 409+fallback в legacy, убрал записи в legacy-пивоты. Поэтому D6
после D4 — остаточная зачистка.

## Сделано

1. **Удалён `CutoverMetricsSnapshotCommand`** (`core:cutover-metrics-snapshot`) — монитор
   dual-write drift'а (local-vs-Core counts) эпохи Stage 2 α. Kickoff D6 прямо называл его.
   Удалены 2 покрывающих теста в `CutoverCommandsTest` (pre/post-smoke тесты остались).
2. **Reword докблока** `PointService::coreCreateAssignment` — убран маркер «silent fallback»
   (был только в комментарии, не в коде), чтобы acceptance-grep стал пустым.

## Сознательно НЕ трогал (обосновано)

- **Seed*/Backfill/Reconcile/Pre-PostSmoke команды** (`SeedLocations`, `SeedLocationAssignments`,
  `SeedProdMirror`, `SeedCoreEmployees`, `BackfillCoreEmployeeLinks`, `ReconcileCoreData`,
  `CutoverPre/PostSmoke`) — это **backfill/verification tooling для Track E/F**, не dual-write
  hot-path (kickoff: «Backfill — Track F»). Их 409-swallow в seeders — корректная идемпотентность
  backfill. Остаются.
- **core_*_external_id writes** — под Option A (D4) единственные bridge-writes в app-коде:
  `PointService::create` (установка anchor↔Core линка для новой точки — легитимно, Core
  authoritative отдаёт external_id) и backfill-команды. Отдельной dual-write-синхронизации,
  которую требовал убрать kickoff D6, **нет** (kickoff писался до Option A). bridge-колонки
  остаются writable для anchor-создания, читаются для FK-join.
- Dual-write config-флагов в rusaifin `config/` нет (в отличие от sklad).

## Acceptance D6 — выполнено

- ✅ `grep -rnE "dual-write|best-effort|swallowed.*409|silent.*fallback" rusaifin/app/` — **пусто**.
- ✅ Feature-тесты зелёные: **148** (было 150 в D4; −2 удалённых metrics-теста).

## Next

- D6 закрыт. Дальше **D7** (acceptance suite) — последний gate Phase 2.
- `cutover-final` (rusaifin) — НЕ мерджить в dev/main до D7.

## Artifacts

- rusaifin `cutover-final`: `97911a0` (D6).
- `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 2, D6).
