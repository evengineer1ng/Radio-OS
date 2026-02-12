import { vitePreprocess } from '@sveltejs/vite-plugin-svelte'

export default {
  preprocess: vitePreprocess(),
  compilerOptions: {
    // Enable legacy mode so $: and export let still work (Svelte 4 compat)
    compatibility: {
      componentApi: 4,
    },
  },
}
