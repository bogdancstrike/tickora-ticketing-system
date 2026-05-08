import Keycloak from 'keycloak-js'

const env = (import.meta as any).env || {}

export const keycloak = new Keycloak({
  url:      env.VITE_KEYCLOAK_URL      || 'http://localhost:8080',
  realm:    env.VITE_KEYCLOAK_REALM    || 'tickora',
  clientId: env.VITE_KEYCLOAK_CLIENT   || 'tickora-spa',
})

export const initOptions = {
  onLoad: 'login-required' as const,
  pkceMethod: 'S256' as const,
  checkLoginIframe: false,
}
