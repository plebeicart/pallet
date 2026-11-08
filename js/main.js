 'use strict';
// CSS owns the timeline; cleanup never waits for images, fonts, or network requests.
(() => {
 const intro = document.querySelector('.page-intro');
 if (!intro) return;
 const dismiss = () => intro.remove();
 if (matchMedia('(prefers-reduced-motion: reduce)').matches) { dismiss(); return; }
 intro.addEventListener('animationend', event => {
  if (event.target === intro) dismiss();
 });
 // Defensive cleanup if animation events are interrupted. CSS also hides it without JS.
 setTimeout(dismiss, 2400);
})();
// Set to your same-origin backend URL after implementing the contract in README.md.
const FORM_ENDPOINT = '';
const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
function closeMenu() { navigation.classList.remove('open'); menuButton.setAttribute('aria-expanded', 'false'); menuButton.setAttribute('aria-label', 'Открыть меню'); }
menuButton.addEventListener('click', () => { const opened = menuButton.getAttribute('aria-expanded') !== 'true'; navigation.classList.toggle('open', opened); menuButton.setAttribute('aria-expanded', String(opened)); menuButton.setAttribute('aria-label', opened ? 'Закрыть меню' : 'Открыть меню'); });
navigation.addEventListener('click', e => { if (e.target.closest('a')) closeMenu(); });
document.addEventListener('click', e => { if (!e.target.closest('.header')) closeMenu(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && navigation.classList.contains('open')) { closeMenu(); menuButton.focus(); } });
matchMedia('(min-width: 69.14375em)').addEventListener('change', e => { if (e.matches) closeMenu(); });
const header = document.querySelector('.header');
const backTop = document.querySelector('.back-top');
let ticking = false;
function updateScroll() { header.classList.toggle('scrolled', scrollY > 20); backTop.hidden = scrollY < 650; ticking = false; }
addEventListener('scroll', () => { if (!ticking) { requestAnimationFrame(updateScroll); ticking = true; } }, { passive: true });
updateScroll();
backTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }));
const products = [...document.querySelectorAll('.product')];
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
 document.querySelectorAll('[data-filter]').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button)); });
 let count = 0;
 products.forEach(product => { const show = button.dataset.filter === 'all' || product.dataset.category.split(' ').includes(button.dataset.filter); product.hidden = !show; if(show) count++; });
 document.querySelector('#filter-status').textContent = `Показано товаров: ${count}`;
}));
const dialog = document.querySelector('#request-dialog');
const dialogTitle = document.querySelector('#dialog-title');
const dialogDescription = document.querySelector('#dialog-description');
const serviceDetails = {
 repair: ['Ремонт и восстановление', 'Восстанавливаем бывшие в употреблении деревянные поддоны. Объём работ и возможность ремонта определяем после оценки состояния партии.'],
 treatment: ['Фитосанитарная обработка', 'Обработка деревянной тары по стандарту ISPM 15. Требования к обработке, документам и маркировке согласовываем с учётом направления перевозки.'],
 recycle: ['Утилизация поддонов', 'Помогаем освободить склад от непригодной деревянной тары. Согласуем состав партии, условия вывоза и утилизации.'],
 delivery: ['Доставка поддонов', 'Доставляем поддоны собственным транспортом. Адрес, объём, график и стоимость перевозки согласовываем до отгрузки. Возможен самовывоз по согласованию.'],
 marking: ['Маркировка поддонов', 'Наносим маркировку на деревянную тару. Клеймо, логотип или штрихкод — вид маркировки и требования обсуждаем при заказе.'],
 pooling: ['Пулинг паллет', 'Организуем оборот возвратной паллетной тары. Схему обмена, учёта и обслуживания подбираем под логистические процессы предприятия.']
};
function openRequest(subject, description = '') {
 closeMenu(); dialog.querySelector('form').reset(); dialog.querySelector('.form-status').textContent = '';
 dialogTitle.textContent = subject; dialogDescription.textContent = description;
 dialogDescription.hidden = !description; dialog.querySelector('[name=subject]').value = subject;
 dialog.showModal(); document.body.classList.add('modal-open');
}
document.querySelectorAll('[data-request]').forEach(button => button.addEventListener('click', () => openRequest(button.dataset.request)));
document.querySelectorAll('[data-service]').forEach(button => button.addEventListener('click', () => openRequest(...serviceDetails[button.dataset.service])));
dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', e => { const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close(); });
dialog.addEventListener('close', () => document.body.classList.remove('modal-open'));
function validatePhone(input) {
 const digits = input.value.replace(/\D/g, '');
 const valid = /^[+\d\s()\-]+$/.test(input.value) && digits.length >= 10 && digits.length <= 15;
 input.setCustomValidity(valid || !input.value ? '' : 'Укажите корректный телефон: от 10 до 15 цифр.');
}
document.querySelectorAll('[name=phone]').forEach(input => { input.addEventListener('input', () => validatePhone(input)); input.addEventListener('blur', () => validatePhone(input)); });
document.querySelectorAll('[data-lead]').forEach(form => {
 const name = form.elements.name;
 name.addEventListener('input', () => name.setCustomValidity(name.value.trim().length >= 2 ? '' : 'Укажите имя: не менее двух символов.'));
 form.addEventListener('submit', async e => {
 e.preventDefault(); validatePhone(form.elements.phone);
 name.setCustomValidity(name.value.trim().length >= 2 ? '' : 'Укажите имя: не менее двух символов.');
 if (!form.reportValidity()) return;
 const status = form.querySelector('.form-status');
 if (!FORM_ENDPOINT) { status.textContent = 'Поля заполнены корректно. Это демонстрационный режим — заявка не отправлена. Для заказа: +7 (999) 117-88-28 или vip@паллет.com.'; return; }
 const submit = form.querySelector('[type=submit]'); submit.disabled = true; status.textContent = 'Отправляем заявку…';
 try { const response = await fetch(FORM_ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.fromEntries(new FormData(form))) }); const result = await response.json(); if (!response.ok || result.ok !== true) throw new Error('Submission failed'); status.textContent = 'Заявка отправлена. Спасибо! Мы свяжемся с вами в рабочее время.'; form.reset(); }
 catch { status.textContent = 'Не удалось отправить заявку. Попробуйте позже или позвоните: +7 (999) 117-88-28.'; }
 finally { submit.disabled = false; }
 });
});
if (FORM_ENDPOINT) { document.querySelectorAll('.demo-notice').forEach(el => el.hidden = true); document.querySelectorAll('[type=submit]').forEach(el => el.innerHTML = 'Отправить заявку <span>↗</span>'); }
if ('IntersectionObserver' in window && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
 const observer = new IntersectionObserver(entries => entries.forEach(entry => { if(entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); } }), { threshold: .08 });
 document.querySelectorAll('.section-head, .direction, .about-grid, .steps article, .contact-grid').forEach(el => { el.classList.add('reveal-ready'); observer.observe(el); });
}
