# Track E — Dev rehearsal (Final Stage Cutover)

**Status:** ✅ DONE — rehearsal зелёный (Шаги 0-4 пройдены, F10/F11 исправлены+валидированы, rollback-proof снят). Track F runbook → `track-f-prod-cutover.md`.

## ✅ Шаг 4 — rollback drill (non-destructive proof, по решению автора)
Полный teardown не делали (git-reset уже доказан в F4; dev оставлен в cutover-состоянии для тестирования).
Прогнан D5 unlock/relock proof (`!`): `unlock-legacy-tables.sql` снял 13 триггеров за **728 ms** (count 13→0),
затем re-lock (`migrate:rollback --path=cutover --step=1` + `migrate --path=cutover` + log_bin pre/post) → count 0→13.
⇒ D5-abort шаг быстрый (~0.7s, незначим для Track F risk-budget). dev снова locked/cutover.
**Track F abort = D5 unlock (~1s) + git reset main→pre-cutover SHA (доказано F4) + composer/caches + restart.**

## Acceptance Track E — итог
- ✅ Все 4 backend + cutover-код на dev (core 07cabc2 / sklad c02c1cd / fin 9f5ffad), миграции применены, D5 13 триггеров.
- ✅ 0 регрессий: backend suites локально (core 88/sklad 131/fin 159), reconcile orphans=0, D2-semantics браузер→API (mint-token) 0×5xx, obs метрики идут/dualwrite=0/no false alerts.
- ✅ Rollback отработан (D5 unlock 728ms + git reset доказан F4).
- ⚠ Окно Шаги 2-3 = ~96 мин (>90 бюджет) — НО ~50% на отладку+фикс F4-F11 (теперь постоянны) → чистый Track F быстрее.
- Findings: F10/F11 ИСПРАВЛЕНЫ+валидированы; F4/F5/F7 устранены в процессе+в runbook; F6/F8/F9/F-obs/F-sec задокументированы (см. ниже + Track F).

### rusaifin gmp — НЕ нужен
host php8.3 gmp=NO, но rusaifin auth быстрый (0.26s) → rusaifin валидирует RS256 не через web-token (openssl-based).
F10 (gmp) касается только web-token-валидаторов: **rusaicore + rusaisklad_back** (оба исправлены, app-base stage в
`docker/Dockerfile` → покрывает и app-prod target). **Track F prereq:** gmp-фикс должен попасть на main (prod rebuild).
**Owner chat:** dolgan / Track E
**Last update:** 2026-05-25
**Цель:** генеральная репетиция полного cutover на dev (restored prod-dump). Замерить окно (<90 мин),
найти грабли, отработать rollback. PROD НЕ ТРОГАТЬ. Merge только в `dev`, НЕ в `main`.

---

## Шаг 0 — Pre-flight

### Pre-cutover dev SHAs (ROLLBACK TARGETS) — зафиксированы 2026-05-25
| Репо | dev (= origin/dev, in sync) |
|---|---|
| rusaicore | `7293df18acfd06b9020f0b018de24391a0e6410c` |
| rusaifin | `b9b5b3a073c4c759955ec8d0117456b19b73a829` |
| rusaisklad_back | `2901b194681618f35e71967eade10a616ef53d9f` |
| rusaiauth | `95955728c538ef73ecab4464563d977948f649dc` (вне cutover-scope, merge нет) |

### cutover-final tips (merge sources)
| Репо | cutover-final | merge `dev←cutover-final` |
|---|---|---|
| rusaicore | `b253ee244911023057ce142da4722bf59470e572` | ✅ CLEAN (merge-tree exit=0) |
| rusaisklad_back | `653a2989f3868f4ae77632207dec29cde40c3903` | ✅ CLEAN (merge-tree exit=0) |
| rusaifin | `483cadfce13cae7a737993b4441015c64cce6cd5` | ⚠ 1 конфликт `StaffService.php` (merge-tree exit=1) |

