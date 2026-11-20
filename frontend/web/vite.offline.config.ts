import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  base: '/',
  publicDir: false,
  build: {
    outDir: 'dist-offline',
    emptyOutDir: true,
    rollupOptions: { input: resolve(__dirname, 'offline.html') },
  },
});
