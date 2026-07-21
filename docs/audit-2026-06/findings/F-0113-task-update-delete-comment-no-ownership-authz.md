---
id: F-0113
flow: tasks
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaifin]
status: closed
---

## Симптом
Любой аутентифицированный не-disabled пользователь может обновить, удалить, прокомментировать и менять исполнителей ЛЮБОЙ задачи по её id. Деструктивный IDOR без проверки владения.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Tasks/TaskController.php:191-207` (`updateTask`) — только `exists:tasks,id` (`:194`), затем `new TaskService($task_id)->update($validated)`. Нет проверки, что юзер = manager/executor/co_executor/observer.
- `:250-257` (`deleteTask`), `:376-390` (`addTaskComment`), `:475-480` (`updateTaskComment`), `:543-551` (`deleteTaskComment`) — без проверки принадлежности.
- `rusaifin/routes/api.php:295-302` — только `['auth:oauth', UserIsNotDisabled::class]`, БЕЗ `CheckPermission` (контраст: clients/education под `*.management`).
- `TaskService` authz-слоя не содержит.

## Триггер / repro
Любой юзер → `PUT /api/tasks/{любой_id}` с произвольным `executor_id` → переназначает исполнителя чужой задачи; `DELETE /api/tasks/{любой_id}` → soft-delete чужой задачи; `POST /api/tasks/{id}/comments` → комментарий в чужую задачу.

## Корневая причина (гипотеза)
Контроллер не сверяет ownership, в `TaskService` нет authz, роуты без permission-гейта. Tasks — единственный из трёх доменов (clients/tasks/education) без `CheckPermission`.

## Радиус поражения
Вся таблица tasks + комментарии; деструктив (delete/переназначение) любым авторизованным.

## Направление фикса
Ownership-проверка (manager/executor/co_executor/observer или ADMIN) в update/delete/comment, либо `CheckPermission` на роутах 295-302.

## Статус закрытия

Закрыто коммитом `5979d29` (rusaifin), проверено по коду на `origin/main` 2026-07-21.
В `TaskService` добавлен `hasAccess()` (ADMIN либо manager/executor/co_executor/observer); вызывается в `updateTask`/`deleteTask`/комментариях.
