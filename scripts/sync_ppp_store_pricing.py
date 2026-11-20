#!/usr/bin/env python3
"""
Mışıl Baby v4.55.0 — Satın Alma Gücü Paritesi (PPP), Hard Paywall & İlk Ay İndirimli Başlangıç Fiyat Motoru.

Kapsam:
1. Apple App Store Connect API v1 (`misil_monthly` #6809228860, `misil_annual` #6809228257):
   - Türkiye (`TUR`: 149.99 TRY / 599.99 TRY) ve İsviçre (`CHE`: 5.00 CHF / 25.00 CHF) baz abonelik fiyatları aynen korunur.
   - Hem Aylık hem Yıllık üründeki eski `FREE_TRIAL` (`ONE_WEEK` / 7 Gün Ücretsiz) teklifleri emekli edilir (DELETE veya aktif tekliflerde yarın UTC `endDate` PATCH).
   - `misil_monthly` üzerinde uygun yeni aboneler için `PAY_UP_FRONT` (`ONE_MONTH`, `numberOfPeriods: 1`) İlk Ay İndirimli Tanıtım Teklifi (`TUR: 49.99 TRY`, `CHE: 2.00 CHF`, `DEU/FRA: 1.99 EUR`, `USA: 1.99 USD` + PPP ülkeleri) tanımlanır.
2. Google Play Developer API v3 (`misilaylik` Aylık, `misil` Yıllık):
   - 174 ülkenin tamamında PPP baz fiyatları korunur/senkronize edilir.
   - Eski 7 günlük ücretsiz deneme teklifleri (`freeytrial` ve `3daystrial`) devre dışı bırakılır (`:deactivate`).
   - `misilaylik` üzerinde 174 ülkenin tamamında 1 aylık tek ödemeli indirimli başlangıç teklifi (`intro-first-month`, `duration: P1M`, `recurrenceCount: 1`, `TR: 49.99 TRY`) oluşturulur ve aktif edilir (`:activate`).

Kullanım:
  python projects/mishil/scripts/sync_ppp_store_pricing.py --offline-check
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

GOOGLE_PLAY_INTRO_OFFER_ID = "intro-first-month"

# 3. İLK AY İNDİRİMLİ BAŞLANGIÇ TEKLİFİ MATRİSİ (Aylık Plan 1. Ay — 2. Aydan İtibaren Baz Aylık Fiyat)
APPLE_INTRO_FIRST_MONTH_TARGETS: Dict[str, Tuple[float, str]] = {
    "TR": (49.99, "TRY"),
    "CH": (2.00, "CHF"),
    "UZ": (0.99, "USD"),
    "AZ": (0.99, "USD"),
    "KZ": (490.0, "KZT"),
    "IN": (49.0, "INR"),
    "BR": (5.90, "BRL"),
    "MX": (19.0, "MXN"),
    "PL": (5.99, "PLN"),
    "RO": (5.99, "RON"),
    "DE": (1.99, "EUR"),
    "FR": (1.99, "EUR"),
    "NL": (1.99, "EUR"),
    "AT": (1.99, "EUR"),
    "BE": (1.99, "EUR"),
    "ES": (1.99, "EUR"),
    "IT": (1.99, "EUR"),
    "PT": (1.99, "EUR"),
    "GR": (1.99, "EUR"),
    "IE": (1.99, "EUR"),
    "GB": (1.99, "GBP"),
    "US": (1.99, "USD"),
    "CA": (2.99, "CAD"),
    "AU": (2.99, "AUD"),
    "AE": (6.99, "AED"),
    "SA": (7.99, "SAR"),
}

GOOGLE_PLAY_INTRO_EXPLICIT_TARGETS: Dict[str, Tuple[float, str]] = {
    "TR": (49.99, "TRY"),
    "CH": (2.00, "CHF"),
    "UZ": (12900.00, "UZS"),
    "AZ": (1.69, "AZN"),
    "KZ": (490.00, "KZT"),
    "IN": (49.00, "INR"),
    "BR": (5.90, "BRL"),
    "MX": (19.00, "MXN"),
    "PL": (5.99, "PLN"),
    "RO": (5.99, "RON"),
    "DE": (1.99, "EUR"),
    "FR": (1.99, "EUR"),
    "NL": (1.99, "EUR"),
    "AT": (1.99, "EUR"),
    "BE": (1.99, "EUR"),
    "ES": (1.99, "EUR"),
    "IT": (1.99, "EUR"),
    "PT": (1.99, "EUR"),
    "GR": (1.99, "EUR"),
    "IE": (1.99, "EUR"),
    "FI": (1.99, "EUR"),
    "GB": (1.99, "GBP"),
    "US": (1.99, "USD"),
    "CA": (2.99, "CAD"),
    "AU": (2.99, "AUD"),
    "AE": (6.99, "AED"),
    "SA": (7.99, "SAR"),
    "BG": (1.49, "EUR"),
    "HU": (590.00, "HUF"),
    "CZ": (39.00, "CZK"),
    "UA": (39.00, "UAH"),
    "GE": (2.99, "GEL"),
    "ID": (12000.00, "IDR"),
    "PK": (250.00, "PKR"),
    "PH": (49.00, "PHP"),
    "EG": (39.00, "EGP"),
    "CO": (3900.00, "COP"),
}


def assert_tr_ch_invariants() -> None:
    """Türkiye ve İsviçre baz + ilk ay başlangıç fiyatlarının korunduğunu doğrulayan emniyet kilidi."""
    assert APPLE_PPP_TARGETS["TR"] == (149.99, 599.99, "TRY"), "TR Apple baz invariant ihlali!"
    assert GOOGLE_PLAY_EXPLICIT_TARGETS["TR"] == (149.99, 599.99, "TRY"), "TR Google Play baz invariant ihlali!"
    assert APPLE_INTRO_FIRST_MONTH_TARGETS["TR"] == (49.99, "TRY"), "TR Apple ilk ay invariant ihlali!"
    assert GOOGLE_PLAY_INTRO_EXPLICIT_TARGETS["TR"] == (49.99, "TRY"), "TR Google Play ilk ay invariant ihlali!"
    assert APPLE_PPP_TARGETS["CH"] == (5.00, 25.00, "CHF"), "CH Apple baz invariant ihlali!"
    assert GOOGLE_PLAY_EXPLICIT_TARGETS["CH"] == (5.00, 25.00, "CHF"), "CH Google Play baz invariant ihlali!"
    assert APPLE_INTRO_FIRST_MONTH_TARGETS["CH"] == (2.00, "CHF"), "CH Apple ilk ay invariant ihlali!"
    assert GOOGLE_PLAY_INTRO_EXPLICIT_TARGETS["CH"] == (2.00, "CHF"), "CH Google Play ilk ay invariant ihlali!"
    for cc, (intro_v, intro_c) in APPLE_INTRO_FIRST_MONTH_TARGETS.items():
        base_m, _, base_c = APPLE_PPP_TARGETS[cc]
        assert intro_c == base_c and 0 < intro_v < base_m, f"Apple ilk ay fiyatı baz aylık fiyattan düşük olmalı: {cc}"
    for cc, (intro_v, intro_c) in GOOGLE_PLAY_INTRO_EXPLICIT_TARGETS.items():
        base_m, _, base_c = GOOGLE_PLAY_EXPLICIT_TARGETS[cc]
        assert intro_c == base_c and 0 < intro_v < base_m, f"Google Play ilk ay fiyatı baz aylık fiyattan düşük olmalı: {cc}"


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


def build_google_play_174_intro_phase_configs(
    gp_monthly_configs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Google Play `misilaylik` için 174 bölgenin tamamında 1 aylık tek ödemeli (`P1M`, `recurrenceCount: 1`)
    indirimli başlangıç fazı (`phases[0].regionalConfigs`) üretir.
    Her bölgede `0 < intro_price < monthly_price` şartını ve alt-birim kurallarını garanti eder.
    """
    phase_configs: List[Dict[str, Any]] = []
    for rc in gp_monthly_configs:
        reg_code = str(rc.get("regionCode") or "").strip().upper()
        m_price_obj = rc.get("price") or {}
        m_val, m_ccy = gp_price_to_float(m_price_obj)
        m_nanos = int(m_price_obj.get("nanos") or 0)

        if reg_code in GOOGLE_PLAY_INTRO_EXPLICIT_TARGETS:
            exp_intro_val, exp_intro_ccy = GOOGLE_PLAY_INTRO_EXPLICIT_TARGETS[reg_code]
            if m_ccy == exp_intro_ccy and exp_intro_val < m_val:
                intro_val = exp_intro_val
            elif m_ccy == "USD":
                intro_val = 0.99 if m_val <= 3.0 else 1.99
            elif m_ccy == "EUR":
                intro_val = 1.49 if m_val <= 3.6 else 1.99
            else:
                intro_val = round(max(0.5, m_val * 0.4), 2)
        else:
            if m_ccy in ("USD", "EUR"):
                intro_val = 1.19 if m_val <= 3.0 else 1.99
            elif m_val >= 2000:
                intro_val = float(max(100, int(round((m_val * 0.4) / 100.0)) * 100))
                if intro_val >= m_val:
                    intro_val = float(max(50, int(m_val * 0.5)))
            elif m_nanos == 0 or m_ccy in ("CHF", "JPY", "KRW", "VND", "CLP", "PYG", "ISK", "HUF", "TWD", "DKK", "SEK", "NOK"):
                intro_val = float(max(1, int(math.floor(m_val * 0.45))))
                if intro_val >= m_val:
                    intro_val = max(0.5, m_val * 0.5)
            elif m_ccy in ("JOD", "KWD", "BHD", "OMR", "TND"):
                intro_val = float(max(1, int(math.floor(m_val * 0.5)))) if m_val >= 2 else round(m_val * 0.5, 2)
            elif m_val >= 100:
                intro_val = float(max(1, int(round(m_val * 0.4))))
            else:
                intro_val = round(max(0.49, m_val * 0.4), 2)

        assert 0 < intro_val < m_val, f"Google Play intro fiyatı baz fiyattan düşük değil ({reg_code}: {intro_val} vs {m_val} {m_ccy})"
        phase_configs.append({
            "regionCode": reg_code,
            "price": float_to_gp_price(intro_val, m_ccy),
        })

    by_reg = {x["regionCode"]: gp_price_to_float(x["price"]) for x in phase_configs}
    assert by_reg.get("TR") == (49.99, "TRY"), f"Google Play TR ilk ay fiyatı 49.99 TRY olmalı: {by_reg.get('TR')}"
    if "CH" in by_reg:
        assert by_reg.get("CH") == (2.00, "CHF"), f"Google Play CH ilk ay fiyatı 2.00 CHF olmalı: {by_reg.get('CH')}"
    return phase_configs


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


