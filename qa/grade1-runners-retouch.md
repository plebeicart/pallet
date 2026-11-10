# Ретушь нижних досок первого сорта

Встроенный image_gen, точечное редактирование исходного assets/images/standard-clean.webp. Исходник сохранён. Результат: assets/images/pallet-grade1-clean-runners.webp, 1040×780, WebP quality 92. В index.html изменён только src соответствующей карточки. Остальные фотографии не менялись.

Удалены заметные тёмные загрязнения на передних нижних досках, сохранены естественная текстура и следы эксплуатации. Результат генеративной ретуши визуально проверен; побайтовое совпадение текстур с исходником не гарантируется.

Запрос:

Use case: precise-object-edit. Edit target: this exact supplied photograph of a used wooden pallet, 1040x780. Gently clean ONLY the conspicuous dark gray dirt smears and grime on the BOTTOM runner boards, especially the two exposed front-facing bottom wood sections between the support blocks in the lower third of the pallet. Restore locally matching pale weathered timber grain in those stained patches, keeping knots, nail marks, scratches and light wear. Keep the used first-grade character; not pristine new wood, not uniform smooth paint. CRITICAL invariants: preserve the exact original pixel composition, product size and position, perspective, board count, all geometry, all support blocks, original lighting and shadows. Keep ALL upper deck boards completely unchanged. Keep white background untouched. Do not restyle, recolor or globally brighten the pallet. No blur, no flat rectangles, no new markings. Same framing and 4:3 aspect ratio.
