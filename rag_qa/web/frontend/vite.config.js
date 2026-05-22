import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath, URL } from 'node:url'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      dts: false,
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
    }),
    Components({
      dts: false,
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
    }),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      includeAssets: ['edurag-icon.svg', 'edurag-maskable.svg'],
      manifest: {
        id: '/',
        name: 'EduRAG 采矿安全智能问答系统',
        short_name: 'EduRAG',
        description: '面向采矿与冶金安全场景的智能问答、知识检索与反馈闭环系统。',
        theme_color: '#0f5bd8',
        background_color: '#f3f6fb',
        display: 'standalone',
        orientation: 'portrait-primary',
        scope: '/',
        start_url: '/',
        lang: 'zh-CN',
        categories: ['education', 'productivity', 'business'],
        shortcuts: [
          {
            name: '智能问答',
            short_name: '问答',
            description: '直接进入智能问答工作台',
            url: '/chat',
            icons: [{ src: '/edurag-icon.svg', sizes: 'any', type: 'image/svg+xml' }],
          },
          {
            name: '系统驾驶舱',
            short_name: '驾驶舱',
            description: '查看系统运行态势和反馈统计',
            url: '/dashboard',
            icons: [{ src: '/edurag-icon.svg', sizes: 'any', type: 'image/svg+xml' }],
          },
        ],
        icons: [
          {
            src: '/edurag-icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any',
          },
          {
            src: '/edurag-maskable.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico}'],
        runtimeCaching: [
          {
            urlPattern: ({ request }) => request.destination === 'document',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'pages-cache',
            },
          },
          {
            urlPattern: ({ request }) => ['style', 'script', 'worker'].includes(request.destination),
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'assets-cache',
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return
          }

          const normalizedId = id.replace(/\\/g, '/')

          if (normalizedId.includes('vue-router')) {
            return 'vue-router'
          }

          if (normalizedId.includes('/@vue/') || normalizedId.includes('node_modules/vue/')) {
            return 'vue-runtime'
          }

          if (normalizedId.includes('@element-plus/icons-vue')) {
            return 'element-plus-icons'
          }

          if (normalizedId.includes('@floating-ui')) {
            return 'floating-ui'
          }

          if (normalizedId.includes('dayjs')) {
            return 'dayjs'
          }

          if (normalizedId.includes('element-plus/es/components/')) {
            const componentName = normalizedId.split('element-plus/es/components/')[1]?.split('/')[0]
            if (componentName) {
              return `el-${componentName}`
            }
          }

          if (normalizedId.includes('element-plus')) {
            return 'element-plus-core'
          }

          if (normalizedId.includes('axios')) {
            return 'network'
          }

          if (normalizedId.includes('marked')) {
            return 'markdown'
          }
        },
      },
    },
  },
})