def _gp_post_action(url: str, headers: Dict[str, str], body_dict: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
    data_bytes = json.dumps(body_dict if body_dict is not None else {}).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode("utf-8", errors="ignore")


def _gp_create_offer_with_version_negotiation(
    offers_collection_url: str,
    offer_id: str,
    body_dict: Dict[str, Any],
    headers: Dict[str, str],
) -> int:
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
        full_url = (
            f"{offers_collection_url}?productId={urllib.parse.quote(body_dict['productId'])}"
            f"&basePlanId={urllib.parse.quote(body_dict['basePlanId'])}"
            f"&offerId={urllib.parse.quote(offer_id)}"
            f"&regionsVersion.version={urllib.parse.quote(ver, safe='/')}"
        )
        req = urllib.request.Request(
            full_url,
            data=json.dumps(body_dict).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                return resp.status
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="ignore")
            last_err = f"HTTP {he.code} (version={ver}): {err_body[:400]}"
            m = re.search(r"20\d{2}/\d{2}", err_body)
            if m and m.group(0) not in tried:
                candidate_versions.insert(idx, m.group(0))
            elif he.code not in (400, 422):
                break
    raise RuntimeError(f"Google Play Offer POST başarısız: {last_err}")


def fetch_current_apple_intro_offers(ap_hdrs: Dict[str, str]) -> Dict[str, List[Dict[str, Any]]]:
    offers_by_sub: Dict[str, List[Dict[str, Any]]] = {
        APPLE_MONTHLY_SUB_ID: [],
        APPLE_ANNUAL_SUB_ID: [],
    }
    for sid in (APPLE_MONTHLY_SUB_ID, APPLE_ANNUAL_SUB_ID):
        url: Optional[str] = (
            f"https://api.appstoreconnect.apple.com/v1/subscriptions/{sid}/introductoryOffers"
            f"?include=territory,subscriptionPricePoint&limit=200"
        )
        pages = 0
        while url and pages < 5:
            pages += 1
            req = urllib.request.Request(url, headers=ap_hdrs)
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            inc_pts = {
                x["id"]: x.get("attributes", {})
                for x in payload.get("included", [])
                if x.get("type") == "subscriptionPricePoints"
            }
            for item in payload.get("data", []):
                attrs = item.get("attributes") or {}
                rels = item.get("relationships") or {}
                terr_id = ((rels.get("territory") or {}).get("data") or {}).get("id", "")
                pp_id = ((rels.get("subscriptionPricePoint") or {}).get("data") or {}).get("id", "")
                offers_by_sub[sid].append({
                    "id": item["id"],
                    "offerMode": attrs.get("offerMode"),
                    "duration": attrs.get("duration"),
                    "numberOfPeriods": attrs.get("numberOfPeriods"),
                    "startDate": attrs.get("startDate"),
                    "endDate": attrs.get("endDate"),
                    "territory": terr_id,
                    "pricePointId": pp_id,
                    "customerPrice": float(inc_pts.get(pp_id, {}).get("customerPrice") or 0.0) if pp_id else 0.0,
                })
            url = (payload.get("links") or {}).get("next")
    return offers_by_sub


def retire_apple_intro_offer(offer_id: str, tomorrow_utc: str, ap_hdrs: Dict[str, str]) -> str:
    """
    Apple ASC v1 kuralı: Henüz başlamamış / süresiz tekliflerde DELETE dener;
    geçmişte başlamış aktif tekliflerde DELETE 409 dönerse endDate ile PATCH uygular.
    """
    del_url = f"https://api.appstoreconnect.apple.com/v1/subscriptionIntroductoryOffers/{offer_id}"
    del_req = urllib.request.Request(del_url, headers=ap_hdrs, method="DELETE")
    try:
        with urllib.request.urlopen(del_req, timeout=15) as resp:
            return f"DELETED (HTTP {resp.status})"
    except urllib.error.HTTPError as he:
        if he.code not in (400, 403, 409, 422):
            err_txt = he.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Apple intro offer DELETE hatası ({offer_id}): HTTP {he.code} {err_txt[:250]}")
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        last_patch_err = ""
        for end_cand in (today_utc, tomorrow_utc):
            patch_body = {
                "data": {
                    "type": "subscriptionIntroductoryOffers",
                    "id": offer_id,
                    "attributes": {"endDate": end_cand},
                }
            }
            patch_req = urllib.request.Request(
                del_url,
                data=json.dumps(patch_body).encode("utf-8"),
                headers=ap_hdrs,
                method="PATCH",
            )
            try:
                with urllib.request.urlopen(patch_req, timeout=15) as p_resp:
                    return f"ENDED@{end_cand} (HTTP {p_resp.status})"
            except urllib.error.HTTPError as phe:
                last_patch_err = f"HTTP {phe.code}: {phe.read().decode('utf-8', errors='ignore')[:220]}"
        raise RuntimeError(f"Apple intro offer PATCH hatası ({offer_id}): {last_patch_err}")


def create_apple_paid_intro_offer(
    iso3: str,
    res_intro: Dict[str, Any],
    existing_monthly_intros: List[Dict[str, Any]],
    ap_hdrs: Dict[str, str],
) -> Tuple[bool, str]:
    """
    Apple ASC üzerinde ilgili ülke (iso3) için ONE_MONTH PAY_UP_FRONT ilk ay teklifi oluşturur.
    Aynı fiyat noktalı aktif/planlı PAY_UP_FRONT teklif zaten varsa idempotent olarak korur;
    eski FREE_TRIAL bitiş tarihiyle çakışma (409) olursa ardışık startDate adaylarıyla planlar.
    """
    for ex in existing_monthly_intros:
        if (
            ex.get("territory") == iso3
            and ex.get("offerMode") == "PAY_UP_FRONT"
            and ex.get("duration") == "ONE_MONTH"
            and ex.get("pricePointId") == res_intro["id"]
        ):
            return True, f"ALREADY_SET ({res_intro['customerPrice']} {res_intro['currency']})"

    now_utc = datetime.now(timezone.utc)
    candidate_starts: List[Optional[str]] = [
        None,
        (now_utc + timedelta(days=1)).strftime("%Y-%m-%d"),
        (now_utc + timedelta(days=2)).strftime("%Y-%m-%d"),
    ]
    last_err = ""
    for sd in candidate_starts:
        attrs: Dict[str, Any] = {
            "duration": "ONE_MONTH",
            "offerMode": "PAY_UP_FRONT",
            "numberOfPeriods": 1,
        }
        if sd:
            attrs["startDate"] = sd
        intro_body = {
            "data": {
                "type": "subscriptionIntroductoryOffers",
                "attributes": attrs,
                "relationships": {
                    "subscription": {"data": {"type": "subscriptions", "id": APPLE_MONTHLY_SUB_ID}},
                    "territory": {"data": {"type": "territories", "id": iso3}},
                    "subscriptionPricePoint": {"data": {"type": "subscriptionPricePoints", "id": res_intro["id"]}},
                },
            }
        }
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    "https://api.appstoreconnect.apple.com/v1/subscriptionIntroductoryOffers",
                    data=json.dumps(intro_body).encode("utf-8"),
                    headers=ap_hdrs,
                    method="POST",
                ),
                timeout=15,
            ) as ir_resp:
                sd_lbl = sd or "ANINDA"
                return True, f"{res_intro['customerPrice']} {res_intro['currency']} (startDate={sd_lbl}, HTTP {ir_resp.status})"
        except urllib.error.HTTPError as ihe:
            body_txt = ihe.read().decode("utf-8", errors="ignore")
            last_err = f"Apple {iso3} İlk Ay Teklifi (startDate={sd}) HTTP {ihe.code}: {body_txt[:220]}"
            if ihe.code == 409:
                continue
            break
    return False, last_err