- Все 3 dev-ветки **в синхроне с origin** (нет local drift). Рабочие деревья: 0 uncommitted.
- **rusaiauth НЕ имеет `cutover-final`** → в Track E merge только 3 backend. rusaiauth dev/main стоят.
- **Фронты (fintech / rusaisklad_front / bibli) НЕ имеют `cutover-final`** → merge не нужен;
  браузерный E2E гоняется против уже задеплоенных dev-фронтов (Track B obs там live).

### ✅ Refresh dev из prod — DONE 2026-05-25 13:30 (~24 мин, узкое место — anonymize 120k redirect_history)
Запущен `/root/refresh-dev-from-prod.server.sh` (по «иди на prod»). Prod только на чтение. Верификация:
- fintech_devbase: points=247, projects=15, ppa=5080, supports=6, regdirs=7, users=512; **0 D5-триггеров**.
- rusaicore_dev: employees=299, projects=14, op_locations=242, memberships=343, assignments=4629.
- rusaiauth_dev oauth_clients=8 (dev redirect_uri сохранены). Дамп-дир `/tmp/refresh-dev-20260525-100628` (можно удалить).
- Расхождение 15/14 projects, 247/242 locations — известная data-реальность (дубли 66/202 + local/inactive) → проверить в D2-semantics (Шаг 3b).

### Reconcile / orphans
- reconcile-команда: `rusaifin app/Console/Commands/Core/ReconcileCoreDataCommand.php` (на cutover-final).
- Прогон orphans=0 — **до merge нельзя** (команда только на cutover-final). Запустится после merge rusaifin
  на dev-чекауте против Core (Шаг 3 acceptance), как в [[stage2_put_to_patch_bugfix]].

### Что прилетит merge'ом (origin/dev..origin/cutover-final)
- **rusaicore (4):** D1 bulk endpoints (2), D4 idempotency infra, D7 Core smoke. Forward-миграция
  `database/migrations/2026_05_25_000000_create_idempotency_keys_table.php` (НЕ в cutover/ → обычный migrate).
  rusaicore `cutover/` пуст → `php artisan migrate` безопасен.
- **rusaisklad_back (2):** D3 reader switch, D7c trait.
- **rusaifin (17):** D2 (readers, Steps 0-5), D4 (writers), D5 (lock-triggers narrow), D6 (drop dual-write),
  D7 (E2E), D2-residue fix `483cadf`.

---

## ⚠ FINDINGS / риски (pre-merge)

### F1 — rusaifin cutover-миграции: НЕ полагаться на `migrate --path=cutover` вслепую
После merge `rusaifin/database/migrations/cutover/` = 3 файла:
- `2026_04_27_180000_drop_api_token_from_users_table.php` (M2, уже применён на prod-dump)
- `2026_04_27_180100_drop_personal_access_tokens_table.php` (M2, уже применён)
- `2026_05_24_000000_lock_legacy_tables_read_only.php` (D5, НОВЫЙ)

Риск: на prod-dump dev оба M2-drop **уже в `migrations` таблице** → artisan их пропустит и применит
только D5. НО если по какой-то причине не записаны — drop упадёт (table gone). Плюс D5 всё равно ловит
1419 (SUPER/log_bin) под app-юзером ([[mysql_trigger_super_1419]]).
**Решение (как в dev dry-run):** D5 применяем **напрямую root-SQL** (`d5_lock.sql`-эквивалент), минуя
artisan — pre-step `log_bin_trust_function_creators=1` → CREATE TRIGGER × 13 → restore. Это и репетирует
Track F окно. Forward idempotency (rusaicore) — обычным `migrate`.

