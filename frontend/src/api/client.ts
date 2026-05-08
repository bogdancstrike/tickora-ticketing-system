import axios from 'axios'

const normalizeBaseUrl = (value?: string): string => {
  const raw = (value || '/tickora').trim()
  const withoutTrailingSlash = raw.replace(/\/+$/, '')
  return withoutTrailingSlash.startsWith('/') || /^https?:\/\//i.test(withoutTrailingSlash)
    ? withoutTrailingSlash
    : `/${withoutTrailingSlash}`
}

const BASE_URL = normalizeBaseUrl((import.meta as any).env?.VITE_API_BASE_URL)

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

let tokenProvider: () => string | undefined = () => undefined

export const setTokenProvider = (fn: () => string | undefined): void => {
  tokenProvider = fn
}

/** Returns the current access token (for SSE / WS where headers can't be set). */
export const getToken = (): string | undefined => tokenProvider()

apiClient.interceptors.request.use((cfg) => {
  const token = tokenProvider()
  if (token) {
    cfg.headers = cfg.headers || {}
    ;(cfg.headers as any).Authorization = `Bearer ${token}`
  }
  return cfg
})

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    const data = err.response?.data
    const msg = data?.message || data?.error || err.message || 'Request failed'
    return Promise.reject(new Error(msg))
  },
)

export const API_BASE = BASE_URL
