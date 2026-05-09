import { create } from 'zustand'

export interface SessionUser {
  id?: string
  username?: string
  email?: string
  firstName?: string
  lastName?: string
  createdAt?: string | null
  roles: string[]
  sectors?: { sectorCode: string; role: 'member' | 'chief' }[]
  hasRootGroup?: boolean
}

interface SessionStore {
  user: SessionUser | null
  setUser: (u: SessionUser | null) => void
  hasRole: (role: string) => boolean
  hasAny: (roles: string[]) => boolean
  isInSector: (sectorCode?: string | null) => boolean
  isChiefOf: (sectorCode?: string | null) => boolean
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  user: null,
  setUser: (u) => set({ user: u }),
  hasRole: (role) => !!get().user?.roles.includes(role),
  hasAny: (roles) => {
    const user = get().user
    if (!user) return false
    return roles.some((r) => user.roles.includes(r))
  },
  isInSector: (sectorCode) => {
    const user = get().user
    if (!user || !sectorCode) return false
    return !!user.sectors?.some((s) => s.sectorCode === sectorCode)
  },
  isChiefOf: (sectorCode) => {
    const user = get().user
    if (!user || !sectorCode) return false
    return !!user.sectors?.some((s) => s.sectorCode === sectorCode && s.role === 'chief')
  },
}))
