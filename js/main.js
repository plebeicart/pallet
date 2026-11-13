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
// The server is the only authority for enabling real collection.
const FORM_ENDPOINT = '/api/requests';
let requestsEnabled = false;
let requestToken = '';
async function loadRequestConfig() {
 try {
  const response = await fetch(`${FORM_ENDPOINT}/config`, { cache: 'no-store', signal: AbortSignal.timeout(5000) });
  const config = await response.json();
  requestsEnabled = response.ok && config.enabled === true && typeof config.token === 'string';
  requestToken = requestsEnabled ? config.token : '';
 } catch { requestsEnabled = false; requestToken = ''; }
 document.querySelectorAll('.demo-notice').forEach(el => el.hidden = requestsEnabled);
 document.querySelectorAll('[data-lead] [type=submit]').forEach(el => {
  if (!el.disabled) el.innerHTML = `${requestsEnabled ? 'Отправить заявку' : 'Проверить заявку'} <span>↗</span>`;
 });
}
loadRequestConfig();
setInterval(loadRequestConfig, 3600000);
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
 closeMenu();
 if (dialog.querySelector('[type=submit]').disabled) { dialog.showModal(); document.body.classList.add('modal-open'); return; }
 if (dialogTitle.textContent !== subject) dialog.querySelector('.form-status').textContent = '';
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
 const valid = /^\+?[0-9 ()-]+$/.test(input.value.trim()) && digits.length >= 10 && digits.length <= 15;
 input.setCustomValidity(valid || !input.value ? '' : 'Укажите корректный телефон: от 10 до 15 цифр.');
}
document.querySelectorAll('[name=phone]').forEach(input => { input.addEventListener('input', () => validatePhone(input)); input.addEventListener('blur', () => validatePhone(input)); });
document.querySelectorAll('[data-lead]').forEach(form => {
 form.removeAttribute('onsubmit');
 const name = form.elements.name;
 const requestIds = new Map();
 let submitting = false;
 name.addEventListener('input', () => name.setCustomValidity(name.value.trim().length >= 2 ? '' : 'Укажите имя: не менее двух символов.'));
 form.addEventListener('submit', async e => {
 e.preventDefault();
 if (submitting) return;
 validatePhone(form.elements.phone);
 name.setCustomValidity(name.value.trim().length >= 2 ? '' : 'Укажите имя: не менее двух символов.');
 if (!form.reportValidity()) return;
 const status = form.querySelector('.form-status');
 if (!requestsEnabled) { status.textContent = 'Поля заполнены корректно. Это демонстрационный режим — заявка не отправлена. Для заказа: +7 (999) 117-88-28 или vip@паллет.com.'; return; }
 const submit = form.querySelector('[type=submit]');
 const payload = { ...Object.fromEntries(new FormData(form)), form: form.dataset.form };
 const signature = JSON.stringify(payload);
 if (!requestIds.has(signature)) requestIds.set(signature, crypto.randomUUID());
 payload.request_id = requestIds.get(signature);
 payload.token = requestToken;
 const controls = [...form.elements].filter(el => !el.disabled);
 controls.forEach(el => el.disabled = true);
 submitting = true; submit.disabled = true; form.setAttribute('aria-busy', 'true');
 status.textContent = 'Отправляем заявку…';
 try {
  const response = await fetch(FORM_ENDPOINT, {
   method: 'POST', headers: { 'Content-Type': 'application/json' },
   body: JSON.stringify(payload), signal: AbortSignal.timeout(90000)
  });
  const result = await response.json();
  if (!response.ok || result.ok !== true) {
   const errors = {
    422: 'Проверьте поля и согласие. Если страница открыта давно, обновите её перед заполнением.',
    429: 'Слишком много попыток. Попробуйте позже или позвоните нам.',
    503: response.headers.get('Retry-After') === '30' ? 'Письмо не принято. Повторите через 30 секунд или позвоните нам.' : 'Приём заявок сейчас недоступен. Пожалуйста, позвоните нам.',
    409: 'Эта заявка уже отправляется. Подождите и проверьте результат.',
    502: 'Не удалось подтвердить отправку. Пожалуйста, позвоните нам, чтобы избежать дублирования заявки.'
   };
   status.textContent = errors[response.status] || 'Не удалось отправить заявку. Позвоните: +7 (999) 117-88-28.';
   return;
  }
  status.textContent = 'Заявка отправлена. Спасибо! Мы свяжемся с вами в рабочее время.';
  form.reset();
  if (form.dataset.form === 'modal') form.elements.subject.value = dialogTitle.textContent;
  await loadRequestConfig();
 } catch {
  status.textContent = 'Не удалось подтвердить отправку. Пожалуйста, позвоните, чтобы уточнить результат: +7 (999) 117-88-28.';
 } finally {
  submitting = false; controls.forEach(el => el.disabled = false); form.removeAttribute('aria-busy');
 }
 });
});
// Enable native controls only after every submit handler is installed.
document.querySelectorAll('[data-lead] [type=submit]').forEach(button => button.disabled = false);
if ('IntersectionObserver' in window && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
 const observer = new IntersectionObserver(entries => entries.forEach(entry => { if(entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); } }), { threshold: .08 });
 document.querySelectorAll('.section-head, .direction, .about-grid, .steps article, .contact-grid').forEach(el => { el.classList.add('reveal-ready'); observer.observe(el); });
}