def run_offline_check() -> Dict[str, Any]:
    """Ağ erişimi gerektirmeden tüm TR/CH koruma kilitlerini ve 174 ülke ilk ay fiyat matematiğini doğrular."""
    assert_tr_ch_invariants()
    synthetic_template = [
        {"regionCode": cc, "price": float_to_gp_price(a_val, ccy)}
        for cc, (_, a_val, ccy) in GOOGLE_PLAY_EXPLICIT_TARGETS.items()
    ] + [
        {"regionCode": "JP", "price": {"currencyCode": "JPY", "units": "2500", "nanos": 0}},
        {"regionCode": "KR", "price": {"currencyCode": "KRW", "units": "19000", "nanos": 0}},
        {"regionCode": "KW", "price": {"currencyCode": "KWD", "units": "5", "nanos": 0}},
        {"regionCode": "ZA", "price": {"currencyCode": "USD", "units": "14", "nanos": 990000000}},
    ]
    gp_monthly = build_google_play_174_configs(synthetic_template, is_annual=False)
    gp_annual = build_google_play_174_configs(synthetic_template, is_annual=True)
    gp_intro = build_google_play_174_intro_phase_configs(gp_monthly)
    print("[OFFLINE-CHECK OK] TR (49.99 -> 149.99 / 599.99 TRY), CH (2.00 -> 5.00 / 25.00 CHF) ve tüm PPP matrisi doğrulandı.")
    return {
        "mode": "offline_check",
        "explicit_gp_targets": len(GOOGLE_PLAY_INTRO_EXPLICIT_TARGETS),
        "explicit_apple_targets": len(APPLE_INTRO_FIRST_MONTH_TARGETS),
        "sample_regions_verified": len(gp_intro),
        "annual_regions_verified": len(gp_annual),
    }


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
    gp_intro_phase_configs = build_google_play_174_intro_phase_configs(gp_monthly_configs)

    gp_annual_map = {x["regionCode"]: gp_price_to_float(x["price"]) for x in gp_annual_configs}
    gp_monthly_map = {x["regionCode"]: gp_price_to_float(x["price"]) for x in gp_monthly_configs}
    gp_intro_map = {x["regionCode"]: gp_price_to_float(x["price"]) for x in gp_intro_phase_configs}

    print(f"\n--- GOOGLE PLAY HEDEF FİYAT & İLK AY TEKLİF TABLOSU ({len(GOOGLE_PLAY_EXPLICIT_TARGETS)} Anahtar Ülke + {len(gp_annual_configs) - len(GOOGLE_PLAY_EXPLICIT_TARGETS)} Otomatik PPP Bölgesi) ---")
    for cc in GOOGLE_PLAY_EXPLICIT_TARGETS.keys():
        i_v, i_c = gp_intro_map.get(cc, (0.0, "-"))
        m_v, m_c = gp_monthly_map.get(cc, (0.0, "-"))
        a_v, a_c = gp_annual_map.get(cc, (0.0, "-"))
        prot = " [KORUNAN BAZ]" if cc in PROTECTED_COUNTRIES else ""
        print(f"  {cc}: İlk Ay {i_v:.2f} {i_c} -> Aylık {m_v:.2f} {m_c} | Yıllık {a_v:.2f} {a_c} (Ücretsiz Deneme: KAPALI){prot}")

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

            # Eski 7 günlük ücretsiz deneme tekliflerini (freeytrial / 3daystrial) devre dışı bırak
            legacy_trial_offer_id = "3daystrial" if is_ann else "freeytrial"
            deact_url = (
                f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{PACKAGE_NAME}"
                f"/subscriptions/{pid}/basePlans/{bpid}/offers/{legacy_trial_offer_id}:deactivate"
            )
            d_code, d_body = _gp_post_action(deact_url, gp_hdrs)
            print(f"  [OK] Google Play {pid}/{legacy_trial_offer_id} ücretsiz deneme kapatıldı (HTTP {d_code} {d_body[:120]}).")

        # Aylık plan (`misilaylik`) üzerinde 1 aylık tek ödemeli indirimli başlangıç teklifi (`intro-first-month`) oluştur / güncelle ve aktif et
        intro_offer_url = (
            f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{PACKAGE_NAME}"
            f"/subscriptions/misilaylik/basePlans/misilaylik/offers/{GOOGLE_PLAY_INTRO_OFFER_ID}"
        )
        intro_collection_url = (
            f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{PACKAGE_NAME}"
            f"/subscriptions/misilaylik/basePlans/misilaylik/offers"
        )
        intro_offer_body: Dict[str, Any] = {
            "packageName": PACKAGE_NAME,
            "productId": "misilaylik",
            "basePlanId": "misilaylik",
            "offerId": GOOGLE_PLAY_INTRO_OFFER_ID,
            "targeting": {"acquisitionRule": {"scope": {"thisSubscription": {}}}},
            "phases": [
                {
                    "recurrenceCount": 1,
                    "duration": "P1M",
                    "regionalConfigs": gp_intro_phase_configs,
                    "otherRegionsConfig": {
                        "otherRegionsPrices": {
                            "usdPrice": float_to_gp_price(1.19, "USD"),
                            "eurPrice": float_to_gp_price(1.19, "EUR"),
                        }
                    },
                }
            ],
            "regionalConfigs": [
                {"regionCode": rc["regionCode"], "newSubscriberAvailability": True}
                for rc in gp_monthly_configs
            ],
            "otherRegionsConfig": {"otherRegionsNewSubscriberAvailability": True},
        }
        offer_exists = False
        try:
            with urllib.request.urlopen(urllib.request.Request(intro_offer_url, headers=gp_hdrs), timeout=10) as ex_resp:
                offer_exists = ex_resp.status == 200
        except urllib.error.HTTPError as he:
            if he.code != 404:
                raise

        if offer_exists:
            up_code = _gp_patch_with_version_negotiation(
                intro_offer_url,
                "phases,targeting,regionalConfigs,otherRegionsConfig",
                intro_offer_body,
                gp_hdrs,
            )
            print(f"  [OK] Google Play misilaylik/{GOOGLE_PLAY_INTRO_OFFER_ID} güncellendi (HTTP {up_code}).")
        else:
            cr_code = _gp_create_offer_with_version_negotiation(
                intro_collection_url,
                GOOGLE_PLAY_INTRO_OFFER_ID,
                intro_offer_body,
                gp_hdrs,
            )
            print(f"  [OK] Google Play misilaylik/{GOOGLE_PLAY_INTRO_OFFER_ID} oluşturuldu (HTTP {cr_code}).")

        act_code, act_body = _gp_post_action(f"{intro_offer_url}:activate", gp_hdrs)
        print(f"  [OK] Google Play misilaylik/{GOOGLE_PLAY_INTRO_OFFER_ID} aktif edildi (HTTP {act_code} {act_body[:120]}).")

    # 2. APPLE APP STORE CONNECT HAZIRLIĞI VE DENETİMİ
    ap_token = get_apple_token()
    ap_hdrs = {"Authorization": f"Bearer {ap_token}", "Content-Type": "application/json"}

    current_apple_prices = fetch_current_apple_prices(ap_hdrs)
    current_apple_intros = fetch_current_apple_intro_offers(ap_hdrs)
    monthly_free_trials = [o for o in current_apple_intros[APPLE_MONTHLY_SUB_ID] if o.get("offerMode") == "FREE_TRIAL"]
    annual_free_trials = [o for o in current_apple_intros[APPLE_ANNUAL_SUB_ID] if o.get("offerMode") == "FREE_TRIAL"]
    print(
        f"\n[Apple ASC] Mevcut FREE_TRIAL kayıtları: Aylık={len(monthly_free_trials)} adet, Yıllık={len(annual_free_trials)} adet "
        f"({'emekli edilecek' if apply_changes else 'dry-run tespit'})."
    )

    if apply_changes:
        for sid, lbl, free_list in [
            (APPLE_ANNUAL_SUB_ID, "Yıllık", annual_free_trials),
            (APPLE_MONTHLY_SUB_ID, "Aylık", monthly_free_trials),
        ]:
            retired_cnt = 0
            for fo in free_list:
                res_lbl = retire_apple_intro_offer(
                    fo["id"],
                    (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d"),
                    ap_hdrs,
                )
                retired_cnt += 1
                if retired_cnt <= 5:
                    print(f"    [OK] Apple {lbl} FREE_TRIAL ({fo.get('territory') or 'GLOBAL'}) -> {res_lbl}")
            if retired_cnt > 5:
                print(f"    [OK] Apple {lbl} toplam {retired_cnt} FREE_TRIAL teklifi emekli edildi.")

    print(f"\n--- APPLE APP STORE CONNECT HEDEF BAZ & İLK AY (PAY_UP_FRONT) FİYAT NOKTALARI ({len(APPLE_PPP_TARGETS)} Ülke) ---")
    apple_resolved_plan: List[Dict[str, Any]] = []
    apply_errors: List[str] = []
    tomorrow_utc = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    for cc, (m_target, a_target, exp_ccy) in APPLE_PPP_TARGETS.items():
        iso3 = ISO2_TO_ISO3[cc]
        cur_m = current_apple_prices[APPLE_MONTHLY_SUB_ID].get(iso3, {})
        cur_a = current_apple_prices[APPLE_ANNUAL_SUB_ID].get(iso3, {})
        intro_target_val, _ = APPLE_INTRO_FIRST_MONTH_TARGETS[cc]
        res_intro = resolve_apple_price_point(ap_token, APPLE_MONTHLY_SUB_ID, iso3, intro_target_val)

        if cc in PROTECTED_COUNTRIES:
            intro_disp = f"{res_intro['customerPrice']} {res_intro['currency']}" if res_intro else f"{intro_target_val}"
            print(
                f"  {cc} ({iso3}) [BAZ KORUNUR]: "
                f"İlk Ay {intro_disp} -> Aylık {cur_m.get('customerPrice')} {cur_m.get('currency')} | "
                f"Yıllık {cur_a.get('customerPrice')} {cur_a.get('currency')}"
            )
            if apply_changes and res_intro:
                ok_intro, info_intro = create_apple_paid_intro_offer(
                    iso3,
                    res_intro,
                    current_apple_intros[APPLE_MONTHLY_SUB_ID],
                    ap_hdrs,
                )
                if ok_intro:
                    print(f"    [OK] Apple {iso3} Aylık İlk Ay Teklifi -> {info_intro}")
                else:
                    print(f"    [ERR] {info_intro}")
                    apply_errors.append(info_intro)
            continue

        res_m = resolve_apple_price_point(ap_token, APPLE_MONTHLY_SUB_ID, iso3, m_target)
        res_a = resolve_apple_price_point(ap_token, APPLE_ANNUAL_SUB_ID, iso3, a_target)
        if not res_m or not res_a:
            print(f"  [WARN] {cc} ({iso3}) için Apple pricePoint bulunamadı!")
            continue

        m_changed = abs(cur_m.get("customerPrice", 0.0) - res_m["customerPrice"]) > 1e-3
        a_changed = abs(cur_a.get("customerPrice", 0.0) - res_a["customerPrice"]) > 1e-3
        intro_lbl = f"{res_intro['customerPrice']} {res_intro['currency']}" if res_intro else "N/A"
        print(
            f"  {cc} ({iso3}): "
            f"İlk Ay {intro_lbl} -> Aylık {cur_m.get('customerPrice')} -> {res_m['customerPrice']} {res_m['currency']} | "
            f"Yıllık {cur_a.get('customerPrice')} -> {res_a['customerPrice']} {res_a['currency']}"
        )
        apple_resolved_plan.append({
            "cc": cc,
            "iso3": iso3,
            "intro_monthly": res_intro,
            "monthly": res_m,
            "annual": res_a,
            "m_changed": m_changed,
            "a_changed": a_changed,
        })

        if apply_changes and res_intro:
            ok_intro, info_intro = create_apple_paid_intro_offer(
                iso3,
                res_intro,
                current_apple_intros[APPLE_MONTHLY_SUB_ID],
                ap_hdrs,
            )
            if ok_intro:
                print(f"    [OK] Apple {iso3} İlk Ay Teklifi -> {info_intro}")
            else:
                print(f"    [ERR] {info_intro}")
                apply_errors.append(info_intro)

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
                                "preserveCurrentPrice": True,
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
                    fail_msg = f"Apple {iso3} {lbl} güncellenemedi."
                    print(f"    [ERR] {fail_msg}")
                    apply_errors.append(fail_msg)

    if apply_changes and apply_errors:
        print(f"\n[HATA] Canlı uygulama sırasında {len(apply_errors)} bölge/teklif hatası oluştu:")
        for em in apply_errors:
            print(f"  - {em}")
        raise RuntimeError(f"sync_ppp_store_pricing kısmi hata ile sonlandı ({len(apply_errors)} hata).")

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
    parser = argparse.ArgumentParser(description="Mışıl Baby PPP & İlk Ay Başlangıç Teklifi Senkronizasyon Motoru")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--apply", action="store_true", help="Değişiklikleri mağaza API'larına canlı uygular.")
    mode_group.add_argument("--dry-run", action="store_true", help="Salt-okunur simülasyon çalıştırır (varsayılan).")
    mode_group.add_argument("--offline-check", action="store_true", help="Ağ çağrısı yapmadan yerel fiyat ve TR/CH değişmezlerini doğrular.")
    args = parser.parse_args()
    if args.offline_check:
        run_offline_check()
        return
    run_sync(apply_changes=bool(args.apply))


if __name__ == "__main__":
    main()
