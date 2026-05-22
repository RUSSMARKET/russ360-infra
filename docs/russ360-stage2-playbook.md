# Russ360 — Stage 2 Cutover Playbook

Runbook на окно финального Stage 2 cutover'а (переключение читателей `rusaifin` на Core API).
Формат и тон — как у `rusaicore/docs/russmarket360/04-cutover-playbook.md` (M2, 2026-05-13).

> **Статус документа:** живой. На 2026-05-20 группа α (dual-write + seed-команды) уже live на prod. Группа β (reader switch) **не начата** — здесь шаблон, конкретные controllers подставим при подготовке окна.

---

## 0. TL;DR

| Что | Состояние на 2026-05-20 |
|---|---|
| α: seed/backfill команды | ✅ live на prod (2026-05-13/18) |
| α: dual-write attach/detach/leader | ✅ live на prod (2026-05-18) |
| α: PUT→PATCH fix в Core gateways | ✅ live на prod (2026-05-20) |
| α: reconcile orphans | ✅ dry-run чист (0 orphans, 2026-05-20) |
| β: reader switch rusaifin → Core | ⛔ не начата |
| Stage 1 хвост (locations + disabled projects) | ✅ закрыт (2026-05-18) |

Окно cutover'а — определяется когда β-ветка будет готова. Скорее всего delivery в окно ~2-3 часа в будний день после 12:00 МСК (по аналогии с M2 2026-05-13).

---

## 1. Состояние «сейчас» (pre-cutover baseline)

### 1.1 Что уже работает в prod

- **OAuth2/OIDC** — все 4 backend + 2 фронта, JWT с `iss` claim через `IssuerAwareAccessToken`.
- **Core зеркало rusaifin**:
  - `core.employees` — 299 (255 added в окно M2 + 38 pre-existing + 6 догнатых).
  - `core.projects` — 9 active + 4 inactive (disabled). 1 pre-existing (default).
  - `core.project_memberships` — 277 пар.
  - `core.operational_locations` — 243 (202 active + 38 inactive + 3 ranger одиночных).
  - `core.operational_location_assignments` — ~4627 open (live + исторические), 0 orphans (reconcile 2026-05-20).
- **Dual-write best-effort**:
  - `PointService::attachAgent/detachAgent/setLeader` → синхронно пишет в Core + legacy `project_point_agents`.
  - 409 на Core (membership missing, location not found) — проглатывается, legacy success.
  - Все update'ы — через **PATCH** (5 gateways, исправлено 2026-05-20).
- **rusaifin.project_points.core_location_external_id** — заполнен у всех 243 точек (char(36) + index).

### 1.2 Что **ещё не делает** Core

- Не отдаёт читателям rusaifin. UI и `auth()->user()->...` в ~200 контроллерах rusaifin **всё ещё** читают `project_points` / `project_point_agents` напрямую.
- Reverb (rusaifin_ws_prod) не подписан на Core events.

### 1.3 Известные drift'ы / технический долг

- `rusaifin.project_points` дубликаты id 66 / 202 (см. `[[rusaifin_duplicate_points_66_202]]`) — не блокер, помечаем при cutover'е.
- `RUSAIAUTH_DB_*` env в rusaifin/rusaisklad использует superuser — security debt, не блокер.
- bibli pipeline на rusaisklad_front prod docker сломан (см. `[[rusaisklad_front_bibli_docker_blocker]]`) — workaround эфемерный, при recreate контейнера развалится. Если в окне cutover'а будет фронт-правка — придётся повторять workaround.

---

## 2. Pre-flight checklist (T-24h до окна)

Все команды read-only / dry-run — выполняем без подтверждения.

### 2.1 Health дамп

```bash
# 1. Reconcile orphan assignments (dry-run)
cd /home/dolgan/russ360/rusaifin
php artisan tinker --no-interaction --execute='
$svc = app(\App\Domain\Core\Gateways\CoreOperationalLocationAssignmentReadGateway::class);
$open = $svc->listOpen(["per_page" => 100]);
echo "open_in_core=" . count($open["data"]) . "\n";
'

# 2. Dual-write success rate (последние сутки)
# Логи rusaifin: storage/logs/laravel.log на host
ssh root@82.146.57.149 'grep -E "Core (assignment|membership)" /home/fintech/web/server.rusaifin.ru/public_html/storage/logs/laravel.log | tail -50'

# 3. Sanity counts legacy vs Core (must be close, диффы — известные disabled projects)
ssh root@82.146.57.149 'mysql findatabase -e "
  SELECT COUNT(*) FROM project_point_agents WHERE ended_at IS NULL;
"'
# vs ожидаемое open в core (≈ same N плюс leader-pairs)
```

