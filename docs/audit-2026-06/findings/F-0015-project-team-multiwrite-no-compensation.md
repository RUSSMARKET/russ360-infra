---
id: F-0015
flow: project-support-membership
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
Создание/обновление проекта с командой выполняет несколько Core-вызовов без транзакции/компенсации; сбой Core посередине оставляет проект с урезанной/отсутствующей командой, ответ 500.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Project/ProjectController.php:268-284` — `createProject`: `Project::Create` (MySQL) → `CoreProjectWriteGateway->create` (Core HTTP) → `setProjectManager` + `applyRegionalDirectors` (ещё N Core HTTP).
- `ProjectService.php:220-229` — `setRegionalDirectors`: сначала в цикле `endMembership` старых РД, потом `coreMembershipCreate` новых — каждый отдельный HTTP. Нет `DB::transaction` (она и не покрыла бы Core) и нет компенсации.
- Core-клиент: `timeout_seconds≈3.0`, `retries=0`.

## Триггер / repro
Core-таймаут/5xx посередине: в `setRegionalDirectors` 2 старых РД сняты (`ended`), а `create` третьего падает → проект с урезанной командой. В `createProject` локальный + Core проект созданы, но PM/РД не записаны → проект без команды, ответ 500.

## Корневая причина (гипотеза)
Мульти-write по HTTP-границе сервиса без саги/идемпотентного реплея на уровне всей операции (идемпотентность есть только per-call через conflict-handling).

## Радиус поражения
create/update проекта при сетевой нестабильности Core; рассинхрон состава команды. (Тот же класс, что F-0004/F-0012, но другой код-путь.)

## Направление фикса (1-2 строки, НЕ реализовано)
Реплей-безопасный порядок (сначала добавить желаемых, потом закрыть лишних) + outbox/реконсиляция; как минимум обработка отказа с откатом локального project в `createProject`.

## Проверка статуса

**2026-07-21 — сверено с `origin/main`: дефект НА МЕСТЕ.**
`ProjectController:268-284` — `Project::Create` → Core-гейтвей → `setProjectManager` → `applyRegionalDirectors` без try/catch, транзакции и компенсации.
