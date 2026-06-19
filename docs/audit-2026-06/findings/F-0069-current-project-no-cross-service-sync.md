---
id: F-0069
flow: project-switch
dimension: data-integrity
severity: P3
confidence: confirmed
services: [rusaifin, rusaisklad_back, rusaicore]
status: open
---

## Симптом

Текущий проект ведётся двумя независимыми локальными столбцами: `rusaifin.users.current_project_external_id` и `rusaisklad_back.users.current_project_id`. Переключение проекта в одном сервисе/фронте не отражается в другом. «Текущий проект» отсутствует в Core (не shared concept). Multi-project юзер видит разные активные проекты в двух UI.

## Доказательства (file:line)

- `rusaifin/app/Services/Project/CurrentProjectService.php` (`syncCurrentProject`/persist) — пишет только `current_project_external_id` локально.
- `rusaisklad_back/app/Services/Projects/CurrentProjectService.php:201-215` (`persistCurrentProject`) — пишет только `current_project_id` локально.
- `grep current_project` по `rusaifin/app/Domain/Core`, `rusaisklad_back/app/Domain/Core`, `rusaicore/app` → пусто (нет push/pull, нет колонки текущего проекта в Core).

## Триггер / repro

Юзер с ≥2 проектами переключается в sklad → в rusaifin current_project остаётся прежним → два UI работают в разных «активных проектах». Для agent (1 проект) не проявляется.

## Корневая причина (гипотеза)

Текущий проект смоделирован как чисто локальное состояние каждого сервиса; общего контракта/поля в Core нет.

## Радиус поражения

UX/консистентность для multi-project пользователей (РГ/менеджеры/support на нескольких проектах). Не порча данных, а рассинхрон проекции между сервисами.

## Направление фикса

Архитектурное решение — НЕ чинить без обсуждения с владельцем: либо принять как осознанное локальное состояние (задокументировать), либо вынести «current project» в Core-профиль и читать обоими сервисами.
