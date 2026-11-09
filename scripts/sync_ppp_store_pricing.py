#!/usr/bin/env python3
"""
Mışıl Baby — Satın Alma Gücü Paritesi (PPP) & Rakip Altı Küresel Abonelik Fiyatlandırma Motoru.
(3 Ajanlı Konsensüs Denetimli: Claude Code CLI task-165 + Codex CLI gpt-6-luna task-175 + Antigravity)

Kapsam:
1. Apple App Store Connect API v1 (`misil_monthly` #6809228860, `misil_annual` #6809228257):
   - Türkiye (`TUR`: 149.99 TRY / 599.99 TRY) ve İsviçre (`CHE`: 5.00 CHF / 25.00 CHF) aynen korunur.
   - Hedef ülkelerde (`UZB, AZE, KAZ, POL, ROU, IND, BRA, MEX, DEU, FRA, NLD, AUT, BEL, ESP, ITA, GBR, USA, CAN, AUS, ARE, SAU` vb.)
     tüm küresel rakiplerin (Huckleberry, Napper, Baby Daybook) altında kalan PPP fiyat noktaları (`subscriptionPricePoints`)
     çözümlenir ve `preserveCurrentPrice: False` ile (409 durumunda ertesi gün UTC `startDate` fallback'i ve POST sonrası canlı GET doğrulamasıyla) uygulanır.
2. Google Play Developer API v3 (`misilaylik` Aylık, `misil` Yıllık + `freeytrial` / `3daystrial` P7D 7G Deneme Teklifleri):
   - Yalnızca 2 bölgede (`TR`, `FR`) açık olan planları 174 ülkenin tamamında PPP fiyatlarıyla satışa açar.
   - 7 günlük ücretsiz deneme tekliflerini (`freeytrial`, `3daystrial` — her ikisi de `duration: P7D`) hem teklif hem de `phases[0]` düzeyinde 174 ülkenin tamamında aktif hale getirir.

Kullanım:
  python projects/mishil/scripts/sync_ppp_store_pricing.py --dry-run
  python projects/mishil/scripts/sync_ppp_store_pricing.py --apply
"""

import argparse
from datetime import datetime, timedelta, timezone
import glob
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

try:
    import jwt
except ImportError:
    from jose import jwt  # type: ignore

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PACKAGE_NAME = "com.levitas.misilbaby"
APPLE_APP_ID = "6809223195"
APPLE_MONTHLY_SUB_ID = "6809228860"  # misil_monthly
APPLE_ANNUAL_SUB_ID = "6809228257"   # misil_annual
DEFAULT_ASC_ISSUER_ID = "7d2413c6-ea40-4bd9-9334-8313a514b0e6"
APPLE_ISSUER_ID = os.environ.get("ASC_ISSUER_ID") or DEFAULT_ASC_ISSUER_ID

# ISO-2 -> ISO-3 Ülke Eşlemesi (Apple App Store Connect Territory ID)
ISO2_TO_ISO3: Dict[str, str] = {
    "TR": "TUR",
    "CH": "CHE",
    "UZ": "UZB",
    "AZ": "AZE",
    "KZ": "KAZ",
    "PL": "POL",
    "RO": "ROU",
    "IN": "IND",
    "BR": "BRA",
    "MX": "MEX",
    "DE": "DEU",
    "FR": "FRA",
    "NL": "NLD",
    "AT": "AUT",
    "BE": "BEL",
    "ES": "ESP",
    "IT": "ITA",
    "PT": "PRT",
    "GR": "GRC",
    "IE": "IRL",
    "FI": "FIN",
    "GB": "GBR",
    "US": "USA",
    "CA": "CAN",
    "AU": "AUS",
    "AE": "ARE",
    "SA": "SAU",
    "BG": "BGR",
    "HU": "HUN",
    "CZ": "CZE",
    "UA": "UKR",
    "GE": "GEO",
    "ID": "IDN",
    "PK": "PAK",
    "PH": "PHL",
    "EG": "EGY",
    "CO": "COL",
}

# ============================================================================
# 1. APPLE APP STORE CONNECT HEDEF PPP MATRİSİ (Aylık, Yıllık, Beklenen Para Birimi)
# Not: TR (149.99 / 599.99 TRY) ve CH (5.00 / 25.00 CHF) KORUNUR (PROTECTED_COUNTRIES).
# ============================================================================
PROTECTED_COUNTRIES = ("TR", "CH")

