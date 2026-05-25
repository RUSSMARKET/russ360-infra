# Track E prep — merge `cutover-final → dev` strategy

**Status:** анализ готов (pre-Track-E). Merge НЕ выполнен — это план для Track E шаг 1.
**Owner chat:** dolgan / pre-Track-E cleanup, 2026-05-25
**Метод:** `git merge-tree --write-tree` (dry-run, без касания dev) + trial-merge в изолированном worktree для rusaifin.

## TL;DR

| Репо | merge `cutover-final → dev` | Конфликты |
|---|---|---|
| **rusaicore** | ✅ CLEAN | нет |
| **rusaisklad_back** | ✅ CLEAN | нет |
| **rusaifin** | ⚠️ 1 конфликт | `app/Services/Staff/StaffService.php` |

**Главное:** конфликт-поверхность — **не Track B**. Track B (obs) был намеренно дизъюнктен
с cutover-final и авто-мёржится чисто во всех 3 репо. Единственный конфликт (rusaifin
`StaffService.php`) порождён **параллельным domain-рефактором Macallan `81b7404`**, не obs.

## Топология (на 2026-05-25)

- **Track B уже в `origin/dev` И `origin/main`** всех 3 backend (dev-tip = obs-коммит
  `fix(observability): fall back to in-memory unless apcu_enabled()`). См. [[observability_stack]].
- `cutover-final` ответвлялась **до** obs-cherry-pick'ов:
  - rusaifin merge-base = `b14405b` (RedirectController), obs-коммиты dev — поверх.
  - rusaicore cutover-final tip `b253ee2`, rusaisklad_back `653a298`.
- Поэтому merge сводит D-track (cutover-final) с уже-приземлённым Track B в dev.

## Почему Track B НЕ конфликтует

Track B-файлы в rusaifin (`app/Http/Controllers/MetricsController.php`,
`app/Http/Middleware/PrometheusRequestMetrics.php`,
`app/Infrastructure/Observability/MetricsRegistry.php`,
`app/Providers/ObservabilityServiceProvider.php`, `config/prometheus.php`,
`tests/**/Observability/*`, плюс `bootstrap/app.php` report()-hook, `composer.json`,
`Dockerfile`) **не пересекаются** с файлами, которые трогала cutover-final
(`comm -12` пересечения изменённых файлов rusaifin = только `StaffService.php`).
→ всё это авто-мёржится без конфликта.

### CoreApiClient deferral — ПОДТВЕРЖДЁНО

Track B намеренно отложил инструментацию `CoreApiClient` в rusaifin (core_api latency /
dualwrite_fallback), чтобы не пересекаться с D2/D4 (Track B status §Known follow-ups).
Проверка: `git diff <merge-base> origin/dev -- app/Domain/Core/Gateways/CoreApiClient.php`
= **пусто** (dev-версия идентична merge-base; 0 obs-ссылок). Значит CoreApiClient в dev
не трогался obs'ом → конфликта с D2/D4-правками CoreApiClient (idempotency writeRequest) **нет**.

## Единственный конфликт: rusaifin `StaffService.php`

Между **`81b7404`** (Macallan, dev: `refactor(staff): enhance StaffService with new methods
for group leader and agent retrieval`, 2026-05-22) и **D2 Tier 2b/2c**
(`0a7f7bf` scope-on-Core, `c8ac5fe` getProjectStaff-on-Core).

Macallan добавил методы (большинство — новые, авто-мёржатся): `getGroupLeaderIdsFromProjects`,
`getSupportVisibleGroupLeaderIds`, `getAllAgentIds`, `getUnassignedStaffIdsForSupport`,
`getSupportScopedStaffIds`; и поведенческие изменения в `getProjectStaff`. Конфликтуют
**4 региона** (общая логика, которую обе стороны переписали):

