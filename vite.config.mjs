import {defineConfig} from 'vite';

export default defineConfig({
  base:'./',
  // Evita carregar a configuracao PostCSS global do perfil do Windows.
  css:{postcss:{plugins:[]}}
});