APPLE_PPP_TARGETS: Dict[str, Tuple[float, float, str]] = {
    # Kuşak 1: Korunan Ülkeler (Değiştirilmez)
    "TR": (149.99, 599.99, "TRY"),
    "CH": (5.00, 25.00, "CHF"),
    # Kuşak 2: Türk Cumhuriyetleri & Doğu Pazarları (En ucuz rakip Baby Daybook $2.99 / $13.99–$19.99 altında)
    "UZ": (2.49, 11.99, "USD"),
    "AZ": (2.49, 12.99, "USD"),
    "KZ": (1290.0, 5990.0, "KZT"),
    # Kuşak 3: Hacim Pazarları (Güney Asya & LatAm - Napper & Baby Daybook altında)
    "IN": (149.0, 699.0, "INR"),
    "BR": (14.90, 59.90, "BRL"),
    "MX": (49.0, 249.0, "MXN"),
    # Kuşak 4: Doğu & Orta Avrupa (Napper & Baby Daybook 14.99 / 99.99 PLN-RON altında)
    "PL": (14.99, 69.99, "PLN"),
    "RO": (14.99, 69.99, "RON"),
    # Kuşak 5: Batı Avrupa, İngiltere, Kuzey Amerika & Körfez (Tüm rakiplerin altında)
    "DE": (4.99, 29.99, "EUR"),
    "FR": (4.99, 29.99, "EUR"),
    "NL": (4.99, 29.99, "EUR"),
    "AT": (4.99, 29.99, "EUR"),
    "BE": (4.99, 29.99, "EUR"),
    "ES": (4.99, 29.99, "EUR"),
    "IT": (4.99, 29.99, "EUR"),
    "PT": (4.99, 24.99, "EUR"),
    "GR": (4.99, 24.99, "EUR"),
    "IE": (4.99, 29.99, "EUR"),
    "GB": (4.99, 24.99, "GBP"),
    "US": (4.99, 24.99, "USD"),
    "CA": (6.99, 34.99, "CAD"),
    "AU": (7.99, 39.99, "AUD"),
    "AE": (17.99, 89.99, "AED"),
    "SA": (19.99, 99.99, "SAR"),
}

# ============================================================================
# 2. GOOGLE PLAY CONSOLE HEDEF PPP MATRİSİ (37 Anahtar Ülke - Yerel Para Birimi Duyarlı)
# Google Play'de AZ -> AZN, UZ -> UZS, BG -> EUR kullanır.
# ============================================================================
GOOGLE_PLAY_EXPLICIT_TARGETS: Dict[str, Tuple[float, float, str]] = {
    "TR": (149.99, 599.99, "TRY"),
    "CH": (5.00, 25.00, "CHF"),
    "UZ": (31900.00, 149000.00, "UZS"),  # ~$2.49 / ~$11.60
    "AZ": (4.29, 21.99, "AZN"),          # ~$2.52 / ~$12.90
    "KZ": (1290.00, 5990.00, "KZT"),
    "IN": (149.00, 699.00, "INR"),
    "BR": (14.90, 59.90, "BRL"),
    "MX": (49.00, 249.00, "MXN"),
    "PL": (14.99, 69.99, "PLN"),
    "RO": (14.99, 69.99, "RON"),
    "DE": (4.99, 29.99, "EUR"),
    "FR": (4.99, 29.99, "EUR"),
    "NL": (4.99, 29.99, "EUR"),
    "AT": (4.99, 29.99, "EUR"),
    "BE": (4.99, 29.99, "EUR"),
    "ES": (4.99, 29.99, "EUR"),
    "IT": (4.99, 29.99, "EUR"),
    "PT": (4.99, 24.99, "EUR"),
    "GR": (4.99, 24.99, "EUR"),
    "IE": (4.99, 29.99, "EUR"),
    "FI": (4.99, 29.99, "EUR"),
    "GB": (4.99, 24.99, "GBP"),
    "US": (4.99, 24.99, "USD"),
    "CA": (6.99, 34.99, "CAD"),
    "AU": (7.99, 39.99, "AUD"),
    "AE": (17.99, 89.99, "AED"),
    "SA": (19.99, 99.99, "SAR"),
    "BG": (3.49, 16.99, "EUR"),          # Google Play BG için EUR kullanır
    "HU": (1490.00, 6990.00, "HUF"),
    "CZ": (89.00, 449.00, "CZK"),
    "UA": (99.00, 499.00, "UAH"),
    "GE": (6.99, 34.99, "GEL"),
    "ID": (29000.00, 149000.00, "IDR"),
    "PK": (590.00, 2900.00, "PKR"),
    "PH": (119.00, 599.00, "PHP"),
    "EG": (99.00, 499.00, "EGP"),
    "CO": (8900.00, 44900.00, "COP"),
}