### F2 — StaffService.php резолв = доменный, не механический
Конфликт `81b7404` (Macallan) × D2 (`0a7f7bf`/`c8ac5fe`). Реальные конфликтные регионы — **2**
(где правили ОБЕ стороны): блок unassigned-методов и `getProjectStaff`. Остальное (`getScopedRoleIds`
правил только Macallan; `getStaff`/`isUserAttached`/`getAccessiblePointIds`/`resolveReportingPointIds`/
`preloadUserAttachments` — только D2) авто-мёржится.

**Дизайн резолва (применить при merge, валидировать suite 155 + браузерным D2-semantics):**
- `getGroupLeaderIdsFromProjects($projects)` — Macallan читает `Point.group_leader_id` (FROZEN D5).
  → переэкспрессить через Core: GL = open assignment role=leader на локациях проектов. Кандидат —
  `StaffVisibilityScopeService::visiblePointIdsByUsers` использует assignmentProvider+locationCatalog;
  нужен симметричный helper «leaderUserIds для projectExternalIds» (или вынести из ProjectStaffReader
  `leaderPointIdsForUser`-логику наоборот). Если чистого helper нет — добавить на scope-service.
- `getSupportVisibleGroupLeaderIds` — assigned-GL (Core assignments) ∪ unassigned-GL (users role=GL без
  Core attachment). Не читать `Point.group_leader_id`.
- `getAllAgentIds()` — `User::where(role_id=AGENT)` — локальная users-таблица, не пивот → **KEEP as-is**.
- `getUnassignedStaffIdsForSupport()` — Macallan-версия ещё читает FROZEN `Project.project_manager_id`/
  `project_regional_directors`/`project_point_agents` → заменить механику на D2 `attachedLocalUserIds()`.
  ⚠ Семантический риск: `attachedLocalUserIds()` строится по project_memberships (PM/RD/support), а
  agent/GL — assignment-based. Проверить, что «unassigned» для support не схлопывается/не раздувается
  (это и есть D2-semantics риск Шага 3b). Тесты `StaffListVisibilityTest`/`StaffVisibilityScopingTest`
  должны поймать.
- `getProjectStaff` — берём D2-версию (на `ProjectStaffReader`). GL point-filter Macallan = опция
  `leaderUserId`; support agent-skip → для SUPPORT_MANAGER передать `visibleAgentUserIds=null`.
  Legacy eager-loads `points.agents`/`points.leader` НЕ возвращать.

Желательна сверка с Macallan (его фичи могли уехать в его собственный flow).

---

## ✅ Шаг 1 — merge cutover-final→dev (2026-05-25) — все 3 зелёные локально
| Репо | merge SHA | suite (локально, docker) |
|---|---|---|
| rusaicore | `7f103f9` | **88 passed** (83 D7 + 5 Track B obs); migrate idempotency_keys ок |
| rusaisklad_back | `3e8b9e3` | **131 passed / 13 skip / 0 red** (127 + 4 obs) |
| rusaifin | `0b226ee` | **159 passed** (155 + 4 obs); StaffService резолв; pint clean |

### StaffService резолв (rusaifin) — как сделано
- Конфликт-маркеры → механика cutover-final (`attachedLocalUserIds()`, `ProjectStaffReader`).
- Фичи Macallan, читавшие frozen `Point.group_leader_id`, **переэкспрессированы через Core** —
  добавлены 2 метода в `StaffVisibilityScopeService`:
  - `groupLeaderUserIdsForLocalProjectIds(array)` — РГ точек проектов через Core assignments role=leader;
  - `assignedGroupLeaderUserIds()` — все РГ с открытым leader-assignment (для комплемента «РГ без точки»), memo.
- `getProjectStaff`: support agent-skip сохранён — для SUPPORT_MANAGER `visibleAgentUserIds=null`
  (иначе `resolveVisibleUserIds` вернул бы только membership-users → агенты отфильтровались бы).
- `getAllAgentIds()` — оставлен как есть (локальная users-таблица, не пивот).
- `StaffListVisibilityTest` (вкл. agent-scoping) + `PointAgentReader` leader-тесты зелёные.