### 2.2 Дампы pre-cutover

```bash
ssh root@82.146.57.149 '
  STAMP=$(date -u +%Y%m%dT%H%M%SZ)
  cd /home/Rusaiauth/web/sso.rusaifin.ru/dumps
  mysqldump -u root findatabase | gzip > rusaifin_pre-stage2_${STAMP}.sql.gz
  docker exec rusaicore_back_prod-pgsql-1 pg_dump -U core core | gzip > rusaicore_pre-stage2_${STAMP}.sql.gz
  echo "dumps в /home/Rusaiauth/web/sso.rusaifin.ru/dumps/"
'
```

### 2.3 Verify β-кода

- В rusaifin dev: feature-flag `STAGE2_READERS_FROM_CORE=true|false` (или per-controller flag — решим при разработке β).
- Все читатели прошли code-review.
- E2E smoke на dev зелёный (login, /agents, /points, /map, attach-detach, leader, logout).
- `git log dev..main` — пусто или только safe-deploy'ы.

### 2.4 Подготовка SSH/доступов

```bash
# Проверка SSH (port 22 для прод — работает)
ssh root@82.146.57.149 'whoami && uptime'

# Проверка git push для rusaifin (SSH:443 через ssh.github.com если 22 заблокирован)
cd /home/dolgan/russ360/rusaifin
git -c "url.ssh://git@ssh.github.com:443/.insteadOf=git@github.com:" fetch origin --dry-run
```

---

## 3. Cutover steps — группа β (reader switch)

**Окно T0 = старт.** Длительность — оценка 60-90 минут (без учёта подготовки).

### 3.1 [T0] Pre-flight verify

- Чекни ещё раз 2.1 (reconcile, dual-write rate).
- Пинг команды: «Stage 2 cutover starts, expect 5-10min UI degradation if rollback».

### 3.2 [T0+5] Merge dev → main (rusaifin)

```bash
cd /home/dolgan/russ360/rusaifin
git checkout dev && git pull origin dev
git checkout main && git pull origin main
git merge dev --ff-only      # должен быть FF; если нет — STOP, разбираемся
git -c "url.ssh://git@ssh.github.com:443/.insteadOf=git@github.com:" push origin main
```

### 3.3 [T0+10] Deploy на prod (rusaifin)

```bash
ssh root@82.146.57.149 '
  cd /home/fintech/web/server.rusaifin.ru/public_html
  sudo -u fintech git fetch origin
  sudo -u fintech git -c safe.directory="*" checkout master   # prod-ветка
  sudo -u fintech git -c safe.directory="*" reset --hard origin/main
  sudo -u fintech composer install --no-dev --optimize-autoloader
  sudo -u fintech php artisan migrate --force    # если миграции есть; если нет — пропустить
  sudo -u fintech php artisan config:cache
  sudo -u fintech php artisan route:cache
  systemctl restart php8.3-fpm
'
```

### 3.4 [T0+20] Enable reader-switch flag

Шаблон — конкретный механизм определим при разработке β. Варианты:

**Вариант A (env flag):**
```bash
ssh root@82.146.57.149 '
  cd /home/fintech/web/server.rusaifin.ru/public_html
  sudo -u fintech sed -i "s/^STAGE2_READERS_FROM_CORE=.*/STAGE2_READERS_FROM_CORE=true/" .env
  sudo -u fintech php artisan config:cache
  systemctl reload php8.3-fpm
'
```

**Вариант B (deploy кода без флага, ветка содержит читателей):** flag не нужен, cutover = деплой ветки.

### 3.5 [T0+25] Smoke prod

```bash
# Backend smoke (curl с админ-токеном)
TOKEN=$(ssh root@82.146.57.149 'docker exec rusaiauth_back_prod-app php /var/www/html/scripts/mint-smoke-token.php <admin_uuid> fintech-web "user:read project:read"')
curl -H "Authorization: Bearer $TOKEN" https://server.rusaifin.ru/api/agents | jq '.data | length'
curl -H "Authorization: Bearer $TOKEN" https://server.rusaifin.ru/api/projects | jq '.data | length'
```

