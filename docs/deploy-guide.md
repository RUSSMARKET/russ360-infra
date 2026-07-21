# Деплой Russ360 — руководство

Живой документ, правим по мере изменения процесса. Обновлён: **2026-07-02**.
Аудитория: все разработчики. CI/CD нет — все деплои = git-pull-на-сервере + скрипты ниже.

Сервер (dev и prod на одной машине): `ssh root@82.146.57.149` (вход только по ключу).
dev-домены (`dev.*`) = staging. Сервер shared с чужими проектами — host-wide команды (reload fpm, prune, rebuild vhosts) не гонять без нужды.

---

## 0. Шпаргалка

| Репо (GitHub) | Что это | Прод-путь | Канонический прод-деплой | Проверка после |
|---|---|---|---|---|
| `fintech` | Nuxt SPA (агенты) | `/home/fintech/web/fintech.rusaifin.ru/public_html` | `bash deploy/deploy.sh` (под root) | `bash deploy/verify-deploy.sh`; `/auth/`=200; fake-чанк=404 |
| `findatabase` (rusaifin) | Laravel monolith, host PHP | `/home/fintech/web/server.rusaifin.ru/public_html` | `git pull --ff-only origin main` | `curl /api/auth/me` → 401 JSON |
| `rusaiauth` | OAuth2/OIDC IdP, docker | `/home/Rusaiauth/web/sso.rusaifin.ru` | `./deploy-back.sh prod` | **`iss` в JWT** + curl JS-ассета логина |
| `rusaicore` | Core-домен, docker, S2S-only | `/home/Rusaicore/web/server.rusaicore.ru/public_html` | bundle-доставка + rebuild (см. §5) | `curl 127.0.0.1:9011/api/v1` → 404 = жив |
| `rusaisklad_back` | Inventory API, docker | `/home/Rusaisklad/web/server.rusaisklad.ru/public_html` | `./deploy-back.sh prod` | `/api/auth/session` → 401 JSON |
| `rusaisklad_front` | Nuxt SPA (склад) | `/home/Rusaisklad/web/rusaisklad.ru/app` | `UPDATE_BIBLI=true ./deploy/deploy.sh prod` | https://rusaisklad.ru открывается, вход |
| `russ360-infra` | Ops/observability | `/root/russ360-infra` | `git pull` | — |

Обёртки: `/root/dev.sh` и `/root/prod.sh` покрывают **только два фронта** (`rf`=fintech, `rs`=sklad-front), интерактивны (confirm). Бэкенды — только скриптами из таблицы.

---

## 1. Общие правила (для всех реп)

1. **Поток веток:** работа в `dev` (крупная фича — своя ветка → merge в `dev`) → деплой на dev-стенд → ручная проверка → merge `dev`→`main` → деплой `main` на prod. Хотфикс — тоже через `dev` (merge в `main` без деплоя на dev допустим). Прямые коммиты в `main` — не наш поток.
2. **Прод деплоится только с `main`** и только осознанным решением, не «по дороге».
3. **Нас двое и мы оба пушим.** Перед merge/деплоем: `git fetch` + посмотреть, что уехало в `origin/dev` и `origin/main` от второго разработчика. Не деплоить чужие полусырые коммиты молча — синхронизироваться.
4. **Uncommitted-дрейф на серверах запрещён.** dev-стенд = staging, `git status` там должен быть чистым, иначе ломается следующий `git pull` (и `/root/dev.sh` молча делает `reset --hard && clean -fd` — снесёт живые правки).
5. **`git` из-под root** в чужих каталогах — всегда `git -c safe.directory='*' ...`.
6. **Миграции:** `php artisan migrate --force` — только штатные. Каталог `database/migrations/cutover/` (rusaiauth/rusaicore) обычным migrate НЕ подхватывается и руками НЕ запускается — только в согласованное окно через `--path=database/migrations/cutover`.
7. **Правки `.env` docker-сервисов** не применяются рестартом: env бейкается при создании контейнера → `docker compose -p <project> -f <file> up -d --force-recreate <service>`.
8. **Всегда указывать `-p <project>`** в docker compose (`rusaiauth_back_prod`, `rusaicore_back_prod`, `rusaisklad_back_prod`, …) — без него compose создаёт дубли по имени директории.

---

