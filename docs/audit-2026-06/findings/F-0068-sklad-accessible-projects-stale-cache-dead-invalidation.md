---
id: F-0068
flow: project-switch
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaisklad_back, rusaifin]
status: open
---

## Симптом

Список доступных проектов в sklad кешируется cross-request на 300с по ключу, не зависящему от набора memberships, а метод инвалидации кеша не вызывается нигде. После изменения membership в Core юзер до 5 минут: видит устаревший список проектов в `/me`, проходит project-selection гейт по старому списку, может `selectCurrentProject` на проект, к которому доступ только что отозван.

## Доказательства (file:line)

- `rusaisklad_back/app/Services/Projects/CurrentProjectService.php:23` — `ACCESSIBLE_PROJECTS_TTL_SECONDS = 300`.
- `:34-53` — `getAccessibleProjects`: cross-request `Cache::put($crossRequestKey, $projects, 300)`.
- `:74-81` — `accessibleProjectsCacheKey` = `sprintf('%d:%s', user->id, user->role?->code)` — НЕ включает fingerprint набора memberships/проектов.
- `:55-60` — `invalidateAccessibleProjectsCache` определён, но `grep` по `app/` → НЕТ ни одного call-site (только определение). То же в `rusaifin/app/Services/Project/CurrentProjectService.php:54` (только определение).
- `selectCurrentProject` валидирует доступ против этого кеша (`getAccessibleProjects()->contains(...)`); `CheckPermission` гейт NO_PROJECTS / PROJECT_SELECTION тоже читает кеш.

Ограничитель радиуса (верифицировано): effective-роль читается СВЕЖЕЙ каждый запрос — `CoreProjectMembershipProvider::loadForEmployee` мемоизирует только per-request (`:101-105`, без `Cache::put`). При отозванном membership `getEffectiveRole` (`CurrentProjectService.php:150`) вернёт `null` → `hasPermission`/`getPages` откажут. Поэтому доступа к ДАННЫМ отозванного проекта stale-кеш НЕ даёт — только проход bootstrap-гейта и залипший `current_project_id`.

## Триггер / repro

Юзер залогинен (кеш прогрет на 300с) → в Core снимают/меняют его membership → в течение 300с юзер дёргает `/me` (старый список проектов) или `PUT /projects/current` на старый проект (проходит) / проходит project-selection гейт. Данные отозванного проекта при этом блокируются свежей ролью (403).

## Корневая причина (гипотеза)

Cross-request кеш доступных проектов не инвалидируется ни при каком изменении membership (нет вызова `invalidateAccessibleProjectsCache` из shadow-sync / при изменениях Core), а ключ кеша не зависит от набора проектов. Асимметрия свежести: гейт доступа = кеш 300с, effective-роль = per-request.

## Радиус поражения

Окно ≤300с после любого membership-изменения (переводы, orphan-backfill, увольнение). Эффект: залипший/неверный current_project, проход bootstrap-гейта, stale `available_projects` в `/me`. НЕ утечка данных (роль свежая). rusaifin имеет тот же мёртвый invalidate, но дополнительно защищён ре-валидацией видимости (`StaffVisibilityScopeService::resolveAccessibleProjectExternalIds` отбраковывает current не из свежего Core-набора → worst case пустой результат).

## Направление фикса

Вызывать `invalidateAccessibleProjectsCache($user)` из точек изменения membership (shadow-sync), либо включить hash набора project external_id в ключ кеша; унифицировать свежесть гейта и effective-роли.
