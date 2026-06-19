---
id: F-0115
flow: education
dimension: correctness
severity: P2
confidence: likely
services: [rusaifin]
status: open
---

## Симптом
Product-визибилити учебных материалов реализована только в листинге разделов (`getEducation`), но НЕ в эндпоинтах вложенных разделов и документов раздела → агент может прочитать метаданные (name + file code) материалов чужого продукта, перебирая `section_id`.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/.../EducationController.php:46,67-81` — `getEducation` фильтрует обучения по продуктам проектов юзера (AGENT/CLIENT/GROUP_LEADER).
- `…/EducationController.php:110-124` (`getEducationParentSections`) — `EducationSection::where('parent_id',$id)` без product-скоупа.
- `…/EducationController.php:358-366` (`getEducations`) — `Education::where('section_id',$id)` без product-скоупа.
- Роут `education/{id}/docs` (`routes/api.php:421`) под `CheckPermission:education.get`, но parent-sections-роут нужно проверить отдельно (если только `auth:oauth` — скоуп обходится полностью).

## Триггер / repro
Агент, которому материалы продукта X скрыты в листинге, перебирает `section_id` → `GET /api/education/{section}/docs` → name+file code чужого продукта.

## Корневая причина (гипотеза)
Product-скоуп применён только в одном из трёх read-методов. Утечка ограничена метаданными (не сам файл) → P2; возможно by-design (требует подтверждения владельца).

## Радиус поражения
Метаданные учебных материалов вне продуктового скоупа агента.

## Направление фикса
Вынести product-скоуп в общий scope модели и применить во всех трёх read-методах; либо подтвердить by-design.