def assert_tr_ch_invariants() -> None:
    """Türkiye ve İsviçre fiyatlarının değişmediğini garanti altına alan emniyet kilidi."""
    assert APPLE_PPP_TARGETS["TR"] == (149.99, 599.99, "TRY"), "TR Apple invariant ihlali!"
    assert GOOGLE_PLAY_EXPLICIT_TARGETS["TR"] == (149.99, 599.99, "TRY"), "TR Google Play invariant ihlali!"
    assert APPLE_PPP_TARGETS["CH"] == (5.00, 25.00, "CHF"), "CH Apple invariant ihlali!"
    assert GOOGLE_PLAY_EXPLICIT_TARGETS["CH"] == (5.00, 25.00, "CHF"), "CH Google Play invariant ihlali!"


def float_to_gp_price(amount: float, currency_code: str) -> Dict[str, Any]:
    """Ondalık fiyatı Google Play Money nesnesine ({currencyCode, units, nanos}) dönüştürür."""
    rounded = round(float(amount), 2)
    units_int = int(math.floor(rounded + 1e-9))
    frac = round(rounded - units_int, 2)
    nanos_int = int(round(frac * 1_000_000_000))
    return {
        "currencyCode": currency_code,
        "units": str(units_int),
        "nanos": nanos_int,
    }


def gp_price_to_float(price_obj: Dict[str, Any]) -> Tuple[float, str]:
    units_v = float(price_obj.get("units") or 0)
    nanos_v = float(price_obj.get("nanos") or 0) / 1e9
    return round(units_v + nanos_v, 2), str(price_obj.get("currencyCode") or "")


def get_google_play_token() -> str:
    gp_path = os.path.join(PROJECT_ROOT, "mobile", "google-play-service-account.json")
    if not os.path.exists(gp_path):
        raise FileNotFoundError(f"Google Play service account bulunamadı: {gp_path}")
    with open(gp_path, "r", encoding="utf-8") as f:
        sa = json.load(f)
    now = int(time.time())
    gp_jwt = jwt.encode(
        {
            "iss": sa["client_email"],
            "scope": "https://www.googleapis.com/auth/androidpublisher",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now - 30,
            "exp": now + 3500,
        },
        sa["private_key"],
        algorithm="RS256",
    )
    tok_data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": gp_jwt,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=tok_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def get_apple_token() -> str:
    p8_files = glob.glob(os.path.join(PROJECT_ROOT, "mobile", "AuthKey_*.p8"))
    if not p8_files:
        raise FileNotFoundError("Apple AuthKey_*.p8 bulunamadı.")
    p8_path = p8_files[0]
    bn = os.path.basename(p8_path)
    key_id = bn[len("AuthKey_"):-len(".p8")]
    with open(p8_path, "r", encoding="utf-8") as f:
        priv_key = f.read()
    now = int(time.time())
    return jwt.encode(
        {"iss": APPLE_ISSUER_ID, "iat": now - 30, "exp": now + 900, "aud": "appstoreconnect-v1"},
        priv_key,
        algorithm="ES256",
        headers={"kid": key_id, "typ": "JWT"},
    )


