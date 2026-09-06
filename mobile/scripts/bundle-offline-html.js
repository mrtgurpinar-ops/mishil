/**
 * public/app.html'i binary'e gömülebilir bir TS string modülüne çevirir.
 *
 * Amaç: uygulama %100 uzak URL'e bağımlı. Railway/DNS/CDN geçici sorununda
 * (özellikle uygulama ilk açılışında) kullanıcı boş ekran yerine gömülü
 * çevrimdışı sürümü görsün; arka planda uzak sürüme yeniden bağlanılır.
 *
 * EAS build yalnızca `mobile/` dizinini yükler; `../public/app.html` orada
 * bulunmaz. Bu yüzden:
 *   - Yerelde / CI'da bu script çalışır ve `offlineHtml.generated.ts` üretir.
 *   - Üretilen dosya repoya COMMIT EDİLİR.
 *   - EAS'te kaynak yoksa script uyarı verip mevcut (commit'li) dosyayı korur.
 *
 * Elle çalıştırma:  node scripts/bundle-offline-html.js
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', '..', 'public', 'app.html');
const OUT = path.join(__dirname, '..', 'features', 'webview', 'offlineHtml.generated.ts');

function main() {
  if (!fs.existsSync(SRC)) {
    console.warn(
      '[bundle-offline-html] Kaynak bulunamadı (' + SRC + '). ' +
      'Muhtemelen EAS build ortamı — mevcut commit\'li offlineHtml.generated.ts korunuyor.'
    );
    if (!fs.existsSync(OUT)) {
      // Build'i kırma; en azından boş bir modül bırak.
      fs.mkdirSync(path.dirname(OUT), { recursive: true });
      fs.writeFileSync(
        OUT,
        '// AUTO-GENERATED fallback (kaynak yoktu)\nexport const OFFLINE_HTML = "";\nexport const OFFLINE_HTML_BUILT_AT = "";\n',
        'utf8'
      );
      console.warn('[bundle-offline-html] Boş modül yazıldı.');
    }
    return;
  }

  const html = fs.readFileSync(SRC, 'utf8');
  const builtAt = new Date().toISOString();
  const body =
    '// AUTO-GENERATED — düzenlemeyin. Yenile: node scripts/bundle-offline-html.js\n' +
    '// Kaynak: projects/mishil/public/app.html\n' +
    '/* eslint-disable */\n' +
    'export const OFFLINE_HTML = ' + JSON.stringify(html) + ';\n' +
    'export const OFFLINE_HTML_BUILT_AT = ' + JSON.stringify(builtAt) + ';\n';

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, body, 'utf8');
  console.log(
    '[bundle-offline-html] Yazıldı: ' + path.relative(path.join(__dirname, '..'), OUT) +
    ' (' + (html.length / 1024).toFixed(0) + ' KB, ' + builtAt + ')'
  );
}

main();
