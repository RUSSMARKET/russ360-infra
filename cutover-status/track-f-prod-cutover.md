# Track F — Production Cutover runbook

**Status:** 📋 READY — обновлён 2026-05-28 под фактическое состояние (dev-рехёрсал + BAT prod-mode + perf-фиксы).
**Источник:** Track E dev-rehearsal + сессия 2026-05-28 (полный прогон на restored prod-dump: код, gmp, D5, BAT майский ре-сид, perf-фиксы — зелёный).
**Правило:** PROD, необратимо на живых данных. Каждый шаг — статус в Telegram «RSM Infra» + в этот файл. На каждый шаг ждать «иди».

---

## 🧭 BRANCH-СТРАТЕГИЯ — `dev → main` (НЕ `cutover-final→main`)

Вся валидированная работа лежит на **`dev`**: cutover-final (D-трэки) + Track-E фиксы (gmp F10 / chunk=50 F11 / StaffService-резолв F2-F3 `0b226ee`) + Macallan (`fact_metric_key` shift/reporting) + BAT майские сидеры + 3 perf-фикса этой сессии. Поэтому прод-мердж = **`dev → main` во всех 5 репах** (rusaiauth, rusaicore, rusaifin, rusaisklad_back, rusaisklad_front).

- **Конфликты `dev→main` (проверено 2026-05-28): ТОЛЬКО Dockerfile'ы** — резолв = union (gmp + apcu/obs):
  - rusaicore: `Dockerfile` + `docker/Dockerfile`
  - rusaisklad_front: `Dockerfile.front.dev`
  - rusaiauth / rusaifin / rusaisklad_back: чисто.
- `main` опережает dev на 3-11 коммитов (obs/deploy-хардненинг уехал прямо в прод) — merge их **сохраняет** (это не потеря).

**Perf-фиксы (едут через dev→main, уже на dev):**
- N+1 attachment в getStaff → батч `membershipIndexByEmployee` — rusaifin `d0889f8` (admin staff 6.6с→0.33с).
- detail-relations убраны из списка staff/project — rusaifin `e0990bc` (3.46МБ→1.28МБ).
- per_page для bulk-чтений: rusaicore `719c0bf` (cap 100→2000) + rusaifin `5e95896` (assignments per_page=2000) — staff/project 4.0с→1.0с, 99 Core-запросов→5.

## ⚠️ PRE-WINDOW PREREQUISITES (ДО окна)

1. **gmp на prod (F10).** В Dockerfile rusaicore+rusaisklad_back (app-base stage). После rebuild prod-образов: `docker exec rusaicore_back_prod-app-1 php -r 'var_dump(extension_loaded("gmp"));'` → true. rusaifin (host php8.3) gmp НЕ нужен.
2. **Prod rusaifin checkout — дивергенция (F4).** `cd /home/fintech/web/server.rusaifin.ru/public_html && git fetch && git log --oneline origin/main..HEAD`. Если локальные пустые merge-коммиты → `reset --hard origin/main` под `fintech`. (prod fin на ветке `master`, tracking origin/main.)
3. **Prod root-owned dirs (F5).** `chown -R fintech:fintech .../database/migrations/cutover .../database/scripts` под root (иначе git reset/pull под fintech падает Permission denied).
4. **composer на prod (F6).** Host php8.3, committed lock требует 8.4 → `composer dump-autoload -o --ignore-platform-reqs` (vendor рабочий). core/sklad — install при rebuild (php8.4 контейнер).
5. **Дампы свежие (<2ч) ВСЕХ 4 prod-БД** — rollback и для cutover, и для BAT-ре-сида (BAT необратим). reconcile orphans=0 (projects/locations). Зафиксировать pre-cutover `main`-SHA каждого репо (rollback target).

---

## SEQUENCE

### T0 — Pre-flight
- Grafana открыт (`obs-grafana` ssh-tunnel). Дампы prod свежие. reconcile orphans=0. pre-cutover main-SHA ×5 зафиксированы. Дежурство.

### T0+5 — Maintenance
- rusaifin nginx 503 на write-эндпоинты (read остаётся). Telegram: «начинаем».

