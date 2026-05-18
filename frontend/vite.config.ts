import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    allowedHosts: ['.trycloudflare.com', '.ngrok-free.app', '.ngrok.io'],
    proxy: {
      '/api/parser': 'http://127.0.0.1:8000',
      '/api/blender': 'http://127.0.0.1:8000',
      '/api/yarn': 'http://127.0.0.1:8000',
      // Yarnseamless routes (Phase 2b ported these to FastAPI). One backend
      // now serves both the wizard and the yarn-processing flow.
      '/api/lama': 'http://127.0.0.1:8000',
      '/api/multithread': 'http://127.0.0.1:8000',
      '/api/multifragment': 'http://127.0.0.1:8000',
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        studio: resolve(__dirname, 'studio.html'),
      },
    },
  },
});