## 2. fintech (фронт агентов) — `RUSSMARKET/fintech`

Статический Nuxt (SPA, `nuxt generate`), nginx раздаёт `.output/public`.

**Прод:**
```bash
cd /home/fintech/web/fintech.rusaifin.ru/public_html
bash deploy/deploy.sh        # под root (.output/.chunk-attic root-owned)
bash deploy/verify-deploy.sh
```
`deploy.sh` делает: `git pull --ff-only origin main` → снапшот чанков в `.chunk-attic` → `npm run generate:update` (с rollback предыдущей раздачи при падении сборки) → аддитивный возврат чанков прошлых билдов → ретенция.

**Почему НЕ голый `npm run generate:update`:** generate сносит старые `/_nuxt/*` чанки; у всех, кто держит открытую вкладку, ломается подгрузка страниц (в т.ч. страницы входа) → волна «белых/чёрных экранов» (инциденты 2026-06-10, 06-29, 07-02).
⚠️ Известный долг: `/root/prod.sh rf` и `/root/dev.sh rf` внутри гоняют именно голый generate — для **прода** пока пользоваться `deploy/deploy.sh` напрямую.
**Страховочная сетка:** root-cron `*/2` `/root/russ360-infra/scripts/fintech-chunk-attic.sh` аддитивно возвращает чанки прошлых билдов даже после «неправильного» деплоя (retention 30 сут). Это страховка, а не замена скрипту.

**Dev:** `/root/dev.sh rf` (= `git pull origin dev` + `npm run generate:update`) — допустимо, ретенция чанков на dev не нужна.

**Грабли:**
- Сборка = `generate`, НЕ `npm run build` (build = SSR, не будет `index.html` → 403).
- `bibli` пинится в `package-lock.json` конкретным коммитом `russ-ui#main`; если сборка падает на «X is not exported by bibli» — обновить пин коммитом в репо (`npm install bibli@github:RUSSMARKET/russ-ui#main --package-lock-only`), не дрейфовать lock на сервере.
- Странная «старая» сборка при чистом логе → протухший Vite-кэш: `rm -rf .nuxt .output node_modules/.cache` и пересобрать. Результат проверять grep'ом новой строки в `.output/public/_nuxt/`, не по логу.
- root-owned `node_modules/.nuxt/.output` после чужого деплоя: сносить под root, ставить под нужным юзером.

---

## 3. rusaifin (бэкенд) — `RUSSMARKET/findatabase`

Host PHP 8.1-fpm под Hestia, **не docker** (в docker только websockets `rusaifin_ws_*-reverb`). БД — host MySQL.

**Прод:**
```bash
cd /home/fintech/web/server.rusaifin.ru/public_html
git -c safe.directory='*' checkout -- storage/api-docs/api-docs.json   # генеренный swagger грязнит дерево
git -c safe.directory='*' pull --ff-only origin main
# миграции, если есть:
sudo -u fintech php artisan migrate --force
```
- opcache `validate_timestamps=On` → код подхватывается сам за ~2с. **`systemctl reload php8.1-fpm` НЕ нужен** (и он host-wide на shared-сервере).
- Правки config/route → `sudo -u fintech php artisan optimize:clear`.
- Проверка: `curl -s https://server.rusaifin.ru/api/auth/me` → 401 JSON.

**Dev:** `cd /home/fintech/web/dev.server.rusaifin.ru/public_html && git pull origin dev` — этого достаточно.

**Грабли:** `APP_DEBUG=true` на проде — намеренно, не «чинить». Локальная копия часто на `dev`, отстающем от `main` — прод-хотфикс класть поверх `origin/main`.

---

## 4. rusaiauth (SSO/IdP) — `RUSSMARKET/rusaiauth`

Docker, **код запечён в образ** (bind только `.env`, storage, keys) → после pull обязателен rebuild. Compose: `-p rusaiauth_back_prod -f compose.back.prod.yaml`, сервис **`auth-app`** (не `app`).

**Прод:**
```bash
cd /home/Rusaiauth/web/sso.rusaifin.ru
./deploy-back.sh prod          # полный: pull → up -d --build → migrate → passport:keys(no force) → синк ассетов
# или быстрый (rebuild только auth-app):
./deploy-back-fast.sh prod
```
Деплоить **только этими скриптами**: они синкают `public/build` из образа на хост (nginx раздаёт статику с хоста — без синка получается split-brain и белый экран логина; рецидив был 2026-06-25 при ручном `up -d --build`).

