# Axiom Energy SRL — Landing page

Landing de una sola página para **Axiom Energy SRL** (combustibles y energía, Santa Cruz, Bolivia).
Estilo inspirado en tilinka.com: escena isométrica 3D con **Three.js**, animaciones con **GSAP + ScrollTrigger**
y scroll suave con **Lenis**. Construida con **Vite** (sin framework).

## Desarrollo

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # genera dist/
npm run preview  # sirve dist/
```

## Estructura

| Archivo | Contenido |
| --- | --- |
| `index.html` | Todas las secciones y textos |
| `src/heroScene.js` | Escena 3D: estación de servicio, tanques, torre, paneles solares, camiones cisterna, ductos con flujo, etiquetas |
| `src/main.js` | GSAP (intro, reveals, contadores, ruta del proceso, tilt), tema claro/oscuro, formulario → WhatsApp. **`CONFIG`** con los datos de contacto |
| `src/coverageMap.js` | Mapa estilizado de cobertura en Santa Cruz |
| `src/style.css` | Estilos y tokens de color (marca: navy `#17384a`, lima `#b5c425`, dorado `#c9a15a`) |

## Pendiente de confirmar con el cliente

- Número de WhatsApp y correo en `CONFIG` (`src/main.js`).
- Cifras de la franja de estadísticas (24/7, +15 municipios, 100 % GPS, <4 h) — son de ejemplo.
- Lista exacta de productos/servicios y localidades de cobertura.
- Logo vectorial original (el del sitio es una recreación en SVG del logo entregado en `public/logo-axiom.webp`).

## Deploy con GitHub Actions

Hay dos workflows; se elige con la variable de repositorio `DEPLOY_TARGET`:

1. **GitHub Pages** (`deploy-pages.yml`, por defecto)
   - Settings → Pages → Source: **GitHub Actions**.
   - Cada push a `main` compila y publica.
   - Dominio propio: crea `public/CNAME` con el dominio (ej. `axiom.tilinka.com`) y apunta un CNAME DNS a `<usuario>.github.io`.

2. **Servidor propio por SSH** (`deploy-vps.yml`)
   - Variable `DEPLOY_TARGET=vps` y secrets `SSH_HOST`, `SSH_USER`, `SSH_KEY`, `SSH_PATH` (y opcional `SSH_PORT`).
   - Hace `rsync --delete` de `dist/` a la carpeta que sirve nginx.

Ambos se pueden lanzar también a mano desde la pestaña **Actions** (`workflow_dispatch`).
