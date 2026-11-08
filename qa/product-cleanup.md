# Удаление лишнего блока контактов и ретушь товаров

Из HTML удалены только абзац о территории/адресе отгрузки и карточка ближайшего склада со всеми дочерними элементами. CSS контактов настроен на две колонки и одну колонку на мобильных; убран унаследованный внутренний отступ последнего блока. Другие тексты и элементы сайта не изменены.

## Изображения

Использован встроенный imagegen, режим редактирования исходников. Отредактированы три фотографии с наложенной корпоративной надписью. Все исходники оставлены без изменений.

- assets/images/euro.jpg → assets/images/euro-clean.webp, 1040 × 784.
- assets/images/standard.webp → assets/images/standard-clean.webp, 1040 × 780; используется в двух карточках 1200 × 1000.
- assets/images/used.jpg → assets/images/used-clean.webp, 1040 × 780.

Результаты imagegen оптимизированы в WebP без растягивания. Проверены по отдельности и в каталоге: наложенной надписи нет, древесина и края досок выглядят естественно. Мелкие физические товарные клейма сохранены. Фото new.jpg и custom.jpg без водяных знаков не изменены, фотография склада не изменена. Внешние фотографии для замены не использовались. Генеративное редактирование восстанавливает скрытые надписью детали, а не извлекает исходные пиксели из-под неё.

## Финальные запросы imagegen

### euro.jpg

Use case: precise-object-edit. Edit target is this existing catalog product photograph of a wooden euro pallet. Owner authorizes watermark removal. Remove ONLY the large semi-transparent overlaid company wordmark/logo crossing the center of the image (the broad gray Cyrillic lettering and linear logo spanning the top planks and white backdrop). Inpaint the covered wood with realistic matching grain, board edges, gaps, and lighting. Keep the exact pallet design, number and arrangement of boards, perspective, proportions, position, white background, and shadows. Keep small authentic dark product stamps on the wooden blocks unchanged. Do not substitute a different pallet, do not crop, do not add text, do not blur or paint flat patches. Output the same landscape composition, with no remaining superimposed company watermark.

### standard.webp

Use case: precise-object-edit. Edit this exact supplied product photograph of a used wooden industrial pallet. Owner authorizes removing the watermark. Remove the large overlaid semi-transparent WHITE company name and line-logo across the front center, including the thin horizontal lines, and restore realistic wood texture and natural plank edges underneath. Preserve the same worn pale timber, knots, wear, nail marks, number/width/spacing of top planks, pallet footprint and construction, same three-quarter perspective, same size and positioning relative to white background, same lighting and shadows. Preserve existing dark small physical stamps, if any. Keep the wide industrial 1200x1000 type, not a narrow EUR pallet. No different product, no cropping, no new logo, no superimposed text, no watermark, no blurry areas, no painted rectangles. Natural realistic catalog product photography, exact original geometry as far as possible.

### used.jpg

Use case: precise-object-edit. Edit target: this exact photograph of a used wooden EUR pallet on white background, owner-authorized watermark removal. Remove ONLY the large overlaid translucent gray company wordmark and line-logo spanning the top central planks and adjacent background. Reconstruct matching natural grain, worn wood coloration, plank edges, narrow gaps and shadows without blur, flat paint, or artifacts. Preserve exact original pallet shape, construction, five upper planks, proportions, camera viewpoint, three-quarter orientation, white background, positioning, lighting and shadow. Keep small genuine dark physical product stamps (EPAL/EUR and other product marks) on the blocks; these are part of the product, not the superimposed watermark. Retain the used second-sort appearance and natural wear, not a pristine new pallet. No unrelated product, no cropping, no new text, no company branding, no overlaid watermark. A faithful cleaned product photograph.

## Проверка

Chromium, localhost:8080, кеш отключён. На 375, 768, 1366 и 1920 px проверены отсутствие удалённых DOM-узлов, два оставшихся блока контактов, шесть карточек и загрузка всех изображений. Скриншоты cleanup-catalog-375/1920.png и cleanup-contacts-375/1920.png просмотрены. Ошибок JS и HTTP нет, горизонтального переполнения нет.

DOM-сравнение с версией до работы после исключения двух удалённых узлов и трёх изменённых путей фотографий подтвердило совпадение остальных текстов, метаданных, ссылок, полей и действий. Повторная проверка меню, фильтров, модального окна, обеих форм и их валидации прошла. JS не изменялся. Фотографий, требующих дополнительной ручной ретуши водяных знаков, среди используемых карточек не выявлено.