def build_google_play_174_configs(
    template_174_configs: List[Dict[str, Any]],
    is_annual: bool,
) -> List[Dict[str, Any]]:
    """
    Google Play'in 174 bölgesinin tamamı için:
    - GOOGLE_PLAY_EXPLICIT_TARGETS içinde yer alan ülkelerde birebir rakip altı PPP fiyatını (ve şablondaki yasal para birimini) kullanır.
    - Geri kalan ülkelerde şablondaki (`misilyillik` bazlı) yerel para birimini koruyarak
      Aylık planda yıllık referansın ~1/5'ine (örn. USD 2.99 / EUR 2.99), Yıllık planda PPP bandına ölçekler.
    - Sıfır ondalıklı (nanos == 0) veya 100-adımlı para birimlerinde (JPY, KRW, CLP, PYG, VND, XOF, XAF, CHF vb.)
      tam sayı / 100-adım yuvarlaması uygulayarak Google Play alt-birim reddi riskini sıfırlar.
    """
    out: List[Dict[str, Any]] = []
    for rc in template_174_configs:
        reg_code = str(rc.get("regionCode") or "").strip().upper()
        tmpl_price_obj = rc.get("price") or {}
        tmpl_val, tmpl_ccy = gp_price_to_float(tmpl_price_obj)
        tmpl_nanos = int(tmpl_price_obj.get("nanos") or 0)

        if reg_code in GOOGLE_PLAY_EXPLICIT_TARGETS:
            m_target, a_target, exp_ccy = GOOGLE_PLAY_EXPLICIT_TARGETS[reg_code]
            chosen_val = a_target if is_annual else m_target
            if tmpl_ccy and tmpl_ccy != exp_ccy:
                print(
                    f"  [WARN] Google Play {reg_code} para birimi şablonda {tmpl_ccy} (beklenen {exp_ccy}); "
                    f"şablon para birimine uyarlanıyor."
                )
                if tmpl_ccy == "USD":
                    chosen_val = (12.99 if is_annual else 2.49) if reg_code in ("AZ", "UZ", "KZ", "GE", "UA") else (24.99 if is_annual else 4.99)
                elif tmpl_ccy == "EUR":
                    chosen_val = (16.99 if is_annual else 3.49) if reg_code in ("PL", "RO", "BG", "HU", "CZ") else (29.99 if is_annual else 4.99)
                use_ccy = tmpl_ccy
            else:
                use_ccy = exp_ccy
        else:
            use_ccy = tmpl_ccy or "USD"
            if use_ccy == "USD":
                chosen_val = 14.99 if is_annual else 2.99
            elif use_ccy == "EUR":
                chosen_val = 14.99 if is_annual else 2.99
            else:
                # Şablondaki `misilyillik` zaten ~$12.39 USD PPP eşdeğerindedir; yıllıkta aynen koru, aylıkta 1/5 oranına çek
                if is_annual:
                    chosen_val = tmpl_val
                else:
                    raw_m = tmpl_val / 5.0
                    if tmpl_val >= 2000:
                        # Büyük nominal değerli para birimleri (CLP, COP, IDR, IQD, KRW, KZT, MMK, MNT, NGN, PYG, TZS, UZS, VND, XAF, XOF)
                        chosen_val = float(max(100, int(round(raw_m / 100.0)) * 100))
                    elif tmpl_nanos == 0 or use_ccy in ("CHF", "JPY", "KRW", "VND", "CLP", "PYG", "ISK", "HUF", "TWD", "DKK", "SEK", "NOK"):
                        # Tam sayı (nanos=0) kullanılan para birimlerinde küsurat üretme
                        chosen_val = float(max(1, int(round(raw_m))))
                    elif tmpl_val >= 100:
                        chosen_val = float(round(raw_m))
                    else:
                        # Ondalıklı para birimlerinde .99 veya tam sayıya yuvarla (JOD vb. 3 ondalıklı birimlerde tam sayı güvenli)
                        chosen_val = float(max(1, int(round(raw_m)))) if use_ccy in ("JOD", "KWD", "BHD", "OMR", "TND") else round(raw_m, 2)

        out.append({
            "regionCode": reg_code,
            "newSubscriberAvailability": True,
            "price": float_to_gp_price(chosen_val, use_ccy),
        })

    out_by_region = {x["regionCode"]: x for x in out}

    # Güvenlik 1: TR kesinlikle 149.99 / 599.99 TRY olmalı
    assert "TR" in out_by_region, "TR bölgesi Google Play listesinde bulunamadı!"
    tr_val, tr_ccy = gp_price_to_float(out_by_region["TR"]["price"])
    expected_tr = 599.99 if is_annual else 149.99
    assert tr_ccy == "TRY" and abs(tr_val - expected_tr) < 1e-4, f"TR fiyatı hatalı: {tr_val} {tr_ccy}"

    # Güvenlik 2: CH (şablonda mevcutsa) kesinlikle 5.00 / 25.00 CHF olmalı
    if "CH" in out_by_region:
        ch_val, ch_ccy = gp_price_to_float(out_by_region["CH"]["price"])
        expected_ch = 25.00 if is_annual else 5.00
        assert ch_ccy == "CHF" and abs(ch_val - expected_ch) < 1e-4, f"CH fiyatı hatalı: {ch_val} {ch_ccy}"

    # Güvenlik 3: Tam 174 bölge şablonu verildiğinde 37 açık hedef ülkenin tamamı çıktıda yer almalı
    if len(template_174_configs) >= 170:
        missing_targets = [cc for cc in GOOGLE_PLAY_EXPLICIT_TARGETS if cc not in out_by_region]
        assert not missing_targets, f"Şablonda eksik hedef ülkeler var: {missing_targets}"

    return out


