import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SoundStore {
  soundEnabled: boolean
  toggleSound: () => void
}

export const useSoundStore = create<SoundStore>()(
  persist(
    (set, get) => ({
      soundEnabled: true,
      toggleSound: () => set({ soundEnabled: !get().soundEnabled }),
    }),
    { name: 'tickora-sound' },
  ),
)