### ⚠ FINDING F3 — support-GL семантика без прямого test-покрытия
Методы `getSupportVisibleGroupLeaderIds`/`getGroupLeaderIdsFromProjects`/`getSupportScopedStaffIds`
(Macallan) **не покрыты выделенным тестом**. Резолв сделал семантический выбор: «attached» = есть
Core-**membership** (PM/RD/support), а агенты/РГ — assignment-based (не в memberships) → для support
unassigned-набор и так включает всех агентов/РГ. Re-expression корректна по механике, но точную
support-видимость РГ надо **подтвердить в браузерном D2-semantics (Шаг 3b)** и/или сверить с Macallan.

## 🟡 Шаг 2 — deploy на dev (WINDOW_START 10:57:15 UTC) — backends DONE, D5 pending
Push `dev`→`origin` ×3: core `7f103f9`, sklad `3e8b9e3`, fin `0b226ee`.
- **rusaicore** ✅: pull(owner Rusaicore) → `docker compose -p rusaicore_back_dev -f compose.back.dev.yaml build && up -d` →
  `migrate --force` (idempotency_keys DONE) → config:cache. metrics=200.
- **rusaisklad_back** ✅: pull(Rusaisklad) → rebuild `-p rusaisklad_back_dev` → up -d → config:cache. metrics=200. (миграций нет)
- **rusaifin** ✅: reset --hard origin/dev (host, owner fintech) → `composer dump-autoload -o --ignore-platform-reqs`
  → config/route/cache:clear. metrics=200, root=200, log чистый. opcache подхватил (revalidate_freq=2, reload не нужен).
- **D5-триггеры**: pending — отдан автору на `!` (migrate --path=cutover + root log_bin pre/post). Ожидаем triggers=13.

### ⚠ FINDINGS Шага 2 (для Track F runbook — критично)
- **F4 — rusaifin dev-чекаут разошёлся с origin** (клубок пустых merge-коммитов, дерево==b9b5b3a). Резолв: `reset --hard origin/dev`
  (0 потерь, доказано). **Track F:** проверить prod-чекаут rusaifin на ту же дивергенцию ДО деплоя; ff-pull не сработает.
- **F5 — root-owned dirs блокируют деплой fintech:** `database/migrations/cutover/` + `database/scripts/` были `root:root`
  (наследие M2/root-операций) → `git reset/pull` под fintech падал `Permission denied`. Фикс: `chown -R fintech:fintech` этих dirs.
  **Track F:** на prod почти наверняка та же проблема → chown ПЕРЕД деплоем.
- **F6 — composer.lock требует PHP 8.4, серверы на 8.3.30:** `symfony/options-resolver v8.0.8` (через sentry, Track B) →
  `composer install` падает на платформе. `vendor/` уже рабочий (Track B), нужен только `dump-autoload -o --ignore-platform-reqs`.
  **Track F:** prod composer-операции с `--ignore-platform-reqs` ЛИБО апгрейд PHP→8.4. (Не от cutover-merge — pre-existing Track B.)
- **F7 — compose project-name:** деплой ОБЯЗАН `-p <svc>_back_dev`/`_prod`; без `-p` compose берёт имя dir (`public_html`) и плодит
  дубль-стек с port-collision. (Как локальный sklad-готча.)
- **F-sec — rusaifin dev git remote содержит вшитый GitHub PAT** в URL → ротировать (вне Track E scope).

## 🟡 Шаг 3 — Acceptance

### 3a reconcile (real Core HTTP) — ✅ PASS (benign)
`core:reconcile-data --dry-run` на dev: projects orphans=**0**, locations orphans=**0** (все matched в Core).
48 «errors» (memberships section) = **40× AGENT(3) без текущего membership + 8× REGISTERED(2) новые юзеры**.
**0 gaps у management-ролей** (PM=8/RD=9/SUPPORT=7/GL=10/DIRECTOR — все с открытым membership). 243 employee с
открытым membership. ⇒ нормальная data-реальность (незанятый агент/новый юзер), НЕ поломка cutover'а.
NB: PHPUnit-на-dev пропущен осознанно — мокает Core + отдельная `server_findatabase` → = локальный результат (159), real-Core не даёт.

