import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import './risk.css'
import './entry.css'
import './workspace.css'
import './editorial.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/', component: App }],
})

createApp(App).use(router).mount('#app')