### Регион 1-2 — `getUnassignedStaffIdsForSupport` / unassigned-логика
- **HEAD (Macallan):** считает «привязанных» через **legacy-пивоты** —
  `projects.project_manager_id`, `project_regional_directors`, `project_point_agents`.
- **cutover-final (D2):** `$this->visibilityScopeService->attachedLocalUserIds()` (Core-членства).
- **Резолв:** Core-источник побеждает (legacy-пивоты **заморожены D5** — читать нельзя).
  Macallan-specific поведение (support-manager видит непривязанных по нужным ролям) переэкспрессить
  поверх `attachedLocalUserIds()`.

### Регион 3-4 — `getProjectStaff`
- **HEAD (Macallan):** GL-фильтр точек (`group_leader_id == viewer`), support skip
  agent-visibility, **eager-load legacy-связей** `points.agents` / `points.leader`
  (читают project_point_agents / group_leader_id).
- **cutover-final (D2 Tier 2c):** `ProjectStaffReader` (Core батч) +
  `accessibleLocalProjectIdsForViewer` + `resolveVisibleUserIds`.
- **Резолв:** Core-версия — база; новые поведения Macallan (GL point-filter,
  support agent-visibility skip) переэкспрессить через Core-данные. Legacy eager-loads
  **не возвращать**.

**Принцип резолва (важно):** это **не механический** «ours/theirs». Cutover-final выигрывает
по *механике источника данных* (никаких frozen-пивотов), но *новые бизнес-фичи* Macallan
(`81b7404`) надо сохранить, выразив через Core-методы. Требует доменного понимания и,
желательно, **сверки с Macallan** (его фичи могли уехать в его собственный flow).
См. [[cutover_stage_2_branch]] (правило «не затирать коммиты Macallan»).

## Рекомендованный порядок merge для Track E

Git-уровень: репо независимы (нет cross-repo merge-зависимости). Порядок — по логике
деплоя/проверки на dev (Core — зависимость для fin/sklad):

1. **rusaicore** (clean) → `composer install` (sentry/promphp уже в dev), `config:clear`,
   `php artisan test` (ожидаем 83). Идемпотентность-инфра D4 (`idempotency_keys` миграция,
   `EnsureIdempotency`) — **forward-миграция, не в `cutover/`** → применяется обычным
   `migrate`. Проверить, что не зацепит cutover-drop-миграции (см. CLAUDE.md quirk).
2. **rusaisklad_back** (clean) → `composer install`, suite (см. Задачу sklad re-baseline ниже).
3. **rusaifin** (last) → **разрулить `StaffService.php`** по принципу выше → `composer install`
   → full suite **155** (152 D7 + 3 от pre-Track-E D2-residue fix `483cadf`). Pint: legacy-файлы
   имеют pre-existing style-debt, не переформатировать целиком (bug-fix-only).

После merge каждого: `cutover-final` ветку **не удалять** до успешного dev-rehearsal
(Track E доказывает зелёное на restored prod-dump).

## Пост-merge возможности (не блокеры)

- **rusaifin Core-gateway метрики** (core_api latency, dualwrite_fallback) — Track B их отложил
  под D2/D4. После merge CoreApiClient на cutover-final стабилен (idempotency writeRequest) →
  можно добить как Track B follow-up (Track B status §Known follow-ups #1). Не в Track E scope.
- **D5 cutover-миграция** (13 column-guard триггеров) — в окне Track F, с pre-step
  `log_bin_trust_function_creators=1`. Re-dry-run на dev — см. Задачу D5 (этот заход).

## Артефакты / проверки

- merge-tree dry-run: rusaicore/sklad exit=0; rusaifin exit=1 (StaffService).
- composer.json cutover-final НЕ трогала в rusaicore/sklad (нет lock-regen конфликта).
- Trial-merge rusaifin — в изолированном worktree, удалён после анализа.
- Связано: [[git_workflow_dev_main]] (merge в dev), [[cutover_stage_2_branch]],
  Track B status (`track-b-app-instrumentation.md`), D2 status.
