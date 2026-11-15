import './style.css';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { MotionPathPlugin } from 'gsap/MotionPathPlugin';
import Lenis from 'lenis';
import { createHeroScene } from './heroScene.js';
import { buildCoverageMap } from './coverageMap.js';

gsap.registerPlugin(ScrollTrigger, MotionPathPlugin);

/* ------------------------------------------------------------------ */
/* Configuración del cliente — reemplazar con los datos reales          */
/* ------------------------------------------------------------------ */
const CONFIG = {
  whatsapp: '59170000000', // número en formato internacional sin "+" (PENDIENTE)
  whatsappLabel: '+591 700 00000',
  email: 'ventas@axiomenergy.bo', // PENDIENTE
};

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ---------------- Smooth scroll ---------------- */
let lenis = null;
if (!reducedMotion) {
  lenis = new Lenis({ duration: 1.15, smoothWheel: true });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((t) => lenis.raf(t * 1000));
  gsap.ticker.lagSmoothing(0);
}
$$('a[href^="#"]').forEach((a) =>
  a.addEventListener('click', (e) => {
    const id = a.getAttribute('href');
    if (id.length < 2) return;
    const target = $(id);
    if (!target) return;
    e.preventDefault();
    closeMenu();
    if (lenis) lenis.scrollTo(target, { offset: -70 });
    else target.scrollIntoView({ behavior: 'smooth' });
  })
);

/* ---------------- Tema ---------------- */
$('#themeToggle').addEventListener('click', () => {
  const root = document.documentElement;
  const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
  root.dataset.theme = next;
  hero?.setTheme(next);
  try { localStorage.setItem('axiom-theme', next); } catch (e) { /* sin storage */ }
});

/* ---------------- Navegación ---------------- */
const nav = $('#nav');
const burger = $('#burger');
function closeMenu() {
  nav.classList.remove('is-open');
  burger.setAttribute('aria-expanded', 'false');
}
burger.addEventListener('click', () => {
  const open = nav.classList.toggle('is-open');
  burger.setAttribute('aria-expanded', String(open));
});
ScrollTrigger.create({
  start: 60,
  onUpdate: (self) => nav.classList.toggle('is-scrolled', self.scroll() > 60),
});
// enlace activo según sección
$$('main section[id]').forEach((sec) => {
  const link = $(`.nav__links a[href="#${sec.id}"]`);
  if (!link) return;
  ScrollTrigger.create({
    trigger: sec,
    start: 'top 50%',
    end: 'bottom 50%',
    onToggle: (self) => link.classList.toggle('is-active', self.isActive),
  });
});

/* ---------------- Datos de contacto ---------------- */
const waUrl = (text = '') => `https://wa.me/${CONFIG.whatsapp}${text ? `?text=${encodeURIComponent(text)}` : ''}`;
$('#waFloat').href = waUrl('Hola Axiom Energy, quisiera información sobre combustibles.');
$('#waLabel').textContent = CONFIG.whatsappLabel;
$('#mailLabel').textContent = CONFIG.email;
$('#year').textContent = new Date().getFullYear();

/* ---------------- Reloj Santa Cruz ---------------- */
const clock = $('#clock');
const fmt = new Intl.DateTimeFormat('es-BO', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'America/La_Paz' });
const tickClock = () => (clock.textContent = fmt.format(new Date()));
tickClock();
setInterval(tickClock, 1000);

/* ---------------- Hero 3D ---------------- */
let hero = null;
try {
  hero = createHeroScene($('#heroCanvas'), {
    labelsEl: $('#heroLabels'),
    reducedMotion,
    theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  });
} catch (err) {
  console.warn('WebGL no disponible, se muestra el hero sin 3D.', err);
  document.documentElement.classList.add('no-webgl');
}

/* ---------------- Preloader + intro ---------------- */
function intro() {
  const tl = gsap.timeline();
  tl.to('.preloader__bar span', { scaleX: 1, duration: reducedMotion ? 0.1 : 0.7, ease: 'power2.inOut' })
    .to('.preloader', { yPercent: -100, duration: reducedMotion ? 0.1 : 0.8, ease: 'power3.inOut' })
    .set('.preloader', { display: 'none' });

  if (reducedMotion) {
    hero?.intro();
    return;
  }
  tl.from('.nav', { y: -30, opacity: 0, duration: 0.6 }, '-=0.3')
    .from('.hero__title .word', { yPercent: 110, rotate: 4, duration: 0.9, stagger: 0.07, ease: 'power4.out' }, '-=0.4')
    .from('[data-hero]', { y: 24, opacity: 0, duration: 0.7, stagger: 0.08 }, '-=0.6')
    .add(() => hero?.intro(), '-=1.6')
    .add(startRotator)
    .add(startHud, '-=0.4');
}