### ⚠ FINDING F8 — браузерный OIDC E2E на dev нельзя автоматизировать
`debug_code`/info-log OTP только на `APP_ENV=local`; dev=`development` → реальный MTS-SMS, код в БД bcrypt.
Решение автора: **mint-token + API acceptance** (без изменения dev-конфига). **Track F:** prod-smoke логинится живым
оператором своим аккаунтом (реальный SMS) — для prod не блокер.

### ⚠ FINDING F9 — [[test_personas]] role_id'ы УСТАРЕЛИ
Факт по `app/Enum/RoleEnum.php`: ADMIN=1, REGISTERED=2, **AGENT=3**, DIRECTOR=4, ACCOUNT_DIRECTOR=5,
SUPPORT_SUPERVISOR=6, SUPPORT_MANAGER=7, PROJECT_MANAGER=8, REGIONAL_DIRECTOR=9, **GROUP_LEADER=10**,
ANALYST=11, BUSINESS_COACH=12, CLIENT=13. (Memory говорила 5=RD/7=SUPPORT/8=GL/9=AGENT — неверно.) → обновить memory.

### 3b mint-token API acceptance — 🔴 BLOCKED by F10
Mint через `mint-smoke-token.php <uuid> rusaifin-spa fieldsales.read,core.read` (dev client `rusaifin-spa`).
ADMIN (uuid …27d5): `auth/me`=200, `projects`=200, `staff`=200 (68KB) ✓; **`staff/project`=500** ✗.

### 🔴 FINDING F10 — RS256 token validation ~1.9s/call (missing `gmp`) → Core fan-out 500 (вероятный Track F БЛОКЕР)
- `/api/staff/project` (ADMIN) = **500** стабильно (~3.4–5.6s): `CoreApiException: Core API request to [/project-memberships] timed out` (CORE_API_TIMEOUT_SECONDS=3, retries=0).
- Локализация: no-auth /v1=8ms; authed /v1=**~1.7s фиксировано** (independent от per_page/payload, CPU 0.01% = I/O-wait). DB=17ms, JWKS cached=2ms, /ping(public)=7ms.
- **Root cause (доказан до строки):** `OAuthTokenValidator::validate()`=~1.9s ×каждый вызов; разбивка — `jwkSet()`=0.002s, **`JWSVerifier::verifyWithKeySet` (1 RSA-ключ) = 1.879s**. Контейнер rusaicore (`php:8.4-cli`) **`gmp_loaded=NO`** (openssl=YES) → `web-token/jwt-library` считает RSA в чистом PHP → ~1.9s/verify.
- **Эффект cutover:** D2 `getProjectStaff` (privileged=все проекты) фан-аутит несколько Core-вызовов/HTTP-запрос → каждый платит 1.9s валидации → >3s timeout → 500. До cutover getProjectStaff был локальным Eloquent (быстро) → cutover **обнажил** латентную gmp-проблему.
- **Fix:** добавить `gmp` в образы resource-server'ов (rusaicore + rusaisklad_back: `apt-get install libgmp-dev && docker-php-ext-install gmp`), rebuild. Проверить host-php rusaifin (8.3) на gmp. С gmp verify падает до ~мс.
- ⚠ Track B (obs) live на prod с этим же образом → prod rusaicore тоже ~1.9s/authed-request (латентно, т.к. cutover ещё не было). Track F БЛОКЕР без gmp.
- Runtime-proof install заблокирован auto-mode (shared container) → автору на `!` ЛИБО Dockerfile-фикс+rebuild.

