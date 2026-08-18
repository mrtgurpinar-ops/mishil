import { create } from 'zustand';
import { storage } from '../lib/storage';

export interface Baby {
  id: number;
  user_id: number;
  name: string;
  birth_date: string;
  age_in_months: number;
  created_at: string;
}

export interface User {
  id: number;
  email: string;
  full_name?: string;
  subscription_status: string;
}

export interface OfflineRoutineItem {
  id: string;
  baby_id: number;
  routine_type: string;
  start_time: string;
  end_time?: string;
  details: Record<string, any>;
  notes?: string;
}

interface AppState {
  // Theme
  isDarkMode: boolean;
  useSystemTheme: boolean;
  toggleTheme: () => void;
  setUseSystemTheme: (val: boolean) => void;
  setIsDarkMode: (val: boolean) => void;

  // Auth & User
  user: User | null;
  isAuthenticated: boolean;
  setAuth: (user: User, token: string) => Promise<void>;
  logout: () => Promise<void>;

  // Babies
  activeBaby: Baby | null;
  babies: Baby[];
  setActiveBaby: (baby: Baby) => Promise<void>;
  setBabies: (babies: Baby[]) => void;

  // Offline Queue
  offlineQueue: OfflineRoutineItem[];
  addToOfflineQueue: (item: OfflineRoutineItem) => Promise<void>;
  removeFromOfflineQueue: (id: string) => Promise<void>;
  clearOfflineQueue: () => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => ({
  isDarkMode: true,
  useSystemTheme: true,
  toggleTheme: () => set((state) => ({ isDarkMode: !state.isDarkMode, useSystemTheme: false })),
  setUseSystemTheme: (val) => set({ useSystemTheme: val }),
  setIsDarkMode: (val) => set({ isDarkMode: val }),

  user: null,
  isAuthenticated: false,
  setAuth: async (user, token) => {
    await storage.setToken(token);
    set({ user, isAuthenticated: true });
  },
  logout: async () => {
    await storage.removeToken();
    set({ user: null, isAuthenticated: false, activeBaby: null, babies: [] });
  },

  activeBaby: null,
  babies: [],
  setActiveBaby: async (baby) => {
    await storage.setActiveBabyId(baby.id);
    set({ activeBaby: baby });
  },
  setBabies: (babies) => {
    set({ babies });
    if (babies.length > 0 && !get().activeBaby) {
      set({ activeBaby: babies[0] });
    }
  },

  offlineQueue: [],
  addToOfflineQueue: async (item) => {
    const updated = [...get().offlineQueue, item];
    set({ offlineQueue: updated });
    await storage.setOfflineQueue(updated);
  },
  removeFromOfflineQueue: async (id) => {
    const updated = get().offlineQueue.filter((i) => i.id !== id);
    set({ offlineQueue: updated });
    await storage.setOfflineQueue(updated);
  },
  clearOfflineQueue: async () => {
    set({ offlineQueue: [] });
    await storage.setOfflineQueue([]);
  },
}));