### T0+15 — Merge `dev → main` ×5 + push
Порядок: rusaicore → rusaisklad_back → rusaifin → rusaiauth → rusaisklad_front.
- Резолв Dockerfile-конфликтов (core + front): оставить **union** (gmp + apcu/obs — как на dev). Остальное авто-мёржится.
- `git push origin main` каждого. (StaffService-резолв уже в dev `0b226ee` → конфликта НЕТ, в отличие от старого cutover-final→main.)

### T0+20 — Deploy по сервисам (⚠ ВСЕГДА `-p <svc>_back_prod` — F7)
**rusaicore:**
```
cd /home/Rusaicore/web/server.rusaicore.ru/public_html
sudo -u Rusaicore git pull --ff-only origin main
docker compose -p rusaicore_back_prod -f compose.back.prod.yaml build      # gmp
docker compose -p rusaicore_back_prod -f compose.back.prod.yaml up -d
docker exec rusaicore_back_prod-app-1 php artisan migrate --force           # FWD: idempotency_keys (cutover/ пуст у core)
docker exec rusaicore_back_prod-app-1 php artisan config:cache
docker exec rusaicore_back_prod-app-1 php -r 'var_dump(extension_loaded("gmp"));'   # F10 → true
```
**rusaisklad_back:** `-p rusaisklad_back_prod -f compose.back.prod.yaml` build+up → `migrate --force` (**FWD: `transfers_require_documents`**) → config:cache → gmp-check.
**rusaifin (host php-fpm, F4/F5/F6):**
```
cd /home/fintech/web/server.rusaifin.ru/public_html
sudo -u fintech git fetch origin && sudo -u fintech git reset --hard origin/main   # F4
sudo -u fintech composer dump-autoload -o --ignore-platform-reqs                   # F6
sudo -u fintech php artisan migrate --force          # FWD: fact_metric_key ×2 (2026_05_26_000001/000002). НЕ трогает cutover/
sudo -u fintech php artisan config:clear && route:clear && cache:clear
```
⚠ Проверить `migrate --pretend` ПЕРЕД `--force`: должны примениться ТОЛЬКО forward-миграции (fact_metric_key), НЕ cutover/ (D5 — отдельно, шаг T0+40).

### T0+30 — Фронты
- **rusaisklad_front** (transfers-UI): `cd /home/Rusaisklad/web/rusaisklad.ru/app && git pull(main) && UPDATE_BIBLI=true ./deploy/deploy.sh prod` (npm+bibli на хосте, docker build). Резолв Dockerfile.front.dev — union.
- **fintech**: cutover-изменений НЕ имеет; деплой только если есть свои правки в main (`./dev.sh rfp`). Иначе пропустить.

### T0+40 — D5 legacy archive (prod БД `fintech_base`)
⚠ root-mysql `SET GLOBAL` + app-artisan взаимозависимы — выполнять одним блоком (оператор вручную через `!`, auto-mode классификатор блокирует).
```
ORIG=$(mysql -BNe "SELECT @@global.log_bin_trust_function_creators")   # на prod может быть != 0
mysql -e "SET GLOBAL log_bin_trust_function_creators=1"
cd /home/fintech/web/server.rusaifin.ru/public_html
sudo -u fintech php artisan migrate --path=database/migrations/cutover --force   # M2-drops уже применены → только D5
mysql -e "SET GLOBAL log_bin_trust_function_creators=$ORIG"
# verify: 13 триггеров (trg_ro_* ×9 + trg_guard_* ×4)
mysql -BNe "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema='fintech_base' AND (trigger_name LIKE 'trg_ro_%' OR trigger_name LIKE 'trg_guard_%')"
```