**Обязательные пост-проверки (каждый деплой):**
```bash
# 1) iss в свежем JWT — без него ВСЕ resource-серверы вернут 401 на все токены:
UUID=$(docker exec rusaiauth_back_prod-app php artisan tinker \
  --execute='echo DB::table("identity_users")->value("id");' | tail -1)
docker exec rusaiauth_back_prod-app php /var/www/html/scripts/mint-smoke-token.php \
  "$UUID" rusaifin-spa "openid profile" | tail -1 | cut -d. -f2 | base64 -d
# в payload должен быть "iss":"https://sso.rusaifin.ru"

# 2) не только HTML логина, но и его JS-ассет (HTML рендерится и при битых ассетах):
curl -s https://sso.rusaifin.ru/auth -o /tmp/a.html
grep -oE '/build/assets/[^"]+\.js' /tmp/a.html | head -1 | \
  xargs -I{} curl -s -o /dev/null -w '%{http_code} {}\n' https://sso.rusaifin.ru{}
```

**Dev:** код bind-mount → `./deploy-back-fast.sh dev` (pull без rebuild).

**Грабли:**
- git pull — через ssh-alias `github-rusaiauth` (дефолтный ключ root видит только russ-ui).
- На проде в `package-lock.json` лежит **незакоммиченный** рабочий bibli-пин — не стешить/не откатывать (закоммиченный пин сломан, build образа упадёт).
- rusaiauth читает MySQL rusaifin (реферал-проверка регистрации): при **любой ротации пароля `fintech_user`** обновлять `RUSAIFIN_DB_PASSWORD` в `.env` rusaiauth + force-recreate (инцидент 2026-07-02, регистрация по ссылке молча ломается; диагностика: `docker logs rusaiauth_back_prod-app | grep referal_db_check_failed`).
- `TRUSTED_PROXIES` — только CIDR (`172.16.0.0/12`), `*` не работает.
- Smoke `/oauth/token` с client_id не-UUID даёт 500 (pgsql quirk) — тестировать с UUID-форматным client_id (корректный ответ 401).

---

## 5. rusaicore — `RUSSMARKET/rusaicore`

Docker, код запечён в образ. S2S-only: наружу не торчит, потребители ходят на `127.0.0.1:9011` (prod) / `:8011` (dev) или по docker-DNS `http://rusaicore/api/v1`.

**Прод: `git pull` НЕ работает** (нет deploy-ключа; хвост — завести ключ). Доставка через bundle:
```bash
# локально:
git bundle create /tmp/rc.bundle origin/main --not <prod_HEAD>
scp /tmp/rc.bundle root@82.146.57.149:/tmp/
# на проде:
cd /home/Rusaicore/web/server.rusaicore.ru/public_html
git -c safe.directory='*' fetch /tmp/rc.bundle refs/remotes/origin/main
git -c safe.directory='*' merge --ff-only FETCH_HEAD
git -c safe.directory='*' update-ref refs/remotes/origin/main <sha>
# rebuild (код в образе!):
docker compose -p rusaicore_back_prod -f compose.back.prod.yaml build app
docker compose -p rusaicore_back_prod -f compose.back.prod.yaml up -d app
docker exec rusaicore_back_prod-app-1 php /var/www/html/artisan migrate --force
```
Проверка: `curl http://127.0.0.1:9011/api/v1` → 404 = фреймворк жив. Hestia-vhost `server.rusaicore.ru` — мёртвый дефолт, для проверок не использовать.

**Dev:** та же bundle-схема (dev-репо тоже без ключа), project `rusaicore_back_dev`, health `curl 127.0.0.1:8011/up`. ⚠️ `compose.back.dev.yaml` на dev локально правлен (порты) — `reset --hard` затрёт.

---

## 6. rusaisklad_back — `RUSSMARKET/rusaisklad_back`

Docker, код запечён. Remote настроен (pull работает).

**Прод / dev:**
```bash
cd /home/Rusaisklad/web/server.rusaisklad.ru/public_html   # dev: dev.server.rusaisklad.ru
./deploy-back.sh prod    # или dev; без аргумента определит env по APP_ENV из .env
```
Скрипт: pull → rebuild app → up → migrate.

