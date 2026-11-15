// Mapa estilizado (no cartográfico) de Santa Cruz: puntos en rejilla dentro de
// un contorno aproximado + ciudades con rutas animadas desde la base.
import { gsap } from 'gsap';

const NS = 'http://www.w3.org/2000/svg';

// Contorno aproximado del departamento (coordenadas 0–100, y hacia abajo).
const OUTLINE = [
  [24, 4], [40, 2], [50, 8], [58, 12], [68, 15], [78, 22], [86, 32], [93, 44], [97, 56],
  [94, 66], [86, 72], [80, 82], [70, 90], [58, 96], [44, 98], [32, 94], [26, 86], [20, 76],
  [12, 66], [8, 54], [10, 42], [14, 30], [18, 16],
];

const BASE = { name: 'Santa Cruz de la Sierra', x: 26, y: 50 };
const CITIES = [
  { name: 'Warnes', x: 27, y: 44 },
  { name: 'Montero', x: 25, y: 38 },
  { name: 'Cotoca', x: 31, y: 51 },
  { name: 'Pailón', x: 38, y: 50 },
  { name: 'San Julián', x: 41, y: 36 },
  { name: 'Guarayos', x: 34, y: 20 },
  { name: 'San Ignacio', x: 66, y: 34 },
  { name: 'Puerto Suárez', x: 92, y: 60 },
  { name: 'Cabezas', x: 27, y: 68 },
  { name: 'Camiri', x: 24, y: 88 },
];

function inside(x, y, poly) {
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

function el(tag, attrs, parent) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  parent?.appendChild(n);
  return n;
}

export function buildCoverageMap(svg, { reducedMotion = false } = {}) {
  if (!svg) return;
  const dots = el('g', { class: 'map-dots' }, svg);
  for (let y = 1; y < 100; y += 2.4) {
    for (let x = 1; x < 100; x += 2.4) {
      if (inside(x, y, OUTLINE)) el('circle', { cx: x.toFixed(1), cy: y.toFixed(1), r: 0.55 }, dots);
    }
  }

  const routes = el('g', { class: 'map-routes' }, svg);
  const routePaths = CITIES.map((c) => {
    const mx = (BASE.x + c.x) / 2 + (c.y - BASE.y) * 0.12;
    const my = (BASE.y + c.y) / 2 - (c.x - BASE.x) * 0.12;
    return el('path', { d: `M${BASE.x} ${BASE.y} Q${mx.toFixed(1)} ${my.toFixed(1)} ${c.x} ${c.y}`, pathLength: 1 }, routes);
  });

  const cities = el('g', { class: 'map-cities' }, svg);
  const cityNodes = CITIES.map((c) => {
    const g = el('g', { class: 'map-city', transform: `translate(${c.x} ${c.y})` }, cities);
    el('circle', { r: 1.1 }, g);
    const right = c.x > 80; // etiqueta a la izquierda cerca del borde
    const t = el('text', right ? { x: -2, y: -1.8, 'text-anchor': 'end' } : { x: 2, y: 0.9 }, g);
    t.textContent = c.name;
    return g;
  });

  const base = el('g', { class: 'map-base', transform: `translate(${BASE.x} ${BASE.y})` }, svg);
  el('circle', { r: 4, class: 'map-base__pulse' }, base);
  el('circle', { r: 4, class: 'map-base__pulse map-base__pulse--2' }, base);
  el('circle', { r: 1.9 }, base);
  const bt = el('text', { x: -3, y: -3.2, 'text-anchor': 'end' }, base);
  bt.textContent = 'Base Santa Cruz';

  if (reducedMotion) return;
  gsap.set(routePaths, { strokeDasharray: 1, strokeDashoffset: 1 });
  const tl = gsap.timeline({ scrollTrigger: { trigger: svg, start: 'top 75%' } });
  tl.from(dots.children, { opacity: 0, scale: 0, transformOrigin: 'center', duration: 0.4, stagger: { each: 0.002, from: 'random' } })
    .from(base, { scale: 0, transformOrigin: 'center', duration: 0.6, ease: 'back.out(2)' }, '-=0.3')
    .to(routePaths, { strokeDashoffset: 0, duration: 0.9, stagger: 0.08, ease: 'power2.inOut' }, '-=0.2')
    .from(cityNodes, { opacity: 0, y: 2, duration: 0.4, stagger: 0.08 }, '<0.3');
}