### T0+50 — BAT майский ре-сид (на ЖИВЫХ prod-данных, необратимо → rollback = дамп T0)
Решения (2026-05-28): **снос+пересоздание** (RET получают новые id; phone-match не используем); **departed identity — оставить орфанами** (не чистим в окне).
```
# 1) CORE purge + roster
docker exec -i rusaicore_back_prod-pgsql-1 psql -U rusaicore_prod -d rusaicore_prod -v ON_ERROR_STOP=1 \
  < /home/Rusaicore/web/server.rusaicore.ru/public_html/database/scripts/bat-reseed/purge-bat-field.sql
docker exec rusaicore_back_prod-app-1 php artisan db:seed --class=Database\\Seeders\\BatMembershipBackfillSeeder --force
# 2) SKLAD purge + сидеры (НЕ полный DatabaseSeeder — только BAT-цепочка по порядку)
docker exec -i rusaisklad_back_prod-pgsql-1 psql -U rusaisklad_prod_db -d rusaisklad_prod_db -v ON_ERROR_STOP=1 \
  < /home/Rusaisklad/web/server.rusaisklad.ru/public_html/database/scripts/bat-reseed/purge-bat-field.sql
for c in SkuSeeder UserSeeder AssignmentSeeder InventorySeeder; do
  docker exec rusaisklad_back_prod-app-1 php artisan db:seed --class=Database\\Seeders\\$c --force
done
# 3) Кросс-сервис: anchors + identity
docker exec rusaisklad_back_prod-app-1 php artisan core:shadow-sync --write --entity=all
docker exec rusaiauth_back_prod-app php artisan identity:import-from-rusaisklad --write
```
**Verify (как на dev):** балансы СВ по 6 регионам = датасет (итог 18170; Новокузнецк4247/Кемерово3767/Тула3051/Брянск2801/Орёл2160/Смоленск2144); склад=0; as-of 01.05=4010; core BAT-ростер 6 supervisor + 34 promoter(33+Архипова); field anchored 39/39; дублей по phone 0 (на проде phone-match → admin/managers НЕ дублятся, в отличие от dev).

### T0+65 — Smoke critical paths (mint-token + реальный вход оператора)
- mint `<uuid> rusaifin-spa fieldsales.read,core.read` → ADMIN/SUPPORT/RD/GL: `auth/me`,`staff`,`staff/project`,`shift/points` → 2xx, 0×5xx. AGENT: 403 на staff (корректно).
- D2-видимость градуирована (ADMIN>SUPPORT>RD>GL). **Perf:** admin staff/project ~1с / staff ~0.3с (perf-фиксы).
- sklad: `users/hierarchy`/`skus` 2xx; BAT-инвентарь/упрощённые передачи в UI; reconcile orphans=0.
- obs: russ360_* растут, dualwrite_fallback пусто, alerts молчат.

### T0+80 — Снять maintenance, unfreeze. Telegram: «закончили, мониторим».

---

## ROLLBACK
1. Maintenance остаётся.
2. **D5 unlock (~0.7с):** `mysql fintech_base < database/scripts/cutover/unlock-legacy-tables.sql` → 13 триггеров сняты.
3. **Reset main → pre-cutover SHA** ×5 (git reset + rebuild `-p ..._prod` + up; rusaifin — `reset --hard <sha>` + dump-autoload + config:clear).
4. **BAT-ре-сид необратим** → restore prod-БД из дампов T0 (core+sklad+auth). Это главный rollback-кост этого окна.
5. Restart, smoke pre-cutover, unfreeze.

---

## Findings из Track E (постоянные грабли)
- **F10** missing gmp → RS256 1.9с → 500 (gmp в core+sklad Dockerfile). **F11** chunk 100→50 (nginx 414). **F4** divergent fin checkout. **F5** root-owned dirs. **F6** composer php8.4. **F7** compose `-p`.
- **F8** OTP на проде — реальный SMS, оператор логинится своим аккаунтом. **F9** role_id'ы: AGENT=3, SUPPORT_MANAGER=7, PM=8, RD=9, GROUP_LEADER=10.
- **F-obs** rusaifin/фронты не в Prometheus scrape (Track B follow-up). **F-sec** PAT в git-remote dev rusaifin (ротировать).
- **PERF** (после фиксов сессии): admin staff/project ~1с/1.28МБ (было 4с/3.46МБ). Дальнейшее — пагинация (Track G), не блокер.

## Дельта vs Track E rehearsal (что нового в этом окне)
1. Branch `dev→main` (не cutover-final→main) — Dockerfile-only конфликты.
2. Новые forward-миграции: rusaicore idempotency_keys; rusaifin `fact_metric_key`×2; rusaisklad `transfers_require_documents`.
3. **BAT майский ре-сид** (purge-скрипты + сидеры + shadow-sync + identity) — НОВЫЙ шаг T0+50, необратим.
4. rusaisklad_front transfers-UI деплой.
5. perf-фиксы (N+1 / payload / per_page) — авто через dev→main.

Связано: [[git_workflow_dev_main]], [[infra_map]], [[mysql_trigger_super_1419]], [[prod_infrastructure]], [[observability_stack]], [[bat_data_actualization]], `track-e-dev-rehearsal.md`.
