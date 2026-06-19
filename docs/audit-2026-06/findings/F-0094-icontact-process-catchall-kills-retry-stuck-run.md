---
id: F-0094
flow: icontact-sync
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaisklad_back]
status: open
---

## Симптом
`process()` оборачивает весь пайплайн в `try { ... } catch (Throwable)` и помечает задачу FAILED вместо re-throw → очередь видит job успешным → `tries=3`/`backoff` никогда не срабатывают (мёртвый авто-retry). Отдельно: если воркер убит (OOM/timeout) ДО catch, задача застревает в transient-статусе, `ensureNoActiveRun` держит run QUEUED/RUNNING вечно → все будущие `start`/`retry` проекта бросают «уже выполняется».

## Доказательства (file:line)
- `rusaisklad_back/app/Services/Inventory/IContactSyncTaskProcessorService.php:125-133` — catch-all → FAILED, без re-throw.
- `app/Jobs/Inventory/RunIContactSyncTaskJob.php:20,31-34` — `$tries=3`/`backoff()` (не задействуются).
- `app/Services/Inventory/IContactSyncOrchestratorService.php:265-278` — `ensureNoActiveRun` блокирует новые синки при QUEUED/RUNNING.

## Триггер / repro
(а) Транзиентный iContact 5xx → задача FAILED, авто-retry нет несмотря на `tries=3` (только ручной `retryTask`). (б) SIGKILL воркера mid-run → проект навсегда заблокирован от новых синков.

## Корневая причина (гипотеза)
Catch-all конвертирует retryable-сбой в терминальный статус; нет stuck-run reaper / timeout-реконсиляции статуса; retry только ручной.

## Радиус поражения
Операционный: тихий не-retry транзиентных сбоев + жёсткий лок синка проекта после аномального выхода воркера.

## Направление фикса
Re-throw retryable-исключений (различать retryable vs terminal), чтобы `tries`/`backoff` работали; добавить `failed()`-handler и/или reaper, освобождающий run'ы, застрявшие в QUEUED/RUNNING дольше TTL.
