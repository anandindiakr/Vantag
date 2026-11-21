import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import { readFileSync } from 'node:fs';

export default defineConfig({
  plugins: [react(), {
    name: 'bundle-offline-manual',
    generateBundle() {
      for (const extension of ['pdf', 'html']) {
        const name = `vantag-offline-demo-team-manual.${extension}`;
        this.emitFile({ type: 'asset', fileName: `assets/${name}`, source: readFileSync(resolve(__dirname, 'public/handouts', name)) });
      }
    },
  }],
  base: '/',
  publicDir: false,
  build: {
    outDir: 'dist-offline',
    emptyOutDir: true,
    rollupOptions: { input: resolve(__dirname, 'offline.html') },
  },
});
