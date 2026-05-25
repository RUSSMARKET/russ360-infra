# Track D7 — Acceptance test suite (Phase 2 gate)

**Status:** ✅ DONE (suite построен и зелёный локально; ⚠ sklad full-suite — environmental caveat, см. ниже). НЕ мерджить в dev/main до Track E.
**Owner chat:** dolgan / 2026-05-25 session (после D6)
**Last update:** 2026-05-25

## Scope-решения (подтверждены автором 2026-05-25)

1. **D7 = test suite, доказанный ЛОКАЛЬНО на cutover-final** (mocked Core, детерминированно).
   Фактический прогон «на dev с restored prod-dump» — это **Track E (dev rehearsal)**; merge
   cutover-final→dev только в dev-cutover окно ([[cutover_stage_2_branch]]). В D7 не тащим.
2. **sklad sub-track делаем после освобождения rusaisklad_back от Track B** (общее рабочее
   дерево — см. [[parallel_chats_shared_worktree]]).

## D7a — rusaifin E2E (через весь HTTP-стек)

`tests/Feature/Cutover/CutoverE2ETest` (4) — admin lifecycle через
`auth:oauth → UserIsNotDisabled → ResolveCurrentProject → CheckPermission → controller →
service → Core gateway` на mocked Core:
- create project → Core project POST (code RUSAIFIN_*, Idempotency-Key);
- add point → Core location POST (type=sales_point) + локальный anchor с bridge, group_leader=null;
- attach agent → Core assignment POST, **0 записей в project_point_agents**; detach → PATCH ended;
- delete point → Core location PATCH archived.

Agent/leader **visibility** HTTP-покрыта существующим D2-набором (`StaffListVisibilityTest`
скоупит агентов по current Core-project; `ProjectPointAccessHttpContractTest` гейтит доступ) —
не дублируется.

**rusaifin full suite: 152/152 зелёный** (стабильно, MySQL). Pint clean. Commit `78919c2`.

## D7b — Core API smoke

`tests/Feature/Api/V1/CoreApiSmokeTest` (1) — полный write-chain через API
(employee → project → location → membership → assignment, все 201) + все bulk-read фильтры D1
(`filter[external_ids][]`, `filter[project_external_ids][]`,
`filter[operational_location_external_ids][]&filter[is_open]`, `include=project,assignments`).

**rusaicore full suite: 83/83 зелёный** (стабильно). Pint clean. Commit `b253ee2`.

## D7c — sklad test-infra trait

`tests/Concerns/AuthenticatesAsOAuthUser` — rebind 3 Core read-контрактов на `Local*` shadow
+ flush scoped-memo (`LocalExternalIdMap`). Применён к Inventory/Business/Sku/DocumentGeneration/
IContactSync. Восстанавливает suite из **105-red** (D3 переключил чтения на Core-HTTP, а
feature-тесты сидят локальные users/projects/memberships).

Дополнительно:
- `CoreApiClientTest` — застаблен S2S token-provider (был реальный HTTP к :8002) → 2 теста зелёные.
- `BusinessApiTest` — flag-gated local-write coverage гоняется со снятыми D3-guard'ами
  (`disable_local_*_writes=false`); 2 current-project write-теста `markTestSkipped`
  (`@group sklad-legacy-local-write`) — 500 без Core external-id mapping, до sklad-write-via-Core.

**Per-class зелёный** (на спокойной машине): InventoryApiTest 76/76, BusinessApiTest 15+2skip,
SkuApiTest 7, CoreApiClientTest (token-fix), IContactSync/DocumentGeneration. Commit `653a298`.

### ⚠ Environmental caveat — sklad full-suite нестабилен на нагруженной dev-машине

`php artisan test tests/Feature` (все классы разом) **флакает**: набор падений меняется между
прогонами (26 → 13 → 7, разные классы), при большом классе среда деградирует в середине
(~43 passed, дальше **всё** 500-ит — даже endpoints, ожидающие 400/403). Тот же одиночный
прогон `InventoryApiTest` давал 76/76, затем 33-failed **без изменения кода**. Причина —
**исчерпание ресурсов/коннектов** на машине под нагрузкой (obs-стек из ~10 контейнеров +
Track B + параллельные прогоны; `rusaicore-core-app` уже OOM-умер, Exited 137). Это инфра,
не логика и не trait. **Официальный зелёный baseline снять на квисцентной среде в Track E**
(остановить obs-стек/Track B, либо прогнать per-class). Логика доказана per-class green.

## Baseline report (snapshot 2026-05-25)

| Сервис | Suite | Результат |
|---|---|---|
| rusaicore | full | **83 passed** (стабильно) |
| rusaifin | full | **152 passed** (стабильно) |
| rusaisklad_back | per-class | InventoryApiTest 76/76; BusinessApiTest 15+2 skip; SkuApiTest 7; CoreApiClientTest green; DocumentGeneration/IContactSync green |
| rusaisklad_back | full | ⚠ environmentally flaky (см. caveat) — re-baseline в Track E |

## Acceptance D7 (мой scope) — статус

- ✅ E2E rusaifin (admin lifecycle) + smoke Core + smoke fin зелёные локально на cutover-final.
- ✅ sklad suite восстановлен из 105-red (trait); per-class green.
- ✅ Все 4 backend собираются на `cutover-final`.
- ⚠ Полный green на dev с restored prod-dump + observability smoke — **Track E** (по scope-решению 1).
- ⚠ sklad full-suite green — подтвердить на квисцентной среде (Track E).

## Deferred (вне D7 → Track E/прочее)

- Merge cutover-final→dev + prod-dump restore + прогон на dev (Track E).
- Observability smoke (Track B `in progress`, не задеплоен).
- sklad-write-via-Core sub-track (разблокирует 2 skipped BusinessApiTest + re-enable D3 guards в тестах).
- sklad full-suite cross-class isolation / resource профиль (Phase 5 test-debt).

## Artifacts

- rusaicore `cutover-final`: `b253ee2` (Core smoke).
- rusaifin `cutover-final`: `78919c2` (E2E).
- rusaisklad_back `cutover-final`: `653a298` (trait + feature-suite recovery).
- `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 2, D7).
