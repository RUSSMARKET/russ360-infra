# Track F — Production Cutover runbook

**Status:** 📋 READY (составлен из Track E dev-rehearsal 2026-05-25). НЕ запускался.
**Источник:** Track E (`track-e-dev-rehearsal.md`) — полный прогон на restored prod-dump, F4-F11 найдены+исправлены.
**Правило:** PROD. Каждый шаг — статус в Telegram «RSM Infra» + в этот файл. На каждый шаг ждать «иди».

---

## 🧭 ГДЕ ЖИВУТ ФИКСЫ (критично для merge-стратегии Track F)

Track E-фиксы лежат на **`dev`** (НЕ на `cutover-final`!). Merge `cutover-final→main` их НЕ принесёт. Перед окном
довести cutover-final ДО состояния dev одним из путей:
- **gmp (F10):** Dockerfile, отдельные коммиты — rusaicore `07cabc2`, rusaisklad_back `c02c1cd`. Dockerfile есть и на main
  → можно cherry-pick на cutover-final ЛИБО задеплоить на main pre-window независимо.
- **chunk=50 (F11):** rusaifin `9f5ffad` (3 gateway + тест). Эти gateway — D2-код (на main их НЕТ до cutover) →
  **обязан** ехать через cutover-final: cherry-pick `9f5ffad` на cutover-final.
- **StaffService merge-резолв (F2/F3):** в dev merge-коммите `0b226ee` (StaffService.php + 2 новых метода в
  StaffVisibilityScopeService.php). Извлечь diff и закоммитить на cutover-final ОТДЕЛЬНЫМ коммитом, либо реплеить при merge в main.

**Рекомендация:** ДО окна привести `cutover-final` = валидированному dev-состоянию (cherry-pick gmp+chunk+резолв),
тогда `cutover-final→main` чистый. Иначе — реплеить резолв StaffService + cherry-pick gmp/chunk в окне (дольше, рискованнее).
Merge-стратегию для main проанализировать как для dev (`track-e-prep-merge-strategy.md`): main мог получить Macallan `81b7404`.

## ⚠️ PRE-WINDOW PREREQUISITES (сделать ДО окна — иначе окно сорвётся)

Track E доказал: без этих шагов деплой падает. Все — отдельными действиями до cutover-окна.

1. **gmp на prod (F10 — иначе 500 на тяжёлых страницах).** Dockerfile-фикс (`gmp`) уже в dev: rusaicore `07cabc2`,
   rusaisklad_back `c02c1cd` (app-base stage в `docker/Dockerfile` → покрывает app-prod). **Должен попасть на `main`**
   (merge cutover-final→main принесёт его, ИЛИ отдельный pre-window deploy). После деплоя prod-образов проверить:
   `docker exec rusaicore_back_prod-app-1 php -r 'var_dump(extension_loaded("gmp"));'` → true.
   rusaifin (host php8.3) gmp НЕ нужен (валидирует RS256 не через web-token, быстро).
2. **Prod rusaifin checkout — проверить дивергенцию (F4).** Dev-чекаут разошёлся клубком пустых merge-коммитов →
   ff-pull падал. Проверить prod: `cd /home/fintech/web/server.rusaifin.ru/public_html && git fetch && git log --oneline origin/main..HEAD`.
   Если есть локальные коммиты без уникального кода (`git diff <merge-base>..HEAD` пусто) → `reset --hard origin/main`
   (prod fin на ветке `master`, tracking origin/main — см. [[infra_map]]). **Под владельцем fintech.**
3. **Prod root-owned dirs (F5).** `database/migrations/cutover/` + `database/scripts/` на prod fin почти наверняка
   `root:root` → git pull/reset под fintech упадёт `Permission denied`. **Pre-step:**
   `chown -R fintech:fintech /home/fintech/web/server.rusaifin.ru/public_html/database/migrations/cutover /home/fintech/web/server.rusaifin.ru/public_html/database/scripts`.
