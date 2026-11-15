import { defineConfig } from 'vite';

// base relativa: funciona igual en GitHub Pages (usuario.github.io/repo/),
// en un dominio propio (axiom.tilinka.com) o en un servidor nginx.
export default defineConfig({
  base: './',
  build: {
    target: 'es2020',
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
          gsap: ['gsap'],
        },
      },
    },
  },
});