def _gp_patch_with_version_negotiation(
    base_url: str,
    update_mask: str,
    body_dict: Dict[str, Any],
    headers: Dict[str, str],
) -> int:
    """
    Google Play monetization.subscriptions.patch ve offers.patch çağrılarında
    regionsVersion.version parametresini güncel sürümlerle (veya hata mesajından
    okunan resmi sürümle) otomatik müzakere ederek uygular.
    """
    candidate_versions = ["2026/01", "2025/03", "2025/02", "2025/01", "2024/03", "2022/02"]
    last_err = ""
    tried = set()
    idx = 0
    while idx < len(candidate_versions):
        ver = candidate_versions[idx]
        idx += 1
        if ver in tried:
            continue
        tried.add(ver)
        sep = "&" if "?" in base_url else "?"
        full_url = f"{base_url}{sep}updateMask={update_mask}&regionsVersion.version={urllib.parse.quote(ver, safe='/')}"
        req = urllib.request.Request(
            full_url,
            data=json.dumps(body_dict).encode("utf-8"),
            headers=headers,
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                return resp.status
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="ignore")
            last_err = f"HTTP {he.code} (version={ver}): {err_body[:400]}"
            # Google Play hata mesajında güncel regionsVersion sürümü belirtilmişse yakala (örn. 2025/01 veya 2026/01)
            m = re.search(r"20\d{2}/\d{2}", err_body)
            if m and m.group(0) not in tried:
                candidate_versions.insert(idx, m.group(0))
            elif he.code not in (400, 422):
                break
    raise RuntimeError(f"Google Play PATCH başarısız: {last_err}")


def resolve_apple_price_point(
    token: str,
    subscription_id: str,
    territory_iso3: str,
    target_price: float,
) -> Optional[Dict[str, Any]]:
    """
    Apple App Store Connect API üzerinden ilgili abonelik ve ülke (ISO-3) için
    target_price değerine en yakın (eşitlikte daha düşük olan) resmi subscriptionPricePoint kaydını bulur.
    """
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url: Optional[str] = (
        f"https://api.appstoreconnect.apple.com/v1/subscriptions/{subscription_id}/pricePoints"
        f"?filter[territory]={territory_iso3}&include=territory&limit=200"
    )
    candidates: List[Dict[str, Any]] = []
    pages = 0
    while url and pages < 6:
        pages += 1
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        currency = ""
        for inc in payload.get("included", []):
            if inc.get("type") == "territories" and inc.get("id") == territory_iso3:
                currency = inc.get("attributes", {}).get("currency", "")
        for item in payload.get("data", []):
            attrs = item.get("attributes", {})
            cp = float(attrs.get("customerPrice") or 0.0)
            proc = float(attrs.get("proceeds") or 0.0)
            candidates.append({
                "id": item["id"],
                "customerPrice": cp,
                "proceeds": proc,
                "currency": currency,
            })
        # Çoğu ülkede toplam ~800 fiyat noktası vardır ve küçükten büyüğe sıralıdır;
        # ilk 2 sayfada (400 nokta) hedef fiyatın 2 katını geçtiysek durabiliriz.
        if candidates and min(c["customerPrice"] for c in candidates[-50:]) >= target_price * 2.0:
            break
        url = (payload.get("links") or {}).get("next")

    if not candidates:
        return None
    # Hedef fiyata mutlak farkı en küçük olan (eşitlikte daha ucuz olan) noktayı seç
    candidates.sort(key=lambda x: (abs(x["customerPrice"] - target_price), x["customerPrice"]))
    return candidates[0]