**Грабли:**
- После recreate контейнер php-fpm иногда не резолвит `auth-db`/соседей (`could not translate host name`) → `docker restart rusaisklad_back_prod-app-1`.
- `RolePageSeeder` на проде не гонять (перезатирает порядок меню) — точечные вставки.
- Локально compose только с `-p rusaisklad_back_local`.

---

## 7. rusaisklad_front — `RUSSMARKET/rusaisklad_front`

Nuxt в docker-контейнере (`rusaisklad_front_*-nuxt-dev-1`), nginx проксирует. Репо живёт в `app/`, не `public_html`.

**Прод / dev:**
```bash
cd /home/Rusaisklad/web/rusaisklad.ru/app        # dev: dev.rusaisklad.ru/app
git pull origin main                              # dev: origin dev
UPDATE_BIBLI=true ./deploy/deploy.sh prod         # dev: ... dev
```
Или обёрткой: `/root/prod.sh rs` / `/root/dev.sh rs`.

**Грабли:**
- `bibli` здесь — gitignored `./bibli` (curl-вендор с хоста), обновляется флагом `UPDATE_BIBLI=true`; npm-git внутри docker виснет — не переделывать.
- ⚠️ Известный gap: нет chunk-recovery/attic как у fintech — при stale-chunk будет голый белый экран. Механизм раздачи другой (nuxt-контейнер), фикс отдельной задачей.

---

## 8. russ360-infra — `RUSSMARKET/russ360-infra`

Ops-репо: observability (`/root/observability`, контейнеры `obs-*`), скрипты (`scripts/`), ir-tripwire, chunk-attic страж.

```bash
cd /root/russ360-infra && git pull
```
Изменения конфигов Prometheus/Loki/Grafana — перезапуск соответствующего `obs-*` контейнера. Cron-хозяйство root'а: `ir-tripwire.sh` (hourly), `fintech-chunk-attic.sh` (*/2) — при правках скриптов cron сам подхватит новую версию по пути.

---

## 9. После деплоя: куда смотреть

- **GlitchTip** (клиентские и серверные ошибки, проекты: rusaicore, rusaiauth, rusaifin, rusaisklad-back, fintech-front, rusaisklad-front):
  ```bash
  docker exec obs-glitchtip-postgres psql -U glitchtip -d glitchtip -c \
   "select i.last_seen::timestamp(0), p.name, i.count, left(i.title,60) \
    from issue_events_issue i join projects_project p on p.id=i.project_id \
    where i.last_seen > now() - interval '2 hours' order by i.last_seen desc limit 20;"
  ```
  Всплеск `Couldn't resolve component` / `*.default undefined` после деплоя фронта = chunk-волна.
- **Логи бэкендов:** docker-сервисы — `docker logs <container> --since 30m`; rusaifin — `storage/logs/laravel.log` на хосте.
- **Access-логи доменов:** `/var/log/apache2/domains/<domain>.log` (не nginx!).
- **Успешность входов (просадка после деплоя auth-цепочки):** количество свежих строк `oauth_access_tokens` в БД rusaiauth по часам vs прошлые дни.

## 10. Смежное

- **Обновить dev-БД с прода (4 базы, с анонимизацией):** `ssh root@82.146.57.149 /root/refresh-dev-from-prod.server.sh`.
- **Обёртка для навигации/логов/artisan по сервисам:** `scripts/russ` в монорепе (`russ where --fetch`, `russ ssh <svc> <env>`, `russ artisan <svc> <env> -- <cmd>`).
- Известные внешние факторы, которые НЕ лечатся деплоем: флапы timeweb-edge (чёрные экраны у части сетей при здоровом origin), недоставка OTP-SMS части абонентов MTS.

## TODO процесса (кандидаты на улучшение)

- [ ] Починить fintech-деплой внутри `/root/prod.sh` (`rf` должен звать `deploy/deploy.sh`, а не голый generate).
- [ ] Deploy-ключ для rusaicore prod/dev → уйти от bundle-схемы на обычный `git pull`.
- [ ] Вычистить GitHub-PAT из remote-URL dev-реп (токены в открытом виде).
- [ ] chunk-recovery/attic для rusaisklad_front.
- [ ] Единый `deploy.sh <env> <service|all>` в russ360-infra (отложено).
