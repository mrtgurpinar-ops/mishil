/**
 * Expo Router System Deep Link Interceptor (+native-intent)
 *
 * Mışıl Baby tekil WebView mimarisiyle (app/index.tsx -> MishilUnifiedWebView) çalışır.
 * iOS Live Activity (.widgetURL("misilbaby://sleep")) ve Android canlı uyku bildirimi
 * ("misilbaby://sleep") tıklandığında Expo Router'ın "Unmatched Route" hatasına düşmesini
 * veya ikinci bir WebView ekranı açmasını önlemek için tüm özel şema / alt rotalar
 * ana ekrana ('/') normalize edilir; odaklama MishilUnifiedWebView içindeki Linking
 * dinleyicisi tarafından WebView yeniden yüklenmeden yapılır.
 */

export function isSleepDeepLink(urlOrPath?: string | null): boolean {
  if (!urlOrPath || typeof urlOrPath !== 'string') return false;
  const trimmed = urlOrPath.trim();
  if (!trimmed) return false;

  const withoutQuery = trimmed.split('#')[0].split('?')[0].replace(/\/+$/, '');
  const lower = withoutQuery.toLowerCase();

  if (
    lower === 'sleep' ||
    lower === '/sleep' ||
    lower === 'misilbaby://sleep' ||
    lower === 'misilbaby:///sleep'
  ) {
    return true;
  }

  const schemeMatch = lower.match(/^[a-z][a-z0-9+.-]*:\/\/(.*)$/);
  if (schemeMatch) {
    const remainder = schemeMatch[1].replace(/^\/+/, '');
    if (remainder === 'sleep' || remainder.startsWith('sleep/')) {
      return true;
    }
  }

  return false;
}

export function redirectSystemPath({
  path,
}: {
  path: string;
  initial: boolean;
}): string {
  try {
    if (!path || typeof path !== 'string') {
      return '/';
    }
    const clean = path.trim();
    if (!clean || clean === '/') {
      return '/';
    }
    // Tekil WebView mimarisinde tüm misilbaby://... ve alt yollar '/' rotasında karşılanır
    return '/';
  } catch {
    return '/';
  }
}
