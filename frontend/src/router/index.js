import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '数据看板', subtitle: '实时掌握采集、打分与下载全链路状态', icon: 'DataLine' }
      },
      {
        path: 'sources',
        name: 'sources',
        component: () => import('../views/Sources.vue'),
        meta: { title: '数据源与打分预览', subtitle: '勾选调度歌单，透明查看每首歌曲的得分构成', icon: 'Files' }
      },
      {
        path: 'rules',
        name: 'rules',
        component: () => import('../views/Rules.vue'),
        meta: { title: '动态规则配置', subtitle: '调整平台权重、交叉乘数与加减分规则，即时重算', icon: 'Operation' }
      },
      {
        path: 'manual',
        name: 'manual',
        component: () => import('../views/Manual.vue'),
        meta: { title: '手动搜索直下', subtitle: '跳过打分与去重限制，优先消耗上游配额', icon: 'Search' }
      },
      {
        path: 'queue',
        name: 'queue',
        component: () => import('../views/Queue.vue'),
        meta: { title: '下载与后处理队列', subtitle: '实时跟踪排队、限流、下载与归档任务', icon: 'Tickets' }
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('../views/Settings.vue'),
        meta: { title: '系统设置', subtitle: '网络、限流、Navidrome、目录与通知配置', icon: 'Setting' }
      }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const token = localStorage.getItem('mf_token')
  if (!to.meta.public && !token) return '/login'
  if (to.path === '/login' && token) return '/dashboard'
  return true
})

export default router