/* ---------------- Palabra rotativa del título ---------------- */
function startRotator() {
  const items = $$('#rotator .rotator__item');
  const rot = $('#rotator');
  if (!items.length) return;
  let i = 0;
  gsap.set(items, { yPercent: 110, opacity: 0 });
  gsap.set(items[0], { yPercent: 0, opacity: 1 });
  rot.style.setProperty('--w', `${items[0].offsetWidth}px`);
  if (reducedMotion) return;
  const next = () => {
    const cur = items[i];
    i = (i + 1) % items.length;
    const nxt = items[i];
    gsap.timeline()
      .to(rot, { '--bar': 0, duration: 0.35, ease: 'power2.in' })
      .set(rot, { '--w': `${nxt.offsetWidth}px` })
      .to(cur, { yPercent: -110, opacity: 0, duration: 0.55, ease: 'power3.in' }, 0)
      .fromTo(nxt, { yPercent: 110, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.7, ease: 'power3.out' }, 0.45)
      .to(rot, { '--bar': 1, duration: 0.6, ease: 'power3.out' }, 0.7);
  };
  setInterval(next, 2600);
}

/* ---------------- Panel de tanques (ilustrativo) ---------------- */
function startHud() {
  $$('.hud__row').forEach((row, idx) => {
    const bar = $('i', row);
    const out = $('b', row);
    const state = { v: 0 };
    let level = Number(row.dataset.level);
    const render = () => {
      bar.style.transform = `scaleX(${state.v})`;
      out.textContent = `${Math.round(state.v * 100)}%`;
    };
    gsap.to(state, { v: level, duration: 1.6, delay: idx * 0.15, ease: 'power3.out', onUpdate: render });
    if (reducedMotion) return;
    // simula consumo y recarga
    setInterval(() => {
      level = level < 0.3 ? 0.92 : Math.max(0.2, level - 0.02 - Math.random() * 0.05);
      gsap.to(state, { v: level, duration: level > 0.9 ? 1.4 : 0.9, ease: 'power2.inOut', onUpdate: render });
    }, 2400 + idx * 700);
  });
}
// arranca cuando las fuentes están listas (máximo 1.5 s de espera)
Promise.race([document.fonts?.ready ?? Promise.resolve(), new Promise((r) => setTimeout(r, 1500))]).then(intro);

// la escena se inclina y se aleja al salir del hero
if (hero) {
  ScrollTrigger.create({
    trigger: '.hero',
    start: 'top top',
    end: 'bottom top',
    scrub: true,
    onUpdate: (self) => hero.setScrollProgress(self.progress),
  });
}
gsap.to(['.hero__copy', '.hud', '.hero__facts'], {
  yPercent: -18,
  opacity: 0.15,
  ease: 'none',
  scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true },
});

/* ---------------- Medidor de combustible (progreso de scroll) ---------------- */
const fuel = $('#fuelLevel');
if (fuel) {
  ScrollTrigger.create({
    start: 0,
    end: 'max',
    onUpdate: (self) => (fuel.style.transform = `scaleY(${(1 - self.progress * 0.88).toFixed(3)})`),
  });
}

/* ---------------- Reveals ---------------- */
if (!reducedMotion) {
  gsap.set('[data-reveal]', { y: 40, opacity: 0 });
  ScrollTrigger.batch('[data-reveal]', {
    start: 'top 88%',
    once: true,
    onEnter: (els) => gsap.to(els, { y: 0, opacity: 1, duration: 0.9, stagger: 0.09, ease: 'power3.out', overwrite: true }),
  });
}

/* ---------------- Contadores ---------------- */
$$('[data-count]').forEach((n) => {
  const end = Number(n.dataset.count);
  const obj = { v: reducedMotion ? end : 0 };
  if (reducedMotion) { n.textContent = end; return; }
  gsap.to(obj, {
    v: end,
    duration: 1.8,
    ease: 'power2.out',
    scrollTrigger: { trigger: n, start: 'top 90%', once: true },
    onUpdate: () => (n.textContent = Math.round(obj.v)),
  });
});

