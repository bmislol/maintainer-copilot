import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'react': 'preact/compat',
      'react-dom/test-utils': 'preact/test-utils',
      'react-dom': 'preact/compat',
      'react/jsx-runtime': 'preact/jsx-runtime',
    },
  },
  build: {
    lib: {
      entry: 'src/main.jsx',
      name: 'MaintainerCopilotWidget',
      formats: ['iife'],
      fileName: () => 'widget.js',
    },
    outDir: '../backend/app/static',
    emptyOutDir: false,   // don't wipe the static dir between builds
    rollupOptions: {
      output: {
        inlineDynamicImports: true,  // single file, no code-splitting
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.js'],
  },
})