Параллельно — ручной smoke в браузере (login админом + одним агентом + одним leader'ом):
- /agents — список агентов виден
- /points — список точек виден, агенты привязаны
- attach/detach агента — мгновенно обновляется
- /reports — не падает на Carbon

---

## 4. Rollback процедуры

### 4.1 «Тёплый» rollback (rolling back code, dual-write остаётся)

Если smoke 3.5 падает:

```bash
ssh root@82.146.57.149 '
  cd /home/fintech/web/server.rusaifin.ru/public_html
  sudo -u fintech git -c safe.directory="*" reset --hard <pre-cutover SHA>
  sudo -u fintech composer install --no-dev --optimize-autoloader
  sudo -u fintech php artisan config:cache
  sudo -u fintech php artisan route:cache
  systemctl restart php8.3-fpm
'
```

Если был **вариант A (env flag)** — достаточно сменить флаг на `false` + cache clear:
```bash
ssh root@82.146.57.149 '
  cd /home/fintech/web/server.rusaifin.ru/public_html
  sudo -u fintech sed -i "s/^STAGE2_READERS_FROM_CORE=.*/STAGE2_READERS_FROM_CORE=false/" .env
  sudo -u fintech php artisan config:cache
  systemctl reload php8.3-fpm
'
```

Pre-cutover SHA фиксируем перед окном (см. 2.2 — выписать `git rev-parse HEAD` в чат).

### 4.2 «Холодный» rollback (база)

Только если есть drift / corruption (вряд ли — reader switch не пишет):

```bash
# Restore rusaifin MySQL
ssh root@82.146.57.149 '
  gunzip -c /home/Rusaiauth/web/sso.rusaifin.ru/dumps/rusaifin_pre-stage2_<STAMP>.sql.gz \
    | mysql -u root findatabase
'
# rusaicore PG restore — аналогично через pg_restore
```

**Не предусмотрено** для штатного β — только аварийный сценарий.

---

## 5. Post-cutover monitoring (T+0 ... T+24h)

### 5.1 Чек T+15min

- Логи rusaifin: `tail -f storage/logs/laravel.log` — нет всплеска 500.
- Логи rusaicore: `docker logs -f rusaicore_back_prod-app-1` — нет 4xx-шторма от rusaifin.
- Reverb: `docker logs rusaifin_ws_prod-reverb-1 --since 15m` — WS клиенты подключаются.
- Метрики (если будут — пока нет Grafana).

### 5.2 Чек T+1h

- Открытых ассignments в Core: `core.operational_location_assignments WHERE ended_at IS NULL` — не должно резко прыгнуть.
- Юзеры-агенты залогинены, /agents в браузере админа не пустой.

### 5.3 Чек T+24h

- Прогнать reconcile (2.1) — orphans=0.
- Логи Sentry / Laravel error log за сутки — глазами.
- Спросить MacallanS / агентов — есть ли странности в UI.

---

## 6. После «закрытия» окна

1. Tag коммит: `git tag -a stage2-cutover-prod -m "Stage 2 reader switch cutover 2026-MM-DD"`.
2. Обновить `[[m2_prod_cutover_done]]` → создать `stage2_prod_cutover_done.md`.
3. Удалить dual-write код **не сразу** — оставить минимум 1-2 недели как safety net. Целевая ветка для удаления — отдельный PR после Stage 3 (writes из rusaifin переезжают в Core).
4. Закрыть/обновить `docs/russ360-stage2-playbook.md` — отметить «executed YYYY-MM-DD» и архивировать конкретные команды.

---

## 7. Связанные документы и memory

- `rusaicore/docs/russmarket360/04-cutover-playbook.md` — M2 playbook (исторический snapshot).
- `rusaicore/docs/russmarket360/07-implementation-roadmap.md` — milestones M0–M5.
- `docs/russ360-audit-2026-05-18.md` — состояние системы после Stage 1.
- `docs/stage2-cutover-sprint-plan.md` — задачи A1..A8 спринта.
- `[[m2_prod_cutover_done]]`, `[[stage1_locations_mirrored_2026-05-18]]`, `[[stage2_partial_predeploy_prod]]`, `[[stage2_put_to_patch_bugfix]]` — memory с деталями.

## 8. Открытые вопросы (заполнить при разработке β)

- Какие конкретно controllers переключаем? Полный реестр через grep `project_points`, `project_point_agents`, `ProjectPoint::`, `ProjectPointAgent::` по rusaifin/app/.
- Делаем ли batch или по сервисам/доменам (один PR = один контроллер)?
- Feature flag per-controller или один глобальный?
- Что с UI fintech-front — переключаем эндпоинт API или эндпоинты остаются те же, меняется только источник в backend?
- Reverb events — нужно ли подписывать на Core, или legacy events достаточно?
