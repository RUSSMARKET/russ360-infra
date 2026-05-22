# rusaiauth_reader — read-only PG role для внешних сервисов

## Зачем

`rusaifin` и `rusaisklad_back` ходят в БД `rusaiauth` за `identity_users` (резолв phone/email → identity UUID, OAuth backfill). Исторически они подключались под суперюзером `rusaiauth_{dev,prod}` — это полный owner БД, что нарушает principle of least privilege.

Решение — отдельная роль `rusaiauth_reader` с единственным правом `SELECT ON public.identity_users`.

## Где используется

| Сервис | env | host:port | DB |
|---|---|---|---|
| rusaifin dev | `/home/fintech/web/dev.server.rusaifin.ru/public_html/.env` | `127.0.0.1:5436` | `rusaiauth_dev` |
| rusaifin prod | `/home/fintech/web/server.rusaifin.ru/public_html/.env` | `127.0.0.1:5434` | `rusaiauth_prod` |
| rusaisklad_back dev | `/home/Rusaisklad/web/dev.server.rusaisklad.ru/public_html/.env` | `auth-db:5432` (docker net) | `rusaiauth_dev` |
| rusaisklad_back prod | `/home/Rusaisklad/web/server.rusaisklad.ru/public_html/.env` | `rusaiauth_back_prod-db:5432` | `rusaiauth_prod` |

В `.env` каждого сервиса:
```
RUSAIAUTH_DB_USERNAME=rusaiauth_reader
RUSAIAUTH_DB_PASSWORD=<random per env>
```

Пароль рандомный per-env (dev и prod не равны), хранится только в `.env` на сервере и (опционально) в `prod-secrets/`.

## Setup на новой среде

SQL-скрипт: `rusaiauth/database/scripts/create-reader-role.sql` (idempotent).

```bash
# 1. Сгенерить пароль
PASS=$(openssl rand -hex 24)

# 2. Запустить скрипт под суперюзером БД rusaiauth
docker cp rusaiauth/database/scripts/create-reader-role.sql <auth-db-container>:/tmp/
docker exec <auth-db-container> psql -U <superuser> -d <db> \
    -v reader_password="$PASS" \
    -f /tmp/create-reader-role.sql

# 3. Прописать $PASS в .env rusaifin и rusaisklad_back на этом окружении
#    (RUSAIAUTH_DB_USERNAME=rusaiauth_reader, RUSAIAUTH_DB_PASSWORD=$PASS)

# 4. Перечитать конфиг:
#    - rusaifin (native php-fpm): php artisan config:clear
#    - rusaisklad_back (docker compose): force-recreate app container
#      (env injected at container creation, не из mounted .env)
#
#    docker compose -p rusaisklad_back_<env> -f compose.back.<env>.yaml \
#        up -d --force-recreate app
```

## Smoke

```bash
# SELECT должен работать
docker exec <auth-db-container> env PGPASSWORD="$PASS" \
    psql -U rusaiauth_reader -d <db> -c "SELECT count(*) FROM identity_users;"

# INSERT должен быть отказан (SQLSTATE 42501 permission denied)
docker exec <auth-db-container> env PGPASSWORD="$PASS" \
    psql -U rusaiauth_reader -d <db> \
    -c "INSERT INTO identity_users (id, external_id, phone, created_at, updated_at) \
        VALUES (gen_random_uuid(), gen_random_uuid(), '+79990000000', now(), now());"
```

## Rollback

Если что-то ломается под reader-ролью — временно вернуть в `.env` старые `RUSAIAUTH_DB_USERNAME/PASSWORD` (есть backup `.env.backup-YYYYMMDD-HHMMSS-c1` рядом). Recreate контейнера (для sklad) или `config:clear` (для rusaifin native).

## История

- 2026-05-21 — введено, см. Track C item C1 в `docs/final-stage-cutover-cleanup-sprint-plan.md`.
