import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ReactKeycloakProvider } from '@react-keycloak/web'
import { keycloak, initOptions } from './auth/keycloak'
import { setTokenProvider } from './api/client'
import { useSessionStore } from './stores/sessionStore'
import { TickoraApp } from './TickoraApp'
import './index.css'

setTokenProvider(() => keycloak.token)

const onTokens = () => {
  if (!keycloak.tokenParsed) return
  const t = keycloak.tokenParsed as any
  const realmRoles: string[] = t?.realm_access?.roles || []
  const sectors = (t?.groups || [])
    .map((g: string) => {
      const match = g.match(/^\/tickora\/sectors\/([^/]+)\/(members|chiefs)$/)
      if (!match) return null
      return { sectorCode: match[1], role: match[2] === 'chiefs' ? 'chief' : 'member' }
    })
    .filter(Boolean)
  useSessionStore.getState().setUser({
    id:        t.sub,
    username:  t.preferred_username,
    email:     t.email,
    firstName: t.given_name,
    lastName:  t.family_name,
    roles:     realmRoles,
    sectors,
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ReactKeycloakProvider
      authClient={keycloak}
      initOptions={initOptions}
      onTokens={onTokens}
      onEvent={(e) => { if (e === 'onAuthSuccess' || e === 'onAuthRefreshSuccess') onTokens() }}
    >
      <TickoraApp />
    </ReactKeycloakProvider>
  </StrictMode>,
)
