import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 120000 })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('mf_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('mf_token')
      localStorage.removeItem('mf_user')
      if (location.pathname !== '/login') location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
