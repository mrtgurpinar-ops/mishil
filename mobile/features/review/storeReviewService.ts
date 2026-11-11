import AsyncStorage from '@react-native-async-storage/async-storage';
import * as StoreReview from 'expo-store-review';

export const NATIVE_REVIEW_STORAGE_KEY = '@mishil_native_review_last_ts';
// Apple SKStoreReviewController yıllık 3 gösterim kotasını ve Google Play kotalarını korumak için 45 gün kilit
export const NATIVE_REVIEW_COOLDOWN_MS = 45 * 24 * 60 * 60 * 1000;

export type NativeReviewResultReason =
  | 'ok'
  | 'in_flight'
  | 'cooldown'
  | 'unavailable'
  | 'error';

export interface NativeReviewResult {
  triggered: boolean;
  reason: NativeReviewResultReason;
  timestamp?: number;
}

let inFlight = false;

export function isWithinReviewCooldown(
  lastTsRaw: string | number | null | undefined,
  nowMs: number = Date.now()
): boolean {
  if (lastTsRaw === null || lastTsRaw === undefined || lastTsRaw === '') {
    return false;
  }
  const parsed = typeof lastTsRaw === 'number' ? lastTsRaw : parseInt(String(lastTsRaw), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return false;
  }
  // Saat geri alma durumunda negatif fark oluşursa geleceğe ait aşırı sapma değilse koru
  if (nowMs < parsed) {
    return (parsed - nowMs) <= 24 * 60 * 60 * 1000;
  }
  return (nowMs - parsed) < NATIVE_REVIEW_COOLDOWN_MS;
}

/**
 * Resmi uygulama içi sistem değerlendirme penceresini (iOS SKStoreReviewController /
 * Android Play In-App Review) güvenli bir şekilde tetikler.
 *
 * Önemli Güvenlik Kuralı:
 * Yalnızca `StoreReview.isAvailableAsync() === true` iken `requestReview()` çağrılır.
 * Böylece native modülün bulunmadığı ortamlarda `expo-store-review` paketinin
 * mağaza URL'sine yönlendirerek ebeveyni uygulamadan dışarı atması (Linking.openURL fallback)
 * kesin olarak engellenir; çalan ninni veya canlı uyku sayacı asla bölünmez.
 */
export async function triggerNativeStoreReview(options?: {
  nowMs?: number;
  bypassCooldown?: boolean;
}): Promise<NativeReviewResult> {
  if (inFlight) {
    return { triggered: false, reason: 'in_flight' };
  }

  inFlight = true;
  const nowMs = typeof options?.nowMs === 'number' && Number.isFinite(options.nowMs)
    ? options.nowMs
    : Date.now();

  try {
    if (!options?.bypassCooldown) {
      let savedTs: string | null = null;
      try {
        savedTs = await AsyncStorage.getItem(NATIVE_REVIEW_STORAGE_KEY);
      } catch {
        savedTs = null;
      }

      if (isWithinReviewCooldown(savedTs, nowMs)) {
        return {
          triggered: false,
          reason: 'cooldown',
          timestamp: savedTs ? parseInt(savedTs, 10) : undefined,
        };
      }
    }

    if (!StoreReview || typeof StoreReview.isAvailableAsync !== 'function' || typeof StoreReview.requestReview !== 'function') {
      return { triggered: false, reason: 'unavailable' };
    }

    const available = await StoreReview.isAvailableAsync();
    if (!available) {
      return { triggered: false, reason: 'unavailable' };
    }

    await StoreReview.requestReview();

    try {
      await AsyncStorage.setItem(NATIVE_REVIEW_STORAGE_KEY, String(nowMs));
    } catch {
      // Depolama hatası sessiz geçilir
    }

    return {
      triggered: true,
      reason: 'ok',
      timestamp: nowMs,
    };
  } catch {
    return { triggered: false, reason: 'error' };
  } finally {
    inFlight = false;
  }
}
