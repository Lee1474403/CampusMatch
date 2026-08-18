import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/', redirect: '/discover' },
  { path: '/auth', name: 'auth', component: () => import('../views/AuthView.vue'), meta: { guest: true } },
  { path: '/verify-email', name: 'verify-email', component: () => import('../views/VerifyEmailView.vue') },
  { path: '/discover', name: 'discover', component: () => import('../views/DiscoverView.vue'), meta: { auth: true } },
  { path: '/questionnaire', name: 'questionnaire', component: () => import('../views/QuestionnaireView.vue'), meta: { auth: true } },
  { path: '/chat/:matchId?', name: 'chat', component: () => import('../views/ChatView.vue'), meta: { auth: true } },
  { path: '/profile', name: 'profile', component: () => import('../views/ProfileView.vue'), meta: { auth: true } },
  { path: '/:pathMatch(.*)*', redirect: '/discover' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.restoreSession()
  if (to.meta.auth && !auth.isAuthenticated) return { name: 'auth', query: { next: to.fullPath } }
  if (to.meta.guest && auth.isAuthenticated) return { name: 'discover' }
  return true
})

export default router
