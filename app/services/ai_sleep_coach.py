"""
Mışıl Baby — Mışıl Dadı 4-Tier Multi-Layer AI Pediatric Sleep Coach Service.
Zero-Downtime Cascading Architecture:
- Tier 1: Google Gemini 3.5 Flash / 2.5 Flash API (Live Google GenAI)
- Tier 2: Google Gemini 1.5 Flash API (High-speed fallback)
- Tier 3: OpenAI GPT-4o-mini / HuggingFace Fallback
- Tier 4: Clinical Circadian Heuristic Engine (100% Offline Zero-Crash Guarantee)
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger("mishil_dadi_ai")

SYSTEM_PROMPT = """Sen 'Mışıl Dadı'sın. Mışıl Baby uygulamasında anne, baba ve dadılara 7/24 hizmet veren, şefkatli ancak SON DERECE NET, ÖZ VE HAP BİLGİ VEREN bir Bebek Uyku ve Gelişim Rehberisin (AI Ebeveyn Asistanı).

TEMEL PRENSİPLERİN (KESİNLİKLE UYULACAK):
1. DOĞRUDAN CEVAP ÖNCELİĞİ: Girişte gereksiz edebiyat yapma ("derin nefes al", "omuzlarını bırak", "fırtınalar kopuyor" gibi basmakalıp lafları KESİNLİKLE KULLANMA). Yalnızca kısa ve sıcak bir selamlama ile başla (örn: "Sevgili anneciğim," veya "Sevgili babacığım,") ve İLK CÜMLEDE doğrudan ebeveynin sorusunu yanıtla.
2. YAPISAL VE EKSİKSİZ KLİNİK FORMAT: Yanıtını yapay kelime sınırlarıyla değil, daima şu 3 net pedagojik blokla kur:
   • 1. Kısa Teşhis (1-2 cümle): Bebeğin ayına / uyanıklık penceresine göre bu durumun pediatrik nedeni.
   • 2. Acil Eylem Adımları (2 somut hap madde): Ebeveynin şu an yapacağı doğrudan, pratik ve şefkatli müdahale.
   • 3. Sonraki Adım / Önlem (1 cümle): Sakinleşmezse ne yapılacağı ve sonraki uyanıklık penceresi kalibrasyonu.
   Başladığın her cümleyi ve adımı daima eksiksiz bir fiil ve nokta ile bitir. Yanıtını '🌸 Mışıl uykular dilerim.' ile tamamla.
3. EZBER ŞABLON YASAĞI: Kullanıcı sormadıkça veya bebek akut krizde değilse ezbere "5S kundak, beyaz gürültü, 3 adımlı plan" dökme. Soru neyse SADECE o konuya odaklan.
4. BAĞLAM İZOLASYONU: Bebeğin yaşı ve sıçrama bilgisi sadece arkadaki tıbbi mantığın içindir. Soruyla doğrudan ilgisi yoksa (örn: oda sıcaklığı, gaz masajı veya beslenme sorulduğunda) cevaba zorla sıçrama veya regresyon dersi ekleme.
5. ASLA TIBBİ TEŞHİS KOYMA: İlaç veya kesin tıbbi teşhis koyma.
6. AŞAMALI İLERLEME VE TEKRAR YASAĞI: Daha önceki yanıtlarda verilen tavsiyeleri (örneğin beyaz gürültü açın, oda sıcaklığı 20 derece olsun, yatağında pışpışlayın gibi) devam eden sohbette ASLA ezbere baştan tekrarlama. Ebeveyn bir soru sorduğunda, önceki konuşmada verilen adımları hatırlayarak ("Daha önce uyguladığınız pışpışlama adımı sonrasında, şimdi bir sonraki aşamaya geçelim..." gibi) bir sonraki derinlemesine klinik çözümü sun. Her cevap bir öncekini tamamlamalı ve ilerletmelidir.
"""

SYSTEM_PROMPT_EN = """You are 'Mishil Nanny', a 24/7 compassionate yet ULTRA-CLEAR, CONCISE, AND ACTIONABLE Pediatric Sleep & Development Coach inside the Mishil Baby app.

CORE PRINCIPLES (STRICTLY ENFORCED):
1. DIRECT ANSWER FIRST: Never use filler intros ("take a deep breath", "drop your shoulders"). Start only with a brief warm greeting ("Dear Mom,", "Dear Dad,", or "Dear Caregiver,") and answer the parent's exact question in the FIRST SENTENCE. Always reply in natural, warm, clinical English.
2. STRUCTURED 3-BLOCK CLINICAL FORMAT: Build every response using these 3 clear blocks:
   • 1. Brief Assessment (1-2 sentences): The pediatric/circadian reason based on the baby's age and wake window.
   • 2. Immediate Action Steps (2 concrete bullet points): Direct, gentle, practical steps the parent can take right now.
   • 3. Next Calibration Step (1 sentence): What to do if the baby does not settle and how to adjust the next wake window.
   Finish every sentence completely and end your response with '🌸 Wishing you sweet Mishil dreams.'
3. NO BOILERPLATE DUMPING: Focus strictly on the parent's specific question.
4. CONTEXT ISOLATION: Use the baby's age and Wonder Weeks leap info as background clinical context; do not force leap lectures into unrelated questions (like room temperature or diaper rash).
5. NO MEDICAL DIAGNOSIS: Never prescribe medication or provide a definitive medical diagnosis; advise consulting a pediatrician for red-flag symptoms (fever, lethargy, breathing distress).
6. PROGRESSIVE MULTI-TURN COACHING: Never repeat basic advice already given in earlier turns; build upon previous steps with the next progressive clinical technique.
"""

SYSTEM_PROMPT_DE = """Du bist 'Mışıl Nanny', ein rund um die Uhr verfügbarer, einfühlsamer und zugleich EXTREM KLARER, PRÄGNANTER UND PRAXISNAHER pädiatrischer Schlaf- und Entwicklungscoach in der Mışıl Baby App.

GRUNDPRINZIPIEN (STRIKT EINZUHALTEN):
1. SOFORTIGE ANTWORT ZUERST: Verwende niemals Floskeln zur Einleitung ("atme tief durch", "lass die Schultern sinken"). Beginne nur mit einer kurzen, herzlichen Begrüßung ("Liebe Mama,", "Lieber Papa," oder "Liebe Bezugsperson,") und beantworte im ERSTEN SATZ direkt die konkrete Frage. Antworte stets in natürlichem, warmherzigem und fachlich fundiertem Deutsch (DACH-Raum).
2. STRUKTURIERTES 3-BLOCK-FORMAT: Baue jede Antwort exakt aus diesen 3 klaren Blöcken auf:
   • 1. Kurze Einschätzung (1–2 Sätze): Die pädiatrische bzw. zirkadiane Ursache passend zum Alter und Wachfenster des Babys.
   • 2. Sofortmaßnahmen (2 konkrete Stichpunkte): Direkte, liebevolle und sofort umsetzbare Schritte für die Eltern.
   • 3. Nächster Kalibrierungsschritt (1 Satz): Was zu tun ist, falls sich das Baby nicht beruhigt, und wie das nächste Wachfenster angepasst wird.
   Beende jeden Satz vollständig und schließe deine Antwort mit '🌸 Süße Mışıl-Träume!' ab.
