import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

const TOKEN_KEY = 'mishil_auth_token';
const ACTIVE_BABY_KEY = 'mishil_active_baby_id';
const OFFLINE_QUEUE_KEY = 'mishil_offline_routines_queue';

export const storage = {
  // Secure JWT Token Operations
  async getToken(): Promise<string | null> {
    if (Platform.OS === 'web') {
      return AsyncStorage.getItem(TOKEN_KEY);
    }
    try {
      return await SecureStore.getItemAsync(TOKEN_KEY);
    } catch {
      return null;
    }
  },

  async setToken(token: string): Promise<void> {
    if (Platform.OS === 'web') {
      await AsyncStorage.setItem(TOKEN_KEY, token);
      return;
    }
    try {
      await SecureStore.setItemAsync(TOKEN_KEY, token);
    } catch {
      await AsyncStorage.setItem(TOKEN_KEY, token);
    }
  },

  async removeToken(): Promise<void> {
    if (Platform.OS === 'web') {
      await AsyncStorage.removeItem(TOKEN_KEY);
      return;
    }
    try {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    } catch {
      await AsyncStorage.removeItem(TOKEN_KEY);
    }
  },

  // Active Baby ID
  async getActiveBabyId(): Promise<number | null> {
    const val = await AsyncStorage.getItem(ACTIVE_BABY_KEY);
    return val ? parseInt(val, 10) : null;
  },

  async setActiveBabyId(id: number): Promise<void> {
    await AsyncStorage.setItem(ACTIVE_BABY_KEY, id.toString());
  },

  // Offline Queue
  async getOfflineQueue<T>(): Promise<T[]> {
    try {
      const data = await AsyncStorage.getItem(OFFLINE_QUEUE_KEY);
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  },

  async setOfflineQueue<T>(queue: T[]): Promise<void> {
    await AsyncStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue));
  },
};
