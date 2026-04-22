import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    proxy: {
      '/api/parser': 'http://127.0.0.1:8000',
      '/api/blender': 'http://127.0.0.1:8000',
      '/api/yarn': 'http://127.0.0.1:8000',
    },
  },
});
