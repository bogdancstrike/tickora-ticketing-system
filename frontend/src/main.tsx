import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ReactKeycloakProvider } from '@react-keycloak/web'
import { keycloak, initOptions } from './auth/keycloak'
import { setTokenProvider } from './api/client'
import { useSessionStore } from './stores/sessionStore'
import { TickoraApp } from './TickoraApp'
import './index.css'

setTokenProvider(() => keycloak.token)

const FULL_ACCESS_ROLES = [
  'tickora_admin',
]

function normalizeSectorCode(code: string) {
  const value = (code || '').trim().toLowerCase()
  return /^sector\d+$/.test(value) ? `s${value.slice('sector'.length)}` : value
}

function tokenSectors(groups: string[]) {
  const out = new Map<string, Set<'member' | 'chief'>>()
  const add = (code: string, role: 'member' | 'chief') => {
    const sectorCode = normalizeSectorCode(code)
    if (!sectorCode) return
    const roles = out.get(sectorCode) || new Set<'member' | 'chief'>()
    roles.add(role)
    out.set(sectorCode, roles)
  }

  groups.forEach((raw) => {
    const group = (raw || '').trim()
    const sectorPath = group.match(/^\/tickora\/sectors\/([^/]+)(?:\/(members|member|chiefs|chief))?$/)
    const legacyPath = group.match(/^\/tickora\/([^/]+)(?:\/(members|member|chiefs|chief))?$/)
    const shorthand = group.match(/^sector\d+$/i)
    const match = sectorPath || legacyPath

    if (match && match[1] !== 'sectors') {
      const role = match[2]
      if (!role) {
        add(match[1], 'chief')
        add(match[1], 'member')
      } else {
        add(match[1], role.startsWith('chief') ? 'chief' : 'member')
      }
    } else if (shorthand) {
      add(group, 'chief')
      add(group, 'member')
    }
  })

  return Array.from(out.entries()).flatMap(([sectorCode, roles]) =>
    Array.from(roles).map((role) => ({ sectorCode, role })),
  )
}

const onTokens = () => {
  if (!keycloak.tokenParsed) return
  const t = keycloak.tokenParsed as any
  const groups: string[] = t?.groups || []
  const previous = useSessionStore.getState().user
  const roles = new Set<string>(t?.realm_access?.roles || [])
  if (groups.some((g) => g === '/tickora' || g === 'tickora')) {
    FULL_ACCESS_ROLES.forEach((role) => roles.add(role))
  }
  const sectors = tokenSectors(groups)
  useSessionStore.getState().setUser({
    id:        t.sub,
    username:  t.preferred_username,
    email:     t.email,
    firstName: t.given_name,
    lastName:  t.family_name,
    roles:     Array.from(roles),
    sectors:   sectors.length ? sectors : previous?.sectors,
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