### ✅ F10 + F11 ИСПРАВЛЕНЫ
- **F10 fix:** `gmp` добавлен в Dockerfile rusaicore (`07cabc2`) + rusaisklad_back (`c02c1cd`), rebuild dev. После —
  core `/v1/projects` latency **1.7s→0.208s**. validate() с ~1.9s → ~мс.
- **F11 fix:** Core bulk-read chunk 100→**50** в 3 gateways rusaifin (`9f5ffad`) + обновлён `CoreBulkReadGatewayTest`.
  rusaifin 159/159 зелёный. После — `staff/project` (ADMIN) **500→200**.

### ✅ 3b D2-semantics acceptance (mint-token, real Core HTTP) — PASS, 0×5xx
| Роль | staff | staff/project | shift/points |
|---|---|---|---|
| ADMIN(1) | 200 | 200 (3.4MB, 4.3s ⚠perf) | — |
| SUPPORT(7) | 200 (202KB broad, 5.2s ⚠perf) | 200 (38KB) | 200 |
| RD(9) | 200 (24KB scoped) | 200 (20KB) | 200 |
| GL(10) | 200 (6.7KB narrow) | 200 (1.4KB) | 200 |
| AGENT(3) | 403 (корректно — нет staff.get) | 403 (корректно) | 200 (660B own) |
**Вывод:** видимость градуирована корректно (ADMIN>SUPPORT>RD>GL>AGENT), management-роли НЕ схлопнулись →
D2 own-projects семантика и мой StaffService-резолв (F3) подтверждены на реальных данных. **F3 снят.**

### ⚠ PERF-NOTE (не блокер) — admin staff/project=3.4MB/4.3s, support staff=202KB/5.2s
Привилегированные «весь персонал» тяжёлые (фан-аут Core + крупная сериализация). 200, не timeout. Кандидат на
пагинацию/lazy-load пост-cutover (Phase 5 / Track G), не блокирует Track F.

### ✅ 3c observability smoke — PASS
- russ360_* метрики идут: `russ360_http_requests_total` (rusaicore sum=1512, растёт от smoke), `_duration_seconds_*` histogram, `russ360_active_tokens`, `russ360_exceptions_total`.
- **dualwrite_fallback метрика отсутствует** (`{__name__=~".*dualwrite.*"}` пусто) — D6 выпилил dual-write ✓.
- firing alerts: **пусто** (ложно не звенят) ✓.
- scrape up: rusaicore/rusaiauth/rusaisklad (×2 — dev+prod), cadvisor, node_exporter, prometheus.

### ⚠ FINDING F-obs — rusaifin (host php-fpm) + фронты НЕ в Prometheus scrape
rusaifin `/metrics` отдаёт 720 russ360-строк, но в Prometheus **нет job rusaifin/fintech/rusaisklad_front**.
Track B-completeness gap (host php-fpm не добавлен в scrape-конфиг). Не cutover-блокер → Track B follow-up / Track G.

### ✅ 3b sklad smoke — PASS (0×5xx)
gmp пересобран в sklad-образе (gmp=YES). API (token rusaisklad-spa, real Core HTTP): `users/hierarchy`=200 (43KB,
D3 Core-reader), `skus`=200, `sku-categories`=200; inventory/supervisors=404 (иной путь/метод, не 500). D3 readers
работают на dev с реальным Core.

## ✅ Шаг 3 ИТОГ — acceptance пройден (3a reconcile + 3b rusaifin/sklad D2-semantics + 3c observability), 0 регрессий после F10/F11-фиксов.

## Шаг 4-5 — TODO
- [ ] Шаг 4: rollback drill (unlock-legacy-tables.sql + reset веток + замер)
- [ ] Шаг 5: findings → фиксы → re-rehearsal

Связано: [[git_workflow_dev_main]], [[cutover_stage_2_branch]], [[mysql_trigger_super_1419]],
[[refresh_dev_from_prod_2026-05-13]], [[observability_stack]], [[test_personas]], [[infra_map]].