/* ---------------- Tarjetas: tilt + spotlight ---------------- */
if (window.matchMedia('(hover: hover)').matches && !reducedMotion) {
  $$('[data-tilt]').forEach((card) => {
    const rx = gsap.quickTo(card, 'rotationX', { duration: 0.5, ease: 'power3' });
    const ry = gsap.quickTo(card, 'rotationY', { duration: 0.5, ease: 'power3' });
    card.addEventListener('pointermove', (e) => {
      const r = card.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width;
      const py = (e.clientY - r.top) / r.height;
      card.style.setProperty('--mx', `${px * 100}%`);
      card.style.setProperty('--my', `${py * 100}%`);
      rx((0.5 - py) * 10);
      ry((px - 0.5) * 12);
    });
    card.addEventListener('pointerleave', () => { rx(0); ry(0); });
  });
}

/* ---------------- Proceso: ruta con camión ---------------- */
(function setupRoute() {
  const path = $('#routePath');
  const truck = $('#routeTruck');
  const steps = $$('.route .step');
  const len = path.getTotalLength();

  // posiciona cada paso sobre la curva (solo se usa en escritorio vía CSS)
  steps.forEach((s, i) => {
    const p = path.getPointAtLength((len * i) / (steps.length - 1));
    s.style.setProperty('--x', `${(p.x / 1600) * 100}%`);
    s.style.setProperty('--y', `${(p.y / 400) * 100}%`);
    s.classList.toggle('step--below', p.y > 200); // texto hacia afuera de la curva
  });

  gsap.set(path, { strokeDasharray: len, strokeDashoffset: len });
  const update = (progress) => {
    steps.forEach((s, i) => s.classList.toggle('is-active', progress >= i / (steps.length - 1) - 0.02));
  };

  const mm = gsap.matchMedia();
  mm.add({ desktop: '(min-width: 900px)', mobile: '(max-width: 899px)' }, (ctx) => {
    const { desktop } = ctx.conditions;
    const tl = gsap.timeline({
      defaults: { ease: 'none' },
      scrollTrigger: {
        trigger: '.process',
        start: desktop ? 'top top' : 'top 70%',
        end: desktop ? '+=1800' : 'bottom 60%',
        pin: desktop ? '.process__pin' : false,
        scrub: 0.6,
        onUpdate: (self) => update(self.progress),
      },
    });
    tl.to(path, { strokeDashoffset: 0 }, 0).to(
      truck,
      { motionPath: { path, align: path, alignOrigin: [0.5, 0.5], autoRotate: true }, duration: 1 },
      0
    );
  });
})();

/* ---------------- Mapa ---------------- */
buildCoverageMap($('#coverageMap'), { reducedMotion });

/* ---------------- Formulario ---------------- */
const range = $('#volRange');
const out = $('#volOut');
const volInput = $('#quoteForm [name="volumen"]');
const nf = new Intl.NumberFormat('es-BO');
range.addEventListener('input', () => {
  out.textContent = `${nf.format(range.value)} L/mes`;
  volInput.value = nf.format(range.value);
});

$('#quoteForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const note = $('#formNote');
  if (!String(f.get('nombre') || '').trim()) {
    note.textContent = 'Por favor, escribe tu nombre.';
    note.classList.add('is-error');
    e.target.nombre.focus();
    return;
  }
  note.classList.remove('is-error');
  const lines = [
    'Hola Axiom Energy, quiero una cotización:',
    `• Nombre: ${f.get('nombre')}`,
    f.get('empresa') && `• Empresa: ${f.get('empresa')}`,
    `• Producto: ${f.get('producto')}`,
    `• Volumen mensual: ${f.get('volumen') || `${nf.format(range.value)} L`}`,
    f.get('lugar') && `• Lugar de entrega: ${f.get('lugar')}`,
    f.get('mensaje') && `• Detalle: ${f.get('mensaje')}`,
  ].filter(Boolean);
  window.open(waUrl(lines.join('\n')), '_blank', 'noopener');
  note.textContent = 'Abrimos WhatsApp con tu solicitud. ¡Gracias!';
});

// recalcula posiciones cuando cargan las fuentes
document.fonts?.ready.then(() => ScrollTrigger.refresh());
