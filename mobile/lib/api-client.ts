import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import Constants from 'expo-constants';
import { storage } from './storage';

const API_BASE_URL =
  Constants.expoConfig?.extra?.apiUrl ||
  process.env.EXPO_PUBLIC_API_URL ||
  'http://localhost:8000/api/v1';

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// Request Interceptor: Attach Bearer JWT
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = await storage.getToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Format error messages calmly and clearly
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ message?: string; details?: Array<{ field: string; issue: string }> }>) => {
    let cleanMessage = 'Sunucuyla bağlantı kurulurken bir sorun oluştu.';
    if (error.response?.data?.message) {
      cleanMessage = error.response.data.message;
    } else if (error.message === 'Network Error') {
      cleanMessage = 'İnternet bağlantısı algılanamadı. İşleminiz çevrimdışı kuyruğa alındı.';
    }
    
    // Attach user friendly message to error object
    const enhancedError = new Error(cleanMessage);
    (enhancedError as any).status = error.response?.status;
    (enhancedError as any).raw = error;
    return Promise.reject(enhancedError);
  }
);
