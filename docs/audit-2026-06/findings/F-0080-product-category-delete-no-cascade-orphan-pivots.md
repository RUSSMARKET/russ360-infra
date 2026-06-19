---
id: F-0080
flow: products-catalog
dimension: data-integrity
severity: P2
confidence: likely
services: [rusaifin]
status: open
---

## Симптом
Удаление категории продукта и открепление продукта от проекта не чистят зависимые pivot-строки → orphan-привязки: продукты ссылаются на удалённую категорию; продукт, «убранный из проекта», остаётся привязан ко всем точкам этого проекта (`point_products`) и виден агентам.

## Доказательства (file:line)
- **Категория:** `rusaifin/app/Http/Controllers/Product/ProductController.php` `deleteProductCategories()` — `$categories = ProductCategory::find($id); $categories->delete();` без обнуления/перепривязки `products.category_id`. Читатели грузят `with('category')` → null-категория в выдаче.
- **Проект→точки:** `rusaifin/app/Http/Controllers/Project/ProjectController.php:1012` — `$project->products()->detach($validated['product_id'])` чистит только `projects_products`. Точки проекта сохраняют продукт в `point_products` (отдельная таблица, `Point::products()` → `point_products`). Каскада project-detach → point_products нет нигде.

## Триггер / repro
1. Удалить категорию, на которую ссылаются продукты → `products.category_id` указывает на несуществующую строку; `getProducts`/`getPointProducts` отдают null-category.
2. Добавить продукт в проект → разнести по точкам (`system/add-product-to-points` или sync) → `DELETE /project/{id}/product/{product_id}` → продукт исчез из проекта, но остался в `point_products` всех его точек и виден агентам.

## Корневая причина (гипотеза)
Отсутствие каскадной чистки зависимых pivot при удалении/откреплении на уровне приложения (и, вероятно, FK без `ON DELETE`). Класс orphan-привязок (родственно F-0002/F-0010 по природе «частичная/несогласованная мутация связей»), новый домен (продукты rusaifin).

## Радиус поражения
Каталог продуктов: висячие category-ссылки в выдаче; продукты, отключённые от проекта, но активные на точках. Не Core-сущности (локальный домен rusaifin), поэтому ограничено rusaifin.

## Направление фикса
При detach продукта из проекта — каскадно чистить `point_products` по точкам проекта в транзакции; при удалении категории — обнулять/перепривязывать `products.category_id` (или запрет удаления непустой категории).