def fetch_current_apple_prices(ap_hdrs: Dict[str, str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    current_apple_prices: Dict[str, Dict[str, Dict[str, Any]]] = {
        APPLE_MONTHLY_SUB_ID: {},
        APPLE_ANNUAL_SUB_ID: {},
    }
    for sid in (APPLE_MONTHLY_SUB_ID, APPLE_ANNUAL_SUB_ID):
        p_url = f"https://api.appstoreconnect.apple.com/v1/subscriptions/{sid}/prices?include=subscriptionPricePoint,territory&limit=200"
        req = urllib.request.Request(p_url, headers=ap_hdrs)
        with urllib.request.urlopen(req, timeout=15) as resp:
            p_payload = json.loads(resp.read().decode("utf-8"))
        inc_pts = {
            x["id"]: x.get("attributes", {})
            for x in p_payload.get("included", [])
            if x.get("type") == "subscriptionPricePoints"
        }
        inc_terrs = {
            x["id"]: x.get("attributes", {})
            for x in p_payload.get("included", [])
            if x.get("type") == "territories"
        }
        for item in p_payload.get("data", []):
            rels = item.get("relationships", {})
            pp_id = (rels.get("subscriptionPricePoint", {}).get("data") or {}).get("id")
            t_id = (rels.get("territory", {}).get("data") or {}).get("id")
            if t_id and pp_id:
                current_apple_prices[sid][t_id] = {
                    "price_id": item["id"],
                    "pricePointId": pp_id,
                    "customerPrice": float(inc_pts.get(pp_id, {}).get("customerPrice") or 0.0),
                    "proceeds": float(inc_pts.get(pp_id, {}).get("proceeds") or 0.0),
                    "currency": inc_terrs.get(t_id, {}).get("currency", ""),
                    "startDate": (item.get("attributes") or {}).get("startDate"),
                }
    return current_apple_prices


def run_sync(apply_changes: bool = False) -> Dict[str, Any]:
    assert_tr_ch_invariants()
    mode_lbl = "APPLY (CANLI MAĞAZA GÜNCELLEMESİ)" if apply_changes else "DRY-RUN (SALT-OKUNUR SİMÜLASYON)"
    print("======================================================================")
    print(f"Mışıl Baby Küresel PPP Fiyat Motoru — Mod: {mode_lbl}")
    print("======================================================================")

    # 1. GOOGLE PLAY HAZIRLIĞI VE DENETİMİ
    gp_token = get_google_play_token()
    gp_hdrs = {"Authorization": f"Bearer {gp_token}", "Content-Type": "application/json"}
    sub_req = urllib.request.Request(
        f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{PACKAGE_NAME}/subscriptions",
        headers=gp_hdrs,
    )
    with urllib.request.urlopen(sub_req, timeout=15) as resp:
        gp_subs_payload = json.loads(resp.read().decode("utf-8"))

    subs_by_id = {s["productId"]: s for s in gp_subs_payload.get("subscriptions", [])}
    tmpl_sub = subs_by_id.get("misilyillik")
    if not tmpl_sub:
        raise RuntimeError("Google Play üzerinde 174 bölge şablonu için 'misilyillik' bulunamadı.")
    template_174 = tmpl_sub["basePlans"][0]["regionalConfigs"]
    print(f"\n[Google Play] 174 Bölge Şablonu Yüklendi ({len(template_174)} ülke).")

    gp_annual_configs = build_google_play_174_configs(template_174, is_annual=True)
    gp_monthly_configs = build_google_play_174_configs(template_174, is_annual=False)

    gp_annual_map = {x["regionCode"]: gp_price_to_float(x["price"]) for x in gp_annual_configs}
    gp_monthly_map = {x["regionCode"]: gp_price_to_float(x["price"]) for x in gp_monthly_configs}

    print(f"\n--- GOOGLE PLAY HEDEF FİYAT TABLOSU ({len(GOOGLE_PLAY_EXPLICIT_TARGETS)} Anahtar Ülke + {len(gp_annual_configs) - len(GOOGLE_PLAY_EXPLICIT_TARGETS)} Otomatik PPP Bölgesi) ---")
    for cc in GOOGLE_PLAY_EXPLICIT_TARGETS.keys():
        m_v, m_c = gp_monthly_map.get(cc, (0.0, "-"))
        a_v, a_c = gp_annual_map.get(cc, (0.0, "-"))
        prot = " [KORUNAN BAZ]" if cc in PROTECTED_COUNTRIES else ""
        print(f"  {cc}: Aylık {m_v:.2f} {m_c} | Yıllık {a_v:.2f} {a_c}{prot}")

    if apply_changes:
        for pid, bpid, new_configs, is_ann in [
            ("misilaylik", "misilaylik", gp_monthly_configs, False),
            ("misil", "misil", gp_annual_configs, True),
        ]:
            sub_obj = subs_by_id[pid]
            bp_obj = sub_obj["basePlans"][0]
            bp_obj["regionalConfigs"] = new_configs
            bp_obj["otherRegionsConfig"] = {
                "usdPrice": float_to_gp_price(14.99 if is_ann else 2.99, "USD"),
                "eurPrice": float_to_gp_price(14.99 if is_ann else 2.99, "EUR"),
                "newSubscriberAvailability": True,
            }
            sub_base_url = (
                f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{PACKAGE_NAME}"
                f"/subscriptions/{pid}"
            )
            status_code = _gp_patch_with_version_negotiation(
                sub_base_url,
                "basePlans",
                sub_obj,
                gp_hdrs,
            )
            print(f"  [OK] Google Play {pid} BasePlan {len(new_configs)} ülke güncellendi (HTTP {status_code}).")

            # Aktif 7 günlük ücretsiz deneme teklifini (P7D) hem offer hem phases[0] düzeyinde 174 bölgede aç
            offer_id = "3daystrial" if is_ann else "freeytrial"
            off_get_url = (
                f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{PACKAGE_NAME}"
                f"/subscriptions/{pid}/basePlans/{bpid}/offers/{offer_id}"
            )
            off_req = urllib.request.Request(off_get_url, headers=gp_hdrs)
            with urllib.request.urlopen(off_req, timeout=10) as off_resp:
                off_obj = json.loads(off_resp.read().decode("utf-8"))

            off_obj["regionalConfigs"] = [
                {"regionCode": rc["regionCode"], "newSubscriberAvailability": True}
                for rc in new_configs
            ]
            off_obj["otherRegionsConfig"] = {"otherRegionsNewSubscriberAvailability": True}
            if off_obj.get("phases"):
                off_obj["phases"][0]["regionalConfigs"] = [
                    {"regionCode": rc["regionCode"], "free": {}}
                    for rc in new_configs
                ]
                off_obj["phases"][0]["otherRegionsConfig"] = {"free": {}}

            off_status = _gp_patch_with_version_negotiation(
                off_get_url,
                "phases,regionalConfigs,otherRegionsConfig",
                off_obj,
                gp_hdrs,
            )
            print(f"  [OK] Google Play {pid}/{offer_id} (P7D 7G Ücretsiz Deneme) {len(new_configs)} ülkede açıldı (HTTP {off_status}).")

    # 2. APPLE APP STORE CONNECT HAZIRLIĞI VE DENETİMİ
    ap_token = get_apple_token()
    ap_hdrs = {"Authorization": f"Bearer {ap_token}", "Content-Type": "application/json"}

    current_apple_prices = fetch_current_apple_prices(ap_hdrs)

    print(f"\n--- APPLE APP STORE CONNECT HEDEF FİYAT NOKTASI EŞLEŞTİRMESİ ({len(APPLE_PPP_TARGETS)} Ülke) ---")
    apple_resolved_plan: List[Dict[str, Any]] = []
    tomorrow_utc = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    for cc, (m_target, a_target, exp_ccy) in APPLE_PPP_TARGETS.items():
        iso3 = ISO2_TO_ISO3[cc]
        cur_m = current_apple_prices[APPLE_MONTHLY_SUB_ID].get(iso3, {})
        cur_a = current_apple_prices[APPLE_ANNUAL_SUB_ID].get(iso3, {})

        if cc in PROTECTED_COUNTRIES:
            print(
                f"  {cc} ({iso3}) [KORUNUR]: "
                f"Aylık {cur_m.get('customerPrice')} {cur_m.get('currency')} | "
                f"Yıllık {cur_a.get('customerPrice')} {cur_a.get('currency')}"
            )
            continue

        res_m = resolve_apple_price_point(ap_token, APPLE_MONTHLY_SUB_ID, iso3, m_target)
        res_a = resolve_apple_price_point(ap_token, APPLE_ANNUAL_SUB_ID, iso3, a_target)
        if not res_m or not res_a:
            print(f"  [WARN] {cc} ({iso3}) için Apple pricePoint bulunamadı!")
            continue

        m_changed = abs(cur_m.get("customerPrice", 0.0) - res_m["customerPrice"]) > 1e-3
        a_changed = abs(cur_a.get("customerPrice", 0.0) - res_a["customerPrice"]) > 1e-3
        print(
            f"  {cc} ({iso3}): "
            f"Aylık {cur_m.get('customerPrice')} -> {res_m['customerPrice']} {res_m['currency']} "
            f"(Net: {res_m['proceeds']}) | "
            f"Yıllık {cur_a.get('customerPrice')} -> {res_a['customerPrice']} {res_a['currency']} "
            f"(Net: {res_a['proceeds']})"
        )
        apple_resolved_plan.append({
            "cc": cc,
            "iso3": iso3,
            "monthly": res_m,
            "annual": res_a,
            "m_changed": m_changed,
            "a_changed": a_changed,
        })

        if apply_changes:
            for sid, res_pt, changed_flag, lbl in [
                (APPLE_MONTHLY_SUB_ID, res_m, m_changed, "Aylık"),
                (APPLE_ANNUAL_SUB_ID, res_a, a_changed, "Yıllık"),
            ]:
                if not changed_flag:
                    continue
                # Önce startDate: None (anında yürürlük) dene; mevcut aktif fiyat nedeniyle 409 dönerse yarınki UTC startDate ile planla
                applied_ok = False
                for candidate_start in (None, tomorrow_utc):
                    body = {
                        "data": {
                            "type": "subscriptionPrices",
                            "attributes": {
                                "startDate": candidate_start,
                                "preserveCurrentPrice": False,
                            },
                            "relationships": {
                                "subscription": {"data": {"type": "subscriptions", "id": sid}},
                                "territory": {"data": {"type": "territories", "id": iso3}},
                                "subscriptionPricePoint": {
                                    "data": {"type": "subscriptionPricePoints", "id": res_pt["id"]}
                                },
                            },
                        }
                    }
                    post_req = urllib.request.Request(
                        "https://api.appstoreconnect.apple.com/v1/subscriptionPrices",
                        data=json.dumps(body).encode("utf-8"),
                        headers=ap_hdrs,
                        method="POST",
                    )
                    try:
                        with urllib.request.urlopen(post_req, timeout=15) as post_resp:
                            sd_lbl = candidate_start or "ANINDA"
                            print(f"    [OK] Apple {iso3} {lbl} güncellendi -> {res_pt['customerPrice']} {res_pt['currency']} (startDate={sd_lbl}, HTTP {post_resp.status})")
                            applied_ok = True
                            break
                    except urllib.error.HTTPError as he:
                        err_txt = he.read().decode("utf-8", errors="ignore")
                        if he.code == 409 and candidate_start is None:
                            continue
                        print(f"    [ERR] Apple {iso3} {lbl} (startDate={candidate_start}) HTTP {he.code}: {err_txt[:300]}")
                if not applied_ok:
                    print(f"    [WARN] Apple {iso3} {lbl} güncellenemedi.")

    # 3. CANLI UYGULAMA SONRASI GET İLE DOĞRULAMA (POST-APPLY VERIFICATION)
    if apply_changes:
        print("\n--- 3. CANLI MAĞAZA DOĞRULAMA (POST-APPLY GET VERIFICATION) ---")
        with urllib.request.urlopen(sub_req, timeout=15) as v_resp:
            v_gp_payload = json.loads(v_resp.read().decode("utf-8"))
        v_subs = {s["productId"]: s for s in v_gp_payload.get("subscriptions", [])}
        for pid, expected_tr_val, expected_ch_val in [
            ("misilaylik", 149.99, 5.00),
            ("misil", 599.99, 25.00),
        ]:
            rcs = v_subs[pid]["basePlans"][0].get("regionalConfigs", [])
            rc_map = {r["regionCode"]: gp_price_to_float(r["price"]) for r in rcs}
            assert len(rcs) >= 170, f"Google Play {pid} bölge sayısı eksik: {len(rcs)}"
            assert rc_map.get("TR") == (expected_tr_val, "TRY"), f"Google Play {pid} TR doğrulama hatası: {rc_map.get('TR')}"
            assert rc_map.get("CH") == (expected_ch_val, "CHF"), f"Google Play {pid} CH doğrulama hatası: {rc_map.get('CH')}"
            print(f"  [VERIFIED] Google Play {pid}: {len(rcs)} ülke aktif | TR={rc_map['TR']} | CH={rc_map['CH']}")

        v_apple = fetch_current_apple_prices(ap_hdrs)
        assert v_apple[APPLE_MONTHLY_SUB_ID].get("TUR", {}).get("customerPrice") == 149.99, "Apple TUR Aylık değişti!"
        assert v_apple[APPLE_ANNUAL_SUB_ID].get("TUR", {}).get("customerPrice") == 599.99, "Apple TUR Yıllık değişti!"
        assert v_apple[APPLE_MONTHLY_SUB_ID].get("CHE", {}).get("customerPrice") == 5.00, "Apple CHE Aylık değişti!"
        assert v_apple[APPLE_ANNUAL_SUB_ID].get("CHE", {}).get("customerPrice") == 25.00, "Apple CHE Yıllık değişti!"
        print("  [VERIFIED] Apple App Store Connect: TUR (149.99 / 599.99 TRY) ve CHE (5.00 / 25.00 CHF) korundu.")

    return {
        "mode": "apply" if apply_changes else "dry_run",
        "gp_regions_count": len(gp_annual_configs),
        "apple_resolved_count": len(apple_resolved_plan),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mışıl Baby PPP Mağaza Fiyat Senkronizasyon Motoru")
    parser.add_argument("--apply", action="store_true", help="Değişiklikleri mağaza API'larına canlı uygular.")
    parser.add_argument("--dry-run", action="store_true", help="Salt-okunur simülasyon çalıştırır (varsayılan).")
    args = parser.parse_args()
    run_sync(apply_changes=bool(args.apply))


if __name__ == "__main__":
    main()