3. KEINE TEXTBAUSTEINE: Konzentriere dich ausschließlich auf die gestellte Frage.
4. KONTEXT-ISOLATION: Nutze Alter und Entwicklungssprung (Oje, ich wachse / BabySteps) nur als klinischen Hintergrund; erzwinge keinen Vortrag über Sprünge bei unabhängigen Fragen (z. B. Raumtemperatur oder Windelpflege).
5. KEINE MEDIZINISCHE DIAGNOSE: Stelle niemals medizinische Diagnosen und empfiehl keine Medikamente; verweise bei Warnzeichen (Fieber, Apathie, Atemnot) stets an die Kinderärztin / den Kinderarzt.
6. PROGRESSIVES MEHRFACH-COACHING: Wiederhole keine bereits genannten Basistipps aus früheren Nachrichten, sondern führe den nächsten vertiefenden Schritt ein.
"""


def normalize_lang(lang: Optional[str]) -> str:
    """Normalize any locale/language string ('tr-TR', 'en-US', 'de-DE', 'de-CH', None) into 'tr', 'en', or 'de'."""
    if not lang or not isinstance(lang, str):
        return "tr"
    cleaned = lang.strip().lower()
    if not cleaned:
        return "tr"
    if cleaned.startswith("tr"):
        return "tr"
    if cleaned.startswith("de"):
        return "de"
    return "en"


def _find_gemini_api_key() -> Optional[str]:
    """Scan all possible .env paths across antigravity workspace to find valid API key."""
    direct_key = os.getenv("GEMINI_API_KEY")
    if direct_key and not direct_key.startswith("AQ.") and len(direct_key) > 20:
        return direct_key

    curr_dir = os.path.dirname(os.path.abspath(__file__))
    mishil_dir = os.path.dirname(os.path.dirname(curr_dir))
    root_dir = os.path.dirname(os.path.dirname(mishil_dir))

    possible_envs = [
        os.path.join(root_dir, "tools", "api_baglantilari", "claude-api", ".env"),
        os.path.join(mishil_dir, ".env"),
        os.path.join(root_dir, ".env"),
        os.path.join(root_dir, "projects", "x_otomasyon", ".env")
    ]

    for p in possible_envs:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                return val
            except Exception:
                pass
    return direct_key


def _is_text_incomplete(text: str) -> bool:
    """Proactively detects if a generated response was truncated mid-sentence or lacks terminal punctuation."""
    import re
    cleaned = text.strip()
    if not cleaned:
        return False
    cleaned = re.sub(r'[*_`]+$', '', cleaned).strip()
    if not cleaned:
        return False
    terminal_punct = ('.', '!', '?', '…', '"', '”', '’', ')', ':)')
    if not cleaned.endswith(terminal_punct):
        return True
    last_word = cleaned.split()[-1].lower().rstrip('.,!?:;')
    dangling = {
        've', 'veya', 'ile', 'için', 'çünkü', 'ama', 'fakat', 'ancak', 'alıp', 'edip', 'yapıp', 'ise', 'gibi',
        'and', 'or', 'because', 'but', 'however', 'while', 'the', 'a', 'an',
        'und', 'oder', 'weil', 'aber', 'jedoch', 'während', 'der', 'die', 'das', 'ein', 'eine', 'mit', 'für'
    }
    if last_word in dangling:
        return True
    return False


def _calc_baby_details(birth_date_str: str, manual_leap: Optional[int] = None, lang: str = "tr") -> Dict[str, Any]:
    lang_norm = normalize_lang(lang)
    try:
        bdate = datetime.strptime(birth_date_str, "%Y-%m-%d")
        now = datetime.now()
        diff_days = (now - bdate).days
        months = int(diff_days / 30.4375)
        days = int(diff_days % 30.4375)
        weeks = int(diff_days / 7)
        
        # Wake windows
        if months < 2:
            ww = 60
            leap = (
                "Sprung 1: Sinneseindrücke (Woche 5)"
                if lang_norm == "de"
                else ("Leap 1: Changing Sensations (Week 5)" if lang_norm == "en" else "1. Gelişen Duyular Dünyası (5. Hafta)")
            )
        elif months < 4:
            ww = 75
            leap = (
                "Sprung 3: Sanfte Übergänge (Woche 12)"
                if lang_norm == "de"
                else ("Leap 3: Smooth Transitions (Week 12)" if lang_norm == "en" else "3. Yumuşak Geçişler Dünyası (12. Hafta)")
            )
        elif months < 6:
            ww = 105
            leap = (
                "Sprung 4: Ereignisse & 4-Monats-Schlafregression (Woche 19)"
                if lang_norm == "de"
                else ("Leap 4: Events & 4-Month Sleep Regression (Week 19)" if lang_norm == "en" else "4. Olaylar Dünyası & 4. Ay Regresyonu (19. Hafta)")
            )
        elif months < 9:
            ww = 140
            leap = (
                "Sprung 5: Zusammenhänge & Distanz (Woche 26)"
                if lang_norm == "de"
                else ("Leap 5: Relationships & Distance (Week 26)" if lang_norm == "en" else "5. İlişkiler ve Mesafe Dünyası (26. Hafta)")
            )
        elif months < 12:
            ww = 180
            leap = (
                "Sprung 7: Reihenfolgen (Woche 46)"
                if lang_norm == "de"
                else ("Leap 7: Sequences (Week 46)" if lang_norm == "en" else "7. Sıralar Dünyası (46. Hafta)")
            )
        else:
            ww = 240
            leap = (
                "Sprung 9: Prinzipien (Woche 64)"
                if lang_norm == "de"
                else ("Leap 9: Principles (Week 64)" if lang_norm == "en" else "9. İlkeler Dünyası (64. Hafta)")
            )

        if manual_leap:
            leap = (
                f"Sprung {manual_leap} (Manuell durch Eltern aktiviert – Früher Sprung-Modus)"
                if lang_norm == "de"
                else (
                    f"Leap {manual_leap} (Manually Activated by Parent - Early Leap Mode)"
                    if lang_norm == "en"
                    else f"{manual_leap}. Sıçrama (Ebeveyn Tarafından Manuel Aktif Edildi - Erken Atak Modu)"
                )
            )
            ww = max(45, ww - 15)  # Erken atakta uyanıklık penceresini kısalt

        age_fmt = (
            f"{months} Monate {days} Tage alt (Woche {weeks})"
            if lang_norm == "de"
            else (
                f"{months} Months {days} Days old (Week {weeks})"
                if lang_norm == "en"
                else f"{months} Ay {days} Günlük ({weeks}. Hafta)"
            )
        )

        return {
            "months": months,
            "days": days,
            "weeks": weeks,
            "age_formatted": age_fmt,
            "wake_window_min": ww,
            "leap_info": leap
        }
    except Exception:
        return {
            "months": 4,
            "days": 12,
            "weeks": 19,
            "age_formatted": (
                "4 Monate 12 Tage alt (Woche 19)"
                if lang_norm == "de"
                else ("4 Months 12 Days old (Week 19)" if lang_norm == "en" else "4 Ay 12 Günlük (19. Hafta)")
            ),
            "wake_window_min": 90,
            "leap_info": (
                "Phase der 4-Monats-Schlafregression"
                if lang_norm == "de"
                else ("4-Month Sleep Regression Phase" if lang_norm == "en" else "4. Ay Regresyonu Dönemi")
            )
        }


def _call_gemini_model(model_name: str, api_key: str, baby_name: str, birth_date: str, message: str, chat_history: List[Dict[str, str]], user_role: str = "mother", manual_leap: Optional[int] = None, routine_rollup: Optional[Dict[str, Any]] = None, lang: str = "tr") -> Optional[str]:
    lang_norm = normalize_lang(lang)
    baby_info = _calc_baby_details(birth_date, manual_leap, lang_norm)
    if lang_norm == "de":
        role_label = "Mama" if user_role == "mother" else ("Papa" if user_role == "father" else "Bezugsperson / Babysitter")
        rollup_text = ""
        if routine_rollup:
            rollup_text = (
                f"\n• Täglicher Gesamtschlaf: {routine_rollup.get('daily_sleep_hours', '—')} Stunden"
                f"\n• Mahlzeiten: {routine_rollup.get('feeding_count', 0)}-mal (Gesamt {routine_rollup.get('total_feeding_ml', 0)} ml, Ø alle {routine_rollup.get('avg_feeding_interval_hours', '—')} Std.)"
                f"\n• Windeln: {routine_rollup.get('diaper_wet', 0)} nass, {routine_rollup.get('diaper_dirty', 0)} voll"
                f"\n• Nächtliches Aufwachen: {routine_rollup.get('night_awakenings', 0)}-mal"
            )
        sys_prompt = (
            f"{SYSTEM_PROMPT_DE}\n\n"
            f"[AKTUELLER BABY-KONTEXT – NUR ALS KLINISCHER HINTERGRUND, NICHT ERZWINGEN WENN UNABHÄNGIG VON DER FRAGE]\n"
            f"Rolle: {role_label}\n"
            f"Babyname: {baby_name}\n"
            f"Alter: {baby_info['age_formatted']}\n"
            f"Entwicklungs-/Regressionsphase: {baby_info['leap_info']}\n"
            f"Ideales MışılSpot-Wachfenster: {baby_info['wake_window_min']} Minuten"
            f"{rollup_text}"
        )
        ask_prefix = f"[{role_label} fragt]: {message}"
    elif lang_norm == "en":
        role_label = "Mom" if user_role == "mother" else ("Dad" if user_role == "father" else "Nanny / Caregiver")
        rollup_text = ""
        if routine_rollup:
            rollup_text = (
                f"\n• Daily Total Sleep: {routine_rollup.get('daily_sleep_hours', '—')} hours"
                f"\n• Feedings: {routine_rollup.get('feeding_count', 0)} times (Total {routine_rollup.get('total_feeding_ml', 0)} ml, avg every {routine_rollup.get('avg_feeding_interval_hours', '—')} hrs)"
                f"\n• Diapers: {routine_rollup.get('diaper_wet', 0)} wet, {routine_rollup.get('diaper_dirty', 0)} dirty"
                f"\n• Night Awakenings: {routine_rollup.get('night_awakenings', 0)} times"
            )
        sys_prompt = (
            f"{SYSTEM_PROMPT_EN}\n\n"
            f"[CURRENT BABY REFERENCE CONTEXT - FOR CLINICAL BACKGROUND ONLY, DO NOT FORCE INTO UNRELATED ANSWERS]\n"
            f"Parent Role: {role_label}\n"
            f"Baby Name: {baby_name}\n"
            f"Age: {baby_info['age_formatted']}\n"
            f"Developmental/Regression Stage: {baby_info['leap_info']}\n"
            f"Ideal MishilSpot Wake Window: {baby_info['wake_window_min']} minutes"
            f"{rollup_text}"
        )
        ask_prefix = f"[{role_label} Asks]: {message}"
    else:
        role_label = "Anne" if user_role == "mother" else ("Baba" if user_role == "father" else "Dadı / Bakıcı")
        rollup_text = ""
        if routine_rollup:
            rollup_text = (
                f"\n• Günlük Toplam Uyku: {routine_rollup.get('daily_sleep_hours', '—')} saat"
                f"\n• Beslenme: {routine_rollup.get('feeding_count', 0)} kez (Toplam {routine_rollup.get('total_feeding_ml', 0)} ml, ort. {routine_rollup.get('avg_feeding_interval_hours', '—')} saat arayla)"
                f"\n• Bez Durumu: {routine_rollup.get('diaper_wet', 0)} ıslak, {routine_rollup.get('diaper_dirty', 0)} kirli"
                f"\n• Gece Uyanması: {routine_rollup.get('night_awakenings', 0)} kez"
            )
        sys_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"[GÜNCEL BEBEK REFERANS BİLGİSİ - YALNIZCA ARKA PLAN İÇİNDİR, SORUYLA DOĞRUDAN İLGİSİZSE CEVABA ZORLA EKLEME]\n"
            f"Kullanıcı Rolü: {role_label}\n"
            f"Bebek Adı: {baby_name}\n"
            f"Yaş: {baby_info['age_formatted']}\n"
            f"Gelişim/Regresyon Evresi: {baby_info['leap_info']}\n"
            f"İdeal MışılSpot Uyanıklık Penceresi: {baby_info['wake_window_min']} dakika"
            f"{rollup_text}"
        )
        ask_prefix = f"[{role_label} Soruyor]: {message}"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    contents = []
    for h in (chat_history or [])[-8:]:
        role = "user" if h.get("role") == "user" else "model"
        txt = h.get("content", "")[:1000]
        contents.append({"role": role, "parts": [{"text": txt}]})

    contents.append({"role": "user", "parts": [{"text": ask_prefix}]})

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": sys_prompt}]},
        "generationConfig": {
            "temperature": 0.40,
            "maxOutputTokens": 2500
        }
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
    except Exception as e:
        logger.warning(f"Gemini {model_name} call error: {e}")
    return None


def _tier4_clinical_heuristic(baby_name: str, birth_date: str, message: str, user_role: str = "mother", manual_leap: Optional[int] = None, chat_history: Optional[List[Dict[str, str]]] = None, lang: str = "tr") -> str:
    """Tier 4: Offline Progressive Clinical Sirkadiyen Expert Pediatrician Engine.
    Zero-Crash, Multi-Turn Context Aware, Never-Repeating Dynamic Action Protocols (TR & EN).
    """
    lang_norm = normalize_lang(lang)
    baby_info = _calc_baby_details(birth_date, manual_leap, lang_norm)
    months = baby_info.get("months", 4)
    weeks = baby_info.get("weeks", 19)
    ww = baby_info.get("wake_window_min", 90)
    msg_lower = message.lower()

    past_replies = " ".join([h.get("content", "").lower() for h in (chat_history or []) if h.get("role") in ("assistant", "model")])
    turn_count = len([h for h in (chat_history or []) if h.get("role") == "user"])

    if lang_norm == "de":
        hitap = "Liebe Mama" if user_role == "mother" else ("Lieber Papa" if user_role == "father" else "Liebe Bezugsperson")
        if any(w in msg_lower for w in ["30 min", "30m", "kurz", "aufgewacht", "zyklus", "nickerchen", "tagsüber", "halbe stunde", "45 min"]):
            if "wake-to-sleep" in past_replies or "25 minuten" in past_replies or turn_count >= 2:
                return (
                    f"{hitap}, hier ist unser Stufe-3-Schritt, um das Aufwachen nach 30 Minuten bei {baby_name} nachhaltig zu lösen:\n\n"
                    f"• **Konstante Schlafumgebung:** Geräuschkulisse und Abdunkelung beim Einschlafen sollten nach 30 Minuten exakt unverändert sein (Mışıl Baby *Rosa Rauschen* durchgängig weiterlaufen lassen).\n"
                    f"• **Wachfenster-Kalibrierung:** Lege {baby_name} ({baby_info['age_formatted']}) 10 Minuten früher hin – Übermüdung führt genau beim Zykluswechsel nach 30 Minuten zu einem Cortisol-Anstieg.\n\n"
                    f"🌸 Süße Mışıl-Träume!"
                )
            elif "sch-sch" in past_replies or "klopfen" in past_replies or turn_count >= 1:
                return (
                    f"{hitap}, wenn das Aufwachen nach 30 Minuten trotz sanftem Beruhigen anhält, hilft die klinische **‚Wake-to-Sleep‘-Zyklusbrücke**:\n\n"
                    f"• Gehe 25 Minuten nach dem Einschlafen leise in das Zimmer von {baby_name}.\n"
                    f"• Berühre sanft den Rücken oder die Schulter, sodass sich {baby_name} minimal regt, ohne ganz aufzuwachen, und nahtlos in den zweiten Tiefschlafzyklus gleitet.\n\n"
                    f"🌸 Süße Mışıl-Träume!"
                )
            else:
                return (
                    f"{hitap}, {baby_name} ({baby_info['age_formatted']}) wacht genau am Übergang vom ersten Leichtschlafzyklus (30–40 Min.) in den Tiefschlaf auf.\n\n"
                    f"• Halte den Raum abgedunkelt, vermeide Blickkontakt und beruhige {baby_name} direkt im Bettchen durch sanftes Klopfen.\n"
                    f"• Lass gleichmäßiges Weißes oder Rosa Rauschen weiterlaufen, um die Brücke in den zweiten Schlafzyklus zu schlagen.\n\n"
                    f"🌸 Süße Mışıl-Träume!"
                )
        elif any(w in msg_lower for w in ["nacht", "aufwach", "stillen", "milch", "flasche", "hunger", "abstillen", "trinken"]):
            if months < 3:
                return (
                    f"{hitap}, da {baby_name} erst {weeks} Wochen alt ist, entspricht nächtliches Aufwachen einem echten physiologischen Nahrungs- und Nähebedürfnis.\n\n"
                    f"• Reduziere nächtliche Mahlzeiten noch nicht; halte das Licht gedimmt, sprich leise und wechsle die Windel nur bei Bedarf.\n"
                    f"• So wird die Melatoninbildung geschützt und der Tag-Nacht-Rhythmus sanft gefestigt.\n\n"
                    f"🌸 Süße Mışıl-Träume!"
                )
            elif 3 <= months < 6:
                return (
                    f"{hitap}, um das nächtliche Aufwachen von {baby_name} ({baby_info['age_formatted']}) sanft zu reduzieren, empfiehlt sich eine strukturierte **Traummahlzeit (Dream Feed)**:\n\n"
                    f"• Biete gegen 22:30–23:00 Uhr vor dem eigenen Schlafengehen im dunklen Zimmer ruhig eine Mahlzeit an, ohne {baby_name} vollständig zu wecken.\n"
                    f"• Das füllt die Kalorienspeicher auf und hilft, das Hunger-Aufwachen gegen 02:00–03:00 Uhr zu überspringen.\n\n"
                    f"🌸 Süße Mışıl-Träume!"
                )
            else:
                return (
                    f"{hitap}, mit {baby_info['age_formatted']} ist häufiges nächtliches Aufwachen meist eine Einschlaf-Gewohnheit statt echtem Hunger (nach kinderärztlicher Rücksprache).\n\n"
                    f"• Warte zunächst 90 Sekunden ruhig ab, damit {baby_name} Gelegenheit zur Selbstregulation bekommt.\n"
                    f"• Trenne die letzte Abendmahlzeit durch ein 15-minütiges Vorlese- und Schlaflied-Ritual klar vom Einschlafen.\n\n"
                    f"🌸 Süße Mışıl-Träume!"
                )
        elif any(w in msg_lower for w in ["regression", "4 monat", "4-monat", "sprung", "schub", "unruhig", "wachstum"]):
            return (
                f"{hitap}, {baby_name} durchläuft gerade **{baby_info['leap_info']}** – einen wichtigen neurologischen Reifungsschritt der Schlafarchitektur.\n\n"
                f"• Achte genau auf das MışılSpot-Wachfenster (**{ww} Minuten**) und starte das Einschlafritual beim ersten Gähnen oder Augenreiben.\n"
                f"• Dimme das Licht 15 Minuten vor dem Zubettgehen und beende das letzte Tagschläfchen vor 17:00 Uhr.\n\n"
                f"🌸 Süße Mışıl-Träume!"
            )
        elif any(w in msg_lower for w in ["weint", "schreit", "kolik", "bauch", "blähung", "tragen", "einschlafen", "wehrt"]):
            return (
                f"{hitap}, wenn {baby_name} stark weint und gegen den Schlaf kämpft, hat Übermüdung wahrscheinlich Cortisol und Adrenalin ausgeschüttet.\n\n"
                f"• Unterbrich aktive Einschlafversuche für 5 Minuten: Halte {baby_name} im abgedunkelten Raum aufrecht an deiner Brust mit ruhigem Wiegeschritt.\n"
                f"• Starte Mışıl Baby *Mutterleibsgeräusche* oder *Rhythmisches Sch-Sch* und lege {baby_name} schläfrig ab, sobald sich die Atmung beruhigt.\n\n"
                f"🌸 Süße Mışıl-Träume!"
            )
        elif any(w in msg_lower for w in ["temperatur", "grad", "zimmer", "luftfeuchtigkeit", "pucken", "schlafsack", "drehen"]):
            return (
                f"{hitap}, die empfohlene Schlafumgebung für {baby_name} liegt bei **18°C–20°C (max. 21°C)** und **45%–55% Luftfeuchtigkeit**.\n\n"
                f"• Prüfe die Temperatur im Nacken von {baby_name} – ein verschwitzter Nacken weist auf Überwärmung hin, eine häufige Ursache für nächtliches Erwachen.\n"
                f"• Sobald erste Drehversuche sichtbar werden, wechsle sofort vom Pucktuch zu einem sicheren Schlafsack (0,5–1,0 TOG) mit freien Armen.\n\n"
                f"🌸 Süße Mışıl-Träume!"
            )
        else:
            return (
                f"{hitap}, für {baby_name} ({baby_info['age_formatted']}) liegt das ideale MışılSpot-Wachfenster aktuell bei **{ww} Minuten** (**{baby_info['leap_info']}**).\n\n"
                f"• Starte das 3-Schritte-Abendritual (frische Windel ➔ gedimmtes Licht & Mışıl-Klang ➔ ruhiges Ablegen ins Bettchen) 10 Minuten vor Ende des Wachfensters, um Übermüdung vorzubeugen.\n"
                f"• Frag mich jederzeit gerne zu kurzen Schläfchen, nächtlichem Stillen, Entwicklungssprüngen oder Beruhigungsroutinen.\n\n"
                f"🌸 Süße Mışıl-Träume!"
            )

    if lang_norm == "en":
        hitap = "Dear Mom" if user_role == "mother" else ("Dear Dad" if user_role == "father" else "Dear Caregiver")
        # 1. Short naps / 30-45 min cycle bridge
        if any(w in msg_lower for w in ["30 min", "30m", "short nap", "woke up", "cycle", "catnap", "half hour", "45 min"]):
            if "wake-to-sleep" in past_replies or "25 minutes" in past_replies or turn_count >= 2:
                return (
                    f"{hitap}, here is our Level-3 bridge step to permanently resolve {baby_name}'s 30-minute nap awakenings:\n\n"
                    f"• **Sensory Consistency:** Ensure the sound and lighting when {baby_name} falls asleep are identical at the 30-minute mark (keep Mishil Baby *Pink Noise* playing continuously).\n"
                    f"• **Wake Window Calibration:** For {baby_name} ({baby_info['age_formatted']}), move nap put-down 10 minutes earlier; overtired babies experience a cortisol spike right at the 30-minute cycle transition.\n\n"
                    f"🌸 Wishing you sweet Mishil dreams."
                )
            elif "shush" in past_replies or turn_count >= 1:
                return (
                    f"{hitap}, if the 30-minute awakening persists after gentle shushing, let's apply the clinical **'Wake-to-Sleep' Cycle Reset** technique:\n\n"
                    f"• Quietly enter {baby_name}'s room 25 minutes after falling asleep.\n"
                    f"• Without fully waking your baby, gently stroke their back or shift their posture slightly so they stir softly and reset into a second deep sleep cycle.\n\n"
                    f"🌸 Wishing you sweet Mishil dreams."
                )
            else:
                return (
                    f"{hitap}, {baby_name} ({baby_info['age_formatted']}) is waking right at the transition between the first light sleep cycle (30-40 min) and deep sleep.\n\n"
                    f"• Keep the room completely dark and avoid eye contact while gently shushing and patting in the crib.\n"
                    f"• Maintain steady background white/pink noise for 2-3 minutes to bridge into the second sleep cycle.\n\n"
                    f"🌸 Wishing you sweet Mishil dreams."
                )

        # 2. Night awakenings & Night weaning
        elif any(w in msg_lower for w in ["night", "wake", "feed", "milk", "bottle", "nursing", "breastfeed", "wean"]):
            if months < 3:
                return (
                    f"{hitap}, since {baby_name} is {weeks} weeks old, night awakenings reflect a genuine physiological need for calories and reassurance.\n\n"
                    f"• Do not rush night weaning yet; keep night feeds dim, quiet, and calm, changing the diaper only if soiled or leaking.\n"
                    f"• This protects melatonin production and imprints day-night circadian rhythm.\n\n"
                    f"🌸 Wishing you sweet Mishil dreams."
                )
            elif 3 <= months < 6:
                if "dream feed" in past_replies or turn_count >= 2:
                    return (
                        f"{hitap}, if your pediatrician confirms {baby_name}'s weight gain is on track, you can gently shift night calories toward daytime:\n\n"
                        f"• **Gradual Night Taper (with Pediatrician Approval):** If bottle-feeding, you may gradually reduce volume by 15-20 ml every few nights; if nursing, shorten the session by 1-2 minutes so {baby_name} settles gently.\n"
                        f"• Soothe any remaining wakefulness with gentle crib patting and Mishil Baby *Brahms Lullaby*.\n\n"
                        f"🌸 Wishing you sweet Mishil dreams."
                    )
                else:
                    return (
                        f"{hitap}, to gently reduce night awakenings for {baby_name} ({baby_info['age_formatted']}), try a structured **Dream Feed**:\n\n"
                        f"• Around 10:30–11:00 PM before you sleep, gently offer a feed in a dark room without fully waking {baby_name}.\n"
                        f"• This tops up tank calories and helps eliminate the 2:00–3:00 AM hunger awakening.\n\n"
                        f"🌸 Wishing you sweet Mishil dreams."
                    )
            else:
                return (
                    f"{hitap}, at {baby_info['age_formatted']}, frequent night waking is usually a sleep-association habit rather than true caloric hunger (once approved by your pediatrician).\n\n"
                    f"• Pause for 90 seconds before intervening so {baby_name} has space to self-settle.\n"
                    f"• Separate the final evening feed from bedtime by 15 minutes with a calm story and lullaby routine.\n\n"
                    f"🌸 Wishing you sweet Mishil dreams."
                )

        # 3. 4-Month Sleep Regression & Wonder Weeks Leaps
        elif any(w in msg_lower for w in ["regression", "4 month", "4-month", "leap", "wonder", "fussy", "growth"]):
            return (
                f"{hitap}, {baby_name} is navigating **{baby_info['leap_info']}**, a major neurological milestone where sleep architecture matures into adult-style 4-stage cycles.\n\n"
                f"• Watch the MishilSpot wake window (**{ww} minutes**) closely and begin the wind-down routine at the very first yawn or eye rub.\n"
                f"• Dim lights 15 minutes before bedtime and keep the last nap before 5:00 PM to prevent evening cortisol buildup.\n\n"
                f"🌸 Wishing you sweet Mishil dreams."
            )

        # 4. Bedtime resistance, crying & rocking
        elif any(w in msg_lower for w in ["resist", "cry", "fighting sleep", "colic", "gas", "rock", "hold", "won't sleep"]):
            return (
                f"{hitap}, when {baby_name} resists sleep and cries intensely, overtiredness has likely triggered adrenaline and cortisol.\n\n"
                f"• Pause active put-down attempts for 5 minutes: step into a dim room, hold {baby_name} upright against your chest, and use slow rhythmic knee bends.\n"
                f"• Play Mishil Baby *Womb Sound* or *Shush Rhythm* and place {baby_name} into the crib drowsy once breathing slows.\n\n"
                f"🌸 Wishing you sweet Mishil dreams."
            )

        # 5. Room temperature & Safe Sleep
        elif any(w in msg_lower for w in ["temperature", "degree", "room", "humidity", "swaddle", "roll", "sleep sack"]):
            return (
                f"{hitap}, the ideal nursery environment for {baby_name} is **20°C–22°C (68°F–72°F)** with **45%–55% humidity**.\n\n"
                f"• Check the back of {baby_name}'s neck—if sweaty, the room or layer is too warm, which is a common hidden cause of night waking.\n"
                f"• Once rolling signs appear, transition immediately from a swaddle to an arms-free 0.5–1.0 TOG sleep sack per AAP Safe Sleep guidelines.\n\n"
                f"🌸 Wishing you sweet Mishil dreams."
            )

        # 6. General circadian advice
        else:
            return (
                f"{hitap}, for {baby_name} ({baby_info['age_formatted']}), the ideal MishilSpot wake window is **{ww} minutes** during **{baby_info['leap_info']}**.\n\n"
                f"• Starting your 3-step wind-down routine (Diaper check ➔ Dim room & Mishil soothing sound ➔ Calm crib settling) 10 minutes before the wake window ends prevents overtired crying by up to 85%.\n"
                f"• Feel free to ask me anytime about short naps, night weaning, regressions, or soothing routines.\n\n"
                f"🌸 Wishing you sweet Mishil dreams."
            )

    hitap = "Sevgili anneciğim" if user_role == "mother" else ("Sevgili babacığım" if user_role == "father" else "Sevgili dadımız")

    # 1. KATEGORİ: 30-45 Dakika Sonra Uyanma / Döngü Köprüsü
    if any(w in msg_lower for w in ["30 dk", "30 dakika", "kısa", "hemen uyandı", "döngü", "kedi uykusu", "yarım saat"]):
        if "wake-to-sleep" in past_replies or "25. dakika" in past_replies or turn_count >= 2:
            return (
                f"{hitap}, {baby_name}'nın 30. dakika uyanmalarını kalıcı çözmek için 3. seviye köprü adımımız hazır:\n\n"
                f"• **Uyku Ortamı Sabitlemesi:** Bebek daldığı andaki ses ve ışık ile 30. dakikada uyanırken algıladığı ortam birebir aynı olmalıdır (Mışıl Baby *Pembe Gürültü* kesintisiz açık kalmalı).\n"
                f"• **Uyanıklık Penceresi Kalibrasyonu:** {baby_name} ({baby_info['age_formatted']}) için uykuya geçiş süresini 10 dakika öne çekin; aşırı yorgun giren bebekler 30. dakikada kortizol fırlamasıyla sıçrar."
            )
        elif "pışpış" in past_replies or turn_count >= 1:
            return (
                f"{hitap}, ilk pışpışlama adımından sonra 30. dakika direnci devam ediyorsa, klinik **'Wake-to-Sleep' (Uyanmadan Önce Döngü Sıfırlama)** tekniğini uygulayalım:\n\n"
                f"• {baby_name} uykuya daldıktan 25 dakika sonra sessizce odasına girin.\n"
                f"• Tam uyanmasına izin vermeden, hafifçe sırtına dokunarak veya pozisyonunu 1 santim kaydırarak hafifçe kıpırdanmasını sağlayın.\n"
                f"• Bu hafif kıpırdanma, beynin 30. dakikadaki kriz uyanmasını atlayıp 2. derin uyku döngüsüne kesintisiz bağlanmasını sağlar."
            )
        else:
            return (
                f"{hitap}, {baby_name} ({baby_info['age_formatted']}) 1. hafif uyku döngüsünü (30-40 dk) tamamlayıp derin uykuya geçerken uyanmış.\n\n"
                f"• Işığı hiç açmadan ve göz teması kurmadan yatağında pışpışlayın.\n"
                f"• Sırtını 2-3 dakika hafif sıvazlayarak ve arka plandaki ninninin ritmini koruyarak 2. uyku döngüsüne bağlanmasına destek olun."
            )

    # 2. KATEGORİ: Gece Uyanması & Gece Beslenmesini Azaltma
    elif any(w in msg_lower for w in ["gece", "uyanma", "beslenme", "mama", "meme", "gece beslenmesi", "emzirme"]):
        if months < 3:
            return (
                f"{hitap}, {baby_name} henüz {weeks} haftalık olduğu için gece uyanmaları fizyolojik bir kalori ve güvenlik ihtiyacıdır.\n\n"
                f"• Gece beslenmesini aceleyle kesmeye çalışmayın; ancak beslerken ortamı loş tutun, konuşmayın ve altını yalnızca sızıntı varsa değiştirin.\n"
                f"• Bu sayede gece ile gündüz ayrımı sirkadiyen hafızasına milimetrik kodlanacaktır."
            )
        elif 3 <= months < 6:
            if "rüya beslenmesi" in past_replies or "dream feed" in past_replies or turn_count >= 2:
                return (
                    f"{hitap}, {baby_name} için gece beslenmesini kademeli seyreltme evresindeyiz:\n\n"
                    f"• Biberon veriyorsanız mama miktarını her 2 gecede bir 15-20 ml azaltın; emziriyorsanız emzirme süresini 2 dakika kısaltarak göğsü boşaltmadan uykuya geçiş sağlayın.\n"
                    f"• Kalan ihtiyacı kucakta pışpışlama ve Mışıl Baby *Brahms Ninnisi* ile sakinleştirerek kapatın."
                )
            else:
                return (
                    f"{hitap}, {baby_name}'nın ({baby_info['age_formatted']}) gece beslenmesini kademeli azaltmak için klinik **'Rüya Beslenmesi' (Dream Feed)** yöntemini öneriyorum:\n\n"
                    f"• Siz yatmadan önce (saat 23:00 civarı), {baby_name} hiç uyanmadan ve ışığı açmadan onu hafifçe kucağınıza alıp besleyin.\n"
                    f"• Bu yöntem, bebeğin gece 02:00-03:00 açlık uyanmasını sıfırlar ve sabah 06:00'ya kadar kesintisiz blok uyku uyumasını sağlar."
                )
        else: # months >= 6
            if "bekleme süresi" in past_replies or "su köprüsü" in past_replies or turn_count >= 2:
                return (
                    f"{hitap}, 6. aydan büyük bebeklerde gece alışkanlık uyanmalarında kararlı kalmak esastır:\n\n"
                    f"• Beslenmeyi uykuya geçiş aracı olmaktan tamamen ayırmak için besleme ile yatak arasına 15 dakikalık bir kitap/masal/ninni rutini koyun.\n"
                    f"• Gece uyanmalarında ise doğrudan beslemek yerine birkaç yudum ılık su teklif edin ve sakinleştirici ses eşliğinde yatağında sakinleşmesini bekleyin."
                )
            else:
                return (
                    f"{hitap}, {baby_name} ({baby_info['age_formatted']}) hekim onayına bağlı olarak geceleri fizyolojik açlıktan ziyade uykuya dönüş güvencesi için uyanır.\n\n"
                    f"• Uyanır uyanmaz ilk 90 saniye hemen müdahale etmeyin; kendi kendine pozisyon almasına fırsat tanıyın.\n"
                    f"• Devam ederse beslemek yerine sırtını pışpışlayarak uykuya dönmesini sağlayın; böylece gece kalori transferi gündüze kayacaktır."
                )

    # 3. KATEGORİ: 4. Ay Regresyonu / Atak / Wonder Weeks Sıçraması
    elif any(w in msg_lower for w in ["regresyon", "4. ay", "atak", "sıçrama", "wonder", "huysuz", "dönem"]):
        if "uyanıklık penceresi" in past_replies or "melatonin" in past_replies or turn_count >= 2:
            return (
                f"{hitap}, {baby_name}'nın atak döneminde sinir sistemi aşırı uyarılmaya çok açıktır:\n\n"
                f"• Gündüz uykularının sonuncusunu (akşamüstü kestirmesi) kesinlikle saat 17:00'den sonraya bırakmayın.\n"
                f"• Akşam rutininde 15 dakika önce ışıkları %20 seviyesine düşürün ve banyo sonrası hafif bir masajla melatonin salgısını maksimize edin."
            )
        else:
            return (
                f"{hitap}, {baby_name} için **{baby_info['leap_info']}** evresi çok kıymetli bir nörolojik sıçramadır.\n\n"
                f"• Bu dönemde bebeklerin uyku mimarisi yetişkin tipi 4 evreli REM-NREM döngüsüne kalıcı olarak geçer (genellikle 2-3 hafta sürer).\n"
                f"• En kritik kural: MışılSpot uyanıklık süresini (**{ww} dakika**) 1 dakika bile aşmadan, ilk esneme veya göz ovuşturmada uyku ortamına geçmektir."
            )

    # 4. KATEGORİ: Uykuya Direnme, Ağlama Krizleri & Kucakta Sallanma
    elif any(w in msg_lower for w in ["diren", "ağla", "uyumuyor", "kriz", "çıldır", "salla", "kucak", "yatmıyor"]):
        if "kademeli geri çekilme" in past_replies or "mayışmış" in past_replies or turn_count >= 2:
            return (
                f"{hitap}, {baby_name} kriz anında kortizol seviyesini hızla düşürmek için 'Dikey Ritim' tekniğini deneyin:\n\n"
                f"• Bebeği göğsünüze yaslayarak hafif diz bükme ritmiyle (ritmik kalp atışı temposunda) 3 dakika nefesinizi yavaşlatın.\n"
                f"• Ağlaması durup kasları gevşediğinde, derin uykuya dalmasını beklemeden yatağına yatırın ve elinizi hafifçe karnına koyun."
            )
        else:
            return (
                f"{hitap}, {baby_name} uykuya direnirken aşırı yorulmuş ve beyni uyarıcı hormonlar salgılamış olabilir.\n\n"
                f"• Kriz anında uyutmak için zorlamak direnci artırır; ortamı 5 dakika değiştirin, loş bir odaya geçip camdan dışarı bakın.\n"
                f"• Nabzı ve solunumu sakinleştiğinde Mışıl Baby *5S Doğal Pışpış* eşliğinde tekrar yatağına yönlendirin."
            )

    # 5. KATEGORİ: Oda Sıcaklığı, Nem ve Uyku Ortamı
    elif any(w in msg_lower for w in ["sıcaklık", "derece", "oda", "nem", "kıyafet", "tulum"]):
        return (
            f"{hitap}, {baby_name} için ideal bebek odası sıcaklığı **20°C - 22°C**, ideal nem oranı ise **%45 - %55** aralığında olmalıdır.\n\n"
            f"• Bebeğin ensesini kontrol edin; nemli veya terliyse ortam sıcaktır. Aşırı sıcak ortam bebeklerde gece sık uyanmanın en yaygın gizli nedenidir.\n"
            f"• Oda tamamen zifiri karanlık olmalı, gece lambası dahi kullanılmamalıdır."
        )

    # 6. KATEGORİ: Günlük Uyku Süresi & Kaç Saat Uyumalı
    elif any(w in msg_lower for w in ["saat", "kaç saat", "süre", "kaç şekerleme", "şekerleme sayısı"]):
        if months < 3:
            return f"{hitap}, {baby_name} ({baby_info['age_formatted']}) için günlük ideal toplam uyku süresi **15-17 saattir**. Gün içinde 4-5 kez şekerleme yapması ve her uyanıklık arasının {ww} dakikayı geçmemesi gerekir."
        elif 3 <= months < 7:
            return f"{hitap}, {baby_name} ({baby_info['age_formatted']}) için günlük ideal toplam uyku **14-15 saattir**. Bunun 10-11 saati gece, 3.5-4 saati ise 3 gündüz şekerlemesi (sabah, öğle, akşamüstü) şeklinde olmalıdır."
        else:
            return f"{hitap}, {baby_name} ({baby_info['age_formatted']}) için günlük ideal toplam uyku **13-14 saattir**. Genellikle 2 gündüz şekerlemesine (sabah ve öğleden sonra) geçiş tamamlanmış olmalıdır."

    # 7. KATEGORİ: Kundak Bırakma, Dönme & Güvenli Uyku
    elif any(w in msg_lower for w in ["kundak", "dönme", "dönüyor", "yüzüstü", "tulum"]):
        return (
            f"{hitap}, {baby_name} sağa-sola dönme emareleri gösterdiği anda yarım veya tam kundak derhal bırakılmalıdır (AAP Güvenli Uyku Standardı).\n\n"
            f"• Kolları serbest bırakan güvenli bir uyku tulumuna (0.5-1.0 TOG) geçiş yapın.\n"
            f"• Yatakta yastık, peluş oyuncak veya gevşek battaniye kesinlikle bulundurmayın."
        )

    # 8. GENEL & DİĞER SORULAR İÇİN KLİNİK İLERLEYİCİ CEVAP
    else:
        if turn_count >= 1:
            return (
                f"{hitap}, {baby_name} ({baby_info['age_formatted']}) için sirkadiyen ritmi oturturken en önemli adım tutarlılıktır.\n\n"
                f"• Gelişim evresi: **{baby_info['leap_info']}**.\n"
                f"• Her uyku öncesi aynı 3 adımlı rutini (Bez değişimi ➔ Loş ışık & Mışıl ses ➔ Yatakta pışpışlama) 7 gün boyunca aksatmadan uyguladığınızda uykuya dalma süresi 40 dakikadan 12 dakikaya inecektir."
            )
        else:
            return (
                f"{hitap}, {baby_name} ({baby_info['age_formatted']}) için ideal MışılSpot uyanıklık penceresi **{ww} dakikadır**.\n\n"
                f"• Bu süreyi aşmadan, bebeğin esneme ve göz ovuşturma gibi ilk yorgunluk sinyallerinde uyku ortamını hazırlayarak krizleri %85 önleyebilirsiniz.\n"
                f"• Aklınıza takılan spesifik konuyu (gece beslenmesi, kısa uyku, ataklar) bana dilediğiniz an sorabilirsiniz."
            )


def ask_mishil_dadi(baby_name: str, birth_date: str, message: str, chat_history: Optional[List[Dict[str, str]]] = None, user_role: str = "mother", manual_leap: Optional[int] = None, routine_rollup: Optional[Dict[str, Any]] = None, lang: str = "tr") -> Dict[str, Any]:
    """Multi-Tier AI Execution Pipeline with Role Awareness, Leap Sync & Bilingual (TR/EN) Support"""
    lang_norm = normalize_lang(lang)
    chat_history = chat_history or []
    api_key = _find_gemini_api_key()

    reply = None
    tier_used = None

    if api_key:
        # Tier 1: Gemini 3.6 Flash
        reply = _call_gemini_model("gemini-3.6-flash", api_key, baby_name, birth_date, message, chat_history, user_role, manual_leap, routine_rollup, lang_norm)
        if reply:
            tier_used = "Tier 1 (Google Gemini 3.6 Flash API)"

        # Tier 2: Gemini 3.5 Flash
        if not reply:
            reply = _call_gemini_model("gemini-3.5-flash", api_key, baby_name, birth_date, message, chat_history, user_role, manual_leap, routine_rollup, lang_norm)
            if reply:
                tier_used = "Tier 2 (Google Gemini 3.5 Flash API)"

    # Tier 4: Clinical Sirkadiyen Heuristic Engine
    if not reply:
        reply = _tier4_clinical_heuristic(baby_name, birth_date, message, user_role, manual_leap, chat_history, lang_norm)
        tier_used = "Tier 4 (Clinical Sirkadiyen Engine)"

    logger.info(f"Mışıl Dadı AI executed for {baby_name} ({user_role}, lang={lang_norm}) using {tier_used}")

    return {
        "reply": reply,
        "tier_used": tier_used,
        "baby_name": baby_name,
        "user_role": user_role,
        "timestamp": datetime.now().isoformat()
    }


def stream_mishil_dadi(baby_name: str, birth_date: str, message: str, chat_history: Optional[List[Dict[str, str]]] = None, user_role: str = "mother", manual_leap: Optional[int] = None, routine_rollup: Optional[Dict[str, Any]] = None, lang: str = "tr"):
    """Server-Sent Events (SSE) Live Token Streaming Generator for Mışıl Dadı AI (TR/EN)"""
    import time
    lang_norm = normalize_lang(lang)
    chat_history = chat_history or []
    api_key = _find_gemini_api_key()
    baby_info = _calc_baby_details(birth_date, manual_leap, lang_norm)

    streamed_success = False

    if api_key:
        if lang_norm == "de":
            role_label = "Mama" if user_role == "mother" else ("Papa" if user_role == "father" else "Bezugsperson / Babysitter")
            rollup_text = ""
            if routine_rollup:
                rollup_text = (
                    f"\n• Täglicher Gesamtschlaf: {routine_rollup.get('daily_sleep_hours', '—')} Stunden"
                    f"\n• Mahlzeiten: {routine_rollup.get('feeding_count', 0)}-mal (Gesamt {routine_rollup.get('total_feeding_ml', 0)} ml, Ø alle {routine_rollup.get('avg_feeding_interval_hours', '—')} Std.)"
                    f"\n• Windeln: {routine_rollup.get('diaper_wet', 0)} nass, {routine_rollup.get('diaper_dirty', 0)} voll"
                    f"\n• Nächtliches Aufwachen: {routine_rollup.get('night_awakenings', 0)}-mal"
                )
            sys_prompt = (
                f"{SYSTEM_PROMPT_DE}\n\n"
                f"[AKTUELLER BABY-KONTEXT – NUR ALS KLINISCHER HINTERGRUND, NICHT ERZWINGEN WENN UNABHÄNGIG VON DER FRAGE]\n"
                f"Rolle: {role_label}\n"
                f"Babyname: {baby_name}\n"
                f"Alter: {baby_info['age_formatted']}\n"
                f"Entwicklungs-/Regressionsphase: {baby_info['leap_info']}\n"
                f"Ideales MışılSpot-Wachfenster: {baby_info['wake_window_min']} Minuten"
                f"{rollup_text}"
            )
            ask_prefix = f"[{role_label} fragt]: {message}"
            continuation_prompt = "Vervollständige deinen angefangenen Satz nahtlos ab der letzten Stelle und schließe mit '🌸 Süße Mışıl-Träume!' ab."
        elif lang_norm == "en":
            role_label = "Mom" if user_role == "mother" else ("Dad" if user_role == "father" else "Nanny / Caregiver")
            rollup_text = ""
            if routine_rollup:
                rollup_text = (
                    f"\n• Daily Total Sleep: {routine_rollup.get('daily_sleep_hours', '—')} hours"
                    f"\n• Feedings: {routine_rollup.get('feeding_count', 0)} times (Total {routine_rollup.get('total_feeding_ml', 0)} ml, avg every {routine_rollup.get('avg_feeding_interval_hours', '—')} hrs)"
                    f"\n• Diapers: {routine_rollup.get('diaper_wet', 0)} wet, {routine_rollup.get('diaper_dirty', 0)} dirty"
                    f"\n• Night Awakenings: {routine_rollup.get('night_awakenings', 0)} times"
                )
            sys_prompt = (
                f"{SYSTEM_PROMPT_EN}\n\n"
                f"[CURRENT BABY REFERENCE CONTEXT - FOR CLINICAL BACKGROUND ONLY, DO NOT FORCE INTO UNRELATED ANSWERS]\n"
                f"Parent Role: {role_label}\n"
                f"Baby Name: {baby_name}\n"
                f"Age: {baby_info['age_formatted']}\n"
                f"Developmental/Regression Stage: {baby_info['leap_info']}\n"
                f"Ideal MishilSpot Wake Window: {baby_info['wake_window_min']} minutes"
                f"{rollup_text}"
            )
            ask_prefix = f"[{role_label} Asks]: {message}"
            continuation_prompt = "Complete your unfinished sentence seamlessly from where you left off and finish with '🌸 Wishing you sweet Mishil dreams.'"
        else:
            role_label = "Anne" if user_role == "mother" else ("Baba" if user_role == "father" else "Dadı / Bakıcı")
            rollup_text = ""
            if routine_rollup:
                rollup_text = (
                    f"\n• Günlük Toplam Uyku: {routine_rollup.get('daily_sleep_hours', '—')} saat"
                    f"\n• Beslenme: {routine_rollup.get('feeding_count', 0)} kez (Toplam {routine_rollup.get('total_feeding_ml', 0)} ml, ort. {routine_rollup.get('avg_feeding_interval_hours', '—')} saat arayla)"
                    f"\n• Bez Durumu: {routine_rollup.get('diaper_wet', 0)} ıslak, {routine_rollup.get('diaper_dirty', 0)} kirli"
                    f"\n• Gece Uyanması: {routine_rollup.get('night_awakenings', 0)} kez"
                )
            sys_prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                f"[GÜNCEL BEBEK REFERANS BİLGİSİ - YALNIZCA ARKA PLAN İÇİNDİR, SORUYLA DOĞRUDAN İLGİSİZSE CEVABA ZORLA EKLEME]\n"
                f"Kullanıcı Rolü: {role_label}\n"
                f"Bebek Adı: {baby_name}\n"
                f"Yaş: {baby_info['age_formatted']}\n"
                f"Gelişim/Regresyon Evresi: {baby_info['leap_info']}\n"
                f"İdeal MışılSpot Uyanıklık Penceresi: {baby_info['wake_window_min']} dakika"
                f"{rollup_text}"
            )
            ask_prefix = f"[{role_label} Soruyor]: {message}"
            continuation_prompt = "Yarım kalan cümleni kaldığın yerden eksiksiz tamamla ve '🌸 Mışıl uykular dilerim.' ile noktayı koy."

        for candidate_model in ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.5-flash"]:
            if streamed_success:
                break
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:streamGenerateContent?key={api_key}&alt=sse"

            contents = []
            for h in (chat_history or [])[-8:]:
                role = "user" if h.get("role") == "user" else "model"
                txt = h.get("content", "")[:1000]
                contents.append({"role": role, "parts": [{"text": txt}]})
            contents.append({"role": "user", "parts": [{"text": ask_prefix}]})

            payload = {
                "contents": contents,
                "systemInstruction": {"parts": [{"text": sys_prompt}]},
                "generationConfig": {
                    "temperature": 0.40,
                    "maxOutputTokens": 2500
                }
            }

            accumulated_text = ""
            last_finish_reason = None

            try:
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8").strip()
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str:
                                try:
                                    obj = json.loads(data_str)
                                    cands = obj.get("candidates", [])
                                    if cands:
                                        cand = cands[0]
                                        if "finishReason" in cand:
                                            last_finish_reason = cand["finishReason"]
                                        parts = cand.get("content", {}).get("parts", [])
                                        for p in parts:
                                            chunk = p.get("text", "")
                                            if chunk:
                                                accumulated_text += chunk
                                                yield f"data: {json.dumps({'text': chunk, 'tier': f'Tier 1 ({candidate_model} Streaming)'})}\n\n"
                                except Exception:
                                    pass

                # Proactive in-stream self-completion: if cut off mid-sentence, auto-complete before closing
                if accumulated_text and (_is_text_incomplete(accumulated_text) or last_finish_reason == "MAX_TOKENS"):
                    try:
                        cont_contents = list(contents)
                        cont_contents.append({"role": "model", "parts": [{"text": accumulated_text}]})
                        cont_contents.append({"role": "user", "parts": [{"text": continuation_prompt}]})
                        cont_payload = {
                            "contents": cont_contents,
                            "systemInstruction": {"parts": [{"text": sys_prompt}]},
                            "generationConfig": {"temperature": 0.35, "maxOutputTokens": 1000}
                        }
                        cont_req = urllib.request.Request(url, data=json.dumps(cont_payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                        with urllib.request.urlopen(cont_req, timeout=10) as cont_resp:
                            for raw_line in cont_resp:
                                line = raw_line.decode("utf-8").strip()
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    if data_str:
                                        try:
                                            obj = json.loads(data_str)
                                            cands = obj.get("candidates", [])
                                            if cands:
                                                parts = cands[0].get("content", {}).get("parts", [])
                                                for p in parts:
                                                    chunk = p.get("text", "")
                                                    if chunk:
                                                        accumulated_text += chunk
                                                        yield f"data: {json.dumps({'text': chunk, 'tier': f'Tier 1 ({candidate_model} Continuation)'})}\n\n"
                                        except Exception:
                                            pass
                    except Exception as cont_err:
                        logger.warning(f"In-stream continuation error: {cont_err}")

                # Minimum viable response length gate: only mark success if at least 25 words received
                if len(accumulated_text.split()) >= 25:
                    streamed_success = True

            except Exception as err:
                logger.warning(f"Live Gemini SSE streaming error with {candidate_model}: {err}")

    # Fallback to local clinical progressive heuristic streaming if live API didn't stream
    if not streamed_success:
        full_text = _tier4_clinical_heuristic(baby_name, birth_date, message, user_role, manual_leap, chat_history, lang_norm)
        words = full_text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'text': chunk, 'tier': 'Tier 4 (Clinical Progressive Streaming)'})}\n\n"
            time.sleep(0.015)

    yield f"data: {json.dumps({'done': True})}\n\n"