4. **composer на prod (F6).** Committed `composer.lock` требует PHP 8.4 (`symfony/options-resolver` через sentry),
   host rusaifin = 8.3 → `composer install` падает. `vendor/` уже рабочий → достаточно
   `composer dump-autoload -o --ignore-platform-reqs` (новые классы cutover'а). core/sklad — в контейнере php8.4, install ок при rebuild.
5. **Dump'ы свежие (<2ч)**, reconcile orphans=0 (см. §smoke), Phase 0 baseline накоплен, Phase 1 (Track C) закрыт.
6. **StaffService merge-резолв подготовлен (F2/F3).** merge cutover-final→main даст конфликт `app/Services/Staff/StaffService.php`
   (Macallan `81b7404` × D2). Резолв уже выполнен и валидирован в dev (см. ниже §T0+15). Лучше **закоммитить резолв в
   cutover-final ДО окна** (тогда merge в main чистый), либо реплеить по dev-коммиту `0b226ee`.

---

## SEQUENCE (целевое <90 мин; Track E чистая часть ≈ 30-40 мин без отладки)

### T0 — Pre-flight
- Дашборды Grafana открыты (`obs-grafana` 127.0.0.1:3030, ssh-tunnel), Telegram прочищен.
- Дампы prod свежие. reconcile orphans=0 (projects/locations). Дежурство.
- Зафиксировать pre-cutover main SHA каждого репо (rollback target).

### T0+5 — Maintenance window
- rusaifin nginx 503 на write-эндпоинты (read остаётся). Telegram: «начинаем».

### T0+15 — Merge `cutover-final → main` (core → sklad → fin) + push
- Порядок: rusaicore (clean) → rusaisklad_back (clean) → rusaifin (конфликт StaffService).
- **StaffService резолв** (если не закоммичен в cutover-final заранее): Core-механика побеждает; фичи Macallan
  переэкспрессить через Core. Готовый резолв — dev-коммит `0b226ee`:
  - `getGroupLeaderIdsFromProjects` → `StaffVisibilityScopeService::groupLeaderUserIdsForLocalProjectIds()` (Core assignments role=leader, не frozen `Point.group_leader_id`);
  - `getSupportVisibleGroupLeaderIds` → `assignedGroupLeaderUserIds()` (Core) для «РГ без точки»;
  - `getProjectStaff` → версия cutover-final (`ProjectStaffReader`), для SUPPORT_MANAGER `visibleAgentUserIds=null` (иначе агенты отфильтруются);
  - 2 новых метода в `StaffVisibilityScopeService` (groupLeaderUserIdsForLocalProjectIds + assignedGroupLeaderUserIds) — перенести.
- `git push origin main` (3 backend).

### T0+20 — Deploy на prod (per-service; ⚠ ВСЕГДА `-p <svc>_back_prod` — F7)
**rusaicore:**
```
cd /home/Rusaicore/web/server.rusaicore.ru/public_html
sudo -u Rusaicore git pull --ff-only origin main        # remote = git@github (ssh-ключ владельца)
docker compose -p rusaicore_back_prod -f compose.back.prod.yaml build   # включает gmp
docker compose -p rusaicore_back_prod -f compose.back.prod.yaml up -d
docker exec rusaicore_back_prod-app-1 php artisan migrate --force        # forward idempotency_keys (cutover/ пуст — безопасно)
docker exec rusaicore_back_prod-app-1 php artisan config:cache
docker exec rusaicore_back_prod-app-1 php -r 'var_dump(extension_loaded("gmp"));'  # проверка F10
```
**rusaisklad_back:** аналогично `-p rusaisklad_back_prod -f compose.back.prod.yaml` (build+up+config:cache; миграций нет).
**rusaifin (host php-fpm, F4/F5/F6):**
```
cd /home/fintech/web/server.rusaifin.ru/public_html
# prereq chown уже сделан (шаг 3). prod fin на ветке master→origin/main:
sudo -u fintech git fetch origin && sudo -u fintech git reset --hard origin/main   # или ff-pull если чисто
sudo -u fintech composer dump-autoload -o --ignore-platform-reqs                   # F6
sudo -u fintech php artisan config:clear && route:clear && cache:clear
# opcache подхватит за revalidate_freq (~2s); host-wide php-fpm reload — только если validate_timestamps=0
```

### T0+40 — Apply D5 legacy archive (на prod БД `fintech_base`)
Pre-step log_bin + migrate cutover (Track E: M2-drop пропускаются, т.к. записаны в migrations; применится только D5):
```
mysql -e "SET GLOBAL log_bin_trust_function_creators=1"      # capture orig сначала (на prod может быть != 0)
cd /home/fintech/web/server.rusaifin.ru/public_html
sudo -u fintech php artisan migrate --path=database/migrations/cutover --force
mysql -e "SET GLOBAL log_bin_trust_function_creators=<orig>"
# verify: 13 триггеров (trg_ro_* ×9 + trg_guard_* ×4), reads работают
```
⚠ root-mysql `SET GLOBAL` + app-artisan — взаимозависимы, выполнять одним блоком (auto-mode блокирует ассистенту → оператор вручную).

### T0+50 — Smoke critical paths (mint-token, реальный Core HTTP)
- `mint-smoke-token.php <uuid> rusaifin-spa fieldsales.read,core.read` → ADMIN/SUPPORT/RD/GL: `auth/me`,`staff`,`staff/project`,`shift/points` → все 2xx (агент: 403 на staff — корректно).
- **D2-semantics:** видимость градуирована (ADMIN>SUPPORT>RD>GL), management-роли НЕ пустые.
- sklad: `users/hierarchy`/`skus` 2xx. Core `/v1/*` latency <0.3s (gmp). reconcile orphans=0.
- obs: russ360_* метрики растут, dualwrite_fallback отсутствует, alerts не звенят.

### T0+70 — Снять maintenance, unfreeze. Telegram: «закончили, мониторим».

---

## ROLLBACK (если smoke падает) — Track E замеры
1. **Maintenance остаётся.**
2. **D5 unlock (~0.7s, F-Track-E):** `mysql fintech_base < database/scripts/cutover/unlock-legacy-tables.sql` → 13 триггеров сняты, legacy снова writable.
3. **Reset main → pre-cutover SHA** в каждом репо (доказано в F4): core/sklad — git reset + rebuild `-p ..._prod` + up; fin — `sudo -u fintech git reset --hard <sha>` + dump-autoload + config:clear.
4. Restore dumps если требуется. Restart. Smoke pre-cutover. Unfreeze.
- Длительность abort: D5 unlock ~1s + git reset/rebuild (минуты). Заложить в risk-budget.

---

## Findings из Track E (ссылки)
- **F10** missing gmp → RS256 verify 1.9s → 500 (ИСПРАВЛЕН: gmp в core+sklad Dockerfile). Prereq #1.
- **F11** Core bulk GET chunk 100 → nginx 414 (ИСПРАВЛЕН: chunk 50, `9f5ffad`).
- **F4** divergent fin checkout (prereq #2). **F5** root-owned dirs (prereq #3). **F6** composer php8.4 (prereq #4). **F7** compose `-p`.
- **F8** OTP-логин на dev не автоматизируется → на prod оператор логинится своим аккаунтом (реальный SMS) — не блокер.
- **F9** [[test_personas]] role_id'ы устарели (факт: AGENT=3, GL=10, RD=9, SUPPORT=7, PM=8) — обновить memory.
- **F-obs** rusaifin/фронты не в Prometheus scrape (Track B follow-up). **F-sec** PAT в git-remote dev rusaifin (ротировать).
- **PERF-NOTE** admin staff/project=3.4MB/4.3s, support staff=202KB/5.2s — кандидат на пагинацию (Phase 5/Track G), не блокер.

Связано: [[git_workflow_dev_main]], [[infra_map]], [[mysql_trigger_super_1419]], [[prod_infrastructure]], [[observability_stack]].
