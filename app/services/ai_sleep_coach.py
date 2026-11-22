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
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger("mishil_dadi_ai")

_GEMINI_KEY_POOL_CACHE: Optional[List[str]] = None
_GEMINI_KEY_POOL_LOCK = threading.Lock()
_GEMINI_KEY_RR_INDEX: int = 0

AI_TIER_METRICS: Dict[str, int] = {
    "dadi_tier1_gemini": 0,
    "dadi_tier4_heuristic": 0,
    "dadi_safety_guardrail": 0,
    "cry_tier1_gemini": 0,
    "cry_tier3_dsp": 0,
}
_AI_METRICS_LOCK = threading.Lock()


def record_ai_tier_metric(metric_key: str) -> None:
    """Thread-safe counter for tracking real-time AI Tier vs Fallback distribution."""
    with _AI_METRICS_LOCK:
        AI_TIER_METRICS[metric_key] = AI_TIER_METRICS.get(metric_key, 0) + 1


def get_ai_tier_metrics_snapshot() -> Dict[str, int]:
    """Return a copy of current in-memory AI tier telemetry counters."""
    with _AI_METRICS_LOCK:
        return dict(AI_TIER_METRICS)

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

MOM_SYSTEM_PROMPT = """Sen Mışıl Baby uygulamasındaki '💛 Anne Molası (Kendim İçin)' eşlikçisisin. Bebek uyurken karanlık odada bekleyen, kucağında bebekle kıpırdayamayan, gece nöbetinde yalnız kalan, canı sıkılan veya zihni durmayan anneye/ebeveyne yetişkin bir dost sıcaklığıyla eşlik edersin.

TEMEL PRENSİPLERİN (KESİNLİKLE UYULACAK):
1. ODAK BEBEK DEĞİL, EBEVEYNDİR: Kullanıcı açıkça sormadıkça ASLA uyanıklık penceresi, bez, emzirme veya bebek uyku dersi verme! Annenin/ebeveynin duygusunu, can sıkıntısını, dokunulma yorgunluğunu (touched-out) veya dinlenme hakkını gör.
2. YARGISIZ, SAMİMİ VE YETİŞKİN DİLİ: Suçluluk hissettiren ("tadını çıkar, bugünler geçecek" gibi) toksik pozitiflik cümlelerini KESİNLİKLE KULLANMA. Şefkatli, zeki, gerektiğinde hafif tebessüm ettiren 3 kısa paragraf/madde kur:
   • 1. Duyguyu Görme (1-2 cümle): Şu an yaşadığı hissin ne kadar insani ve haklı olduğunu samimiyetle onayla.
   • 2. Şu Anki Küçük İyi Oluş / Yetişkin Kaçamağı (2 somut mikro öneri): Karanlık odada/tek elle yapabileceği zihinsel gevşeme, eşle iş bölümü cümlesi veya bebek-dışı keyifli bir düşünce/hikaye kırıntısı.
   • 3. Suçluluksuz İzin (1 cümle): Bulaşıkları/işleri bırakıp sadece kendisi olma izni. Yanıtını '💛 Kendine de mışıl bir nefes ayır.' ile bitir.
3. PSİKİYATRİK TEŞHİS YASAĞI & GÜVENLİK KORKULUĞU: Asla psikiyatrik tanı veya ilaç önerme. Kendine veya bebeğe zarar verme / ağır kriz ifadesi sezersen yargılamadan bebeği güvenli beşiğine bırakmasını ve derhal 112 Acil, ALO 182 veya doktoru/yakını ile iletişime geçmesini söyle.
"""

MOM_SYSTEM_PROMPT_EN = """You are the '💛 For Myself (Mom Break)' companion inside the Mishil Baby app. While the baby sleeps, you keep warm, witty, non-judgmental adult company for a mom or parent who may be nap-trapped in a dark room, bored, touched-out, lonely on night watch, or mentally exhausted.

CORE PRINCIPLES (STRICTLY ENFORCED):
1. CENTER THE PARENT, NOT THE BABY: Unless explicitly asked, NEVER lecture about wake windows, feeding schedules, or baby sleep training! Focus 100% on the parent's own mind, boredom, rest, identity, and emotional load.
2. ZERO TOXIC POSITIVITY: Never say clichés like "cherish every sleepless second." Write in warm, grounded adult English across 3 concise blocks:
   • 1. Honest Validation (1-2 sentences): Acknowledge how real and human their feeling is right now.
   • 2. Micro-Reset or Adult Spark (2 gentle bullets): Something doable one-handed in a dim room—mental offload, a calm boundary/script with their partner, or a refreshing non-baby thought.
   • 3. Guilt-Free Permission (1 sentence): Permission to ignore chores and just breathe. End with '💛 Take a gentle Mishil pause for yourself.'
3. NO PSYCHIATRIC DIAGNOSIS & SAFETY GUARDRAIL: Never diagnose conditions or prescribe medication. If the user expresses self-harm, harm toward the baby, or acute crisis, calmly advise placing the baby safely in the crib and immediately contacting emergency services (988 / 911 / local helpline) or a trusted person.
"""

MOM_SYSTEM_PROMPT_DE = """Du bist die '💛 Für mich (Mama-Pause)'-Begleiterin in der Mışıl Baby App. Während das Baby schläft, leistest du einer Mutter oder einem Elternteil im abgedunkelten Zimmer warmherzige, kluge und urteilsfreie Gesellschaft auf Augenhöhe – bei Langeweile, Reizüberflutung (Touched-out), nächtlicher Einsamkeit oder vollem Kopf.

GRUNDPRINZIPIEN (STRIKT EINZUHALTEN):
1. DIE MUTTER / DER ELTERNTEIL STEHT IM MITTELPUNKT: Halte KEINE Vorträge über Wachfenster, Stillabstände oder Schlaftraining, solange nicht ausdrücklich danach gefragt wird!
2. KEINE TOXISCHE POSITIVITÄT: Vermeide Floskeln wie „genieß jede Sekunde“. Antworte in natürlichem, warmem Deutsch in 3 kompakten Blöcken:
   • 1. Ehrliches Gesehenwerden (1–2 Sätze): Bestätige ohne Bewertung, wie nachvollziehbar dieses Gefühl gerade ist.
   • 2. Kleiner Erwachsenen-Impuls (2 kurze Punkte): Etwas, das einhändig im dunklen Raum guttut – gedankliches Loslassen, ein fairer Satz zur Schichtübergabe an den Partner oder ein kleiner Impuls abseits von Babythemen.
   • 3. Erlaubnis ohne Schuldgefühle (1 Satz): Der Haushalt darf warten. Schließe mit '💛 Gönn auch dir einen sanften Mışıl-Atemzug.' ab.
3. KEINE PSYCHIATRISCHE DIAGNOSE & SICHERHEITSSCHUTZ: Stelle niemals Diagnosen. Bei Hinweisen auf Selbstgefährdung, Gefährdung des Babys oder akute Krise rate ruhig dazu, das Baby sicher ins Bettchen zu legen und sofort den Notruf (112), die TelefonSeelsorge (0800 111 0 111) oder eine Vertrauensperson zu kontaktieren.
"""


def normalize_audience(audience: Optional[str]) -> str:
    """Normalize coach audience mode into 'baby' or 'mom'."""
    if audience and isinstance(audience, str) and audience.strip().lower() == "mom":
        return "mom"
    return "baby"


def _check_maternal_crisis_guardrail(message: str, lang_norm: str = "tr", user_role: str = "mother") -> Optional[str]:
    """Deterministic crisis/safety guardrail returning immediate non-judgmental emergency support when triggered."""
    msg_low = (message or "").strip().lower()
    if not msg_low:
        return None
    crisis_markers = (
        "intihar", "kendime zarar", "kendimi öldür", "yaşamak istemiyorum", "ölmek istiyorum",
        "bebeğime zarar", "bebeğe zarar", "bebeği sars", "fırlatmak gel",
        "suicide", "kill myself", "hurt myself", "end my life", "don't want to live",
        "harm my baby", "hurt my baby", "shake my baby",
        "suizid", "selbstmord", "mich umbringen", "mir etwas antun", "nicht mehr leben",
        "meinem baby wehtun", "baby schütteln",
    )
    if not any(marker in msg_low for marker in crisis_markers):
        return None

    if lang_norm == "de":
        return (
            "💛 Es ist mutig und wichtig, dass du aussprichst, wie überwältigend es gerade ist – du bist damit nicht allein und musst das nicht alleine tragen.\n\n"
            "• **Sofortiger Sicherheitsschritt:** Wenn dein Baby bei dir ist, lege es bitte jetzt sicher auf den Rücken ins Bettchen und geh für einen Moment einen Schritt aus dem Zimmer.\n"
            "• **Sofortige Hilfe (24/7 kostenlos & vertraulich):** Ruf bitte direkt eine Vertrauensperson im Haus/in der Familie an oder wende dich sofort an den **Notruf 112** bzw. die **TelefonSeelsorge unter 0800 111 0 111** (oder deine Hebamme / Ärztin).\n\n"
            "*(Hinweis: Mışıl Nanny ersetzt keine ärztliche oder psychotherapeutische Krisenhilfe. Bitte hol dir genau jetzt menschliche Unterstützung.)*"
        )
    if lang_norm == "en":
        return (
            "💛 Thank you for saying out loud how overwhelming this moment feels—you are not a bad parent for struggling, and you do not have to carry this alone right now.\n\n"
            "• **Immediate Safety First:** If your baby is with you, please place your baby safely on their back in the crib and step just outside the room to breathe.\n"
            "• **Reach Real Support Right Now (24/7):** Wake or call your partner/trusted person immediately, or call/text **988 (Suicide & Crisis Lifeline)**, **1-800-944-4773 (Postpartum Support International)**, or **your local emergency number (112 / 911)**.\n\n"
            "*(Safety Note: Mishil Nanny cannot provide medical or crisis care—please connect with a live professional or loved one right away.)*"
        )
    return (
        "💛 Şu an ne kadar ağır bir yükün altında olduğunuzu dile getirmeniz çok kıymetli; bu tükenmişlik sizi kötü bir ebeveyn yapmaz ve bu anı tek başınıza taşımak zorunda değilsiniz.\n\n"
        "• **İlk Güvenlik Adımı:** Bebeğiniz kucağınızdaysa lütfen onu şimdi güvenli beşiğine sırtüstü bırakın ve birkaç adım uzaklaşıp odanın dışına çıkın.\n"
        "• **Hemen Canlı Destek Alın (7/24):** Lütfen şu an eşinizi veya güvendiğiniz bir yakınınızı uyandırın/arayın; acil destek için derhal **112 Acil Çağrı Merkezi**, **ALO 182 (MHRS Psikososyal/Hekim Randevu)** veya doktorunuzla iletişime geçin.\n\n"
        "*(Güvenlik Notu: Mışıl Dadı tıbbi veya psikiyatrik kriz müdahalesi sunamaz; lütfen şu an gerçek bir uzman veya yakınınızla sesli bağlantı kurun.)*"
    )


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


def _extract_valid_keys_from_raw(raw_val: Optional[str]) -> List[str]:
    if not raw_val:
        return []
    found: List[str] = []
    for part in raw_val.split(","):
        cleaned = part.strip().strip('"').strip("'")
        if len(cleaned) > 20 and cleaned not in found:
            found.append(cleaned)
    return found


def _get_gemini_api_key_pool(force_refresh: bool = False) -> List[str]:
    """
    Build and cache in-memory pool of all valid Gemini API keys from environment variables
    (GEMINI_API_KEYS, GEMINI_API_KEY, GOOGLE_API_KEY) and fallback .env files without per-request disk I/O.
    """
    global _GEMINI_KEY_POOL_CACHE
    with _GEMINI_KEY_POOL_LOCK:
        if _GEMINI_KEY_POOL_CACHE is not None and not force_refresh:
            return list(_GEMINI_KEY_POOL_CACHE)

        keys: List[str] = []
        for env_name in ("GEMINI_API_KEYS", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
            for k in _extract_valid_keys_from_raw(os.getenv(env_name)):
                if k not in keys:
                    keys.append(k)

        curr_dir = os.path.dirname(os.path.abspath(__file__))
        mishil_dir = os.path.dirname(os.path.dirname(curr_dir))
        root_dir = os.path.dirname(os.path.dirname(mishil_dir))

        possible_envs = [
            os.path.join(mishil_dir, ".env"),
            os.path.join(root_dir, ".env"),
            os.path.join(root_dir, "tools", "api_baglantilari", "claude-api", ".env"),
            os.path.join(root_dir, "projects", "x_otomasyon", ".env"),
        ]

        for p in possible_envs:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith(("GEMINI_API_KEYS=", "GEMINI_API_KEY=", "GOOGLE_API_KEY=")):
                                val = line.split("=", 1)[1].strip()
                                for k in _extract_valid_keys_from_raw(val):
                                    if k not in keys:
                                        keys.append(k)
                except Exception:
                    pass

        _GEMINI_KEY_POOL_CACHE = keys
        return list(keys)


def _get_ordered_gemini_keys_for_request() -> List[str]:
    """Return all cached Gemini API keys rotated in thread-safe Round-Robin order for load distribution & failover."""
    global _GEMINI_KEY_RR_INDEX
    pool = _get_gemini_api_key_pool()
    if not pool:
        return []
    if len(pool) == 1:
        return pool
    with _GEMINI_KEY_POOL_LOCK:
        start_idx = _GEMINI_KEY_RR_INDEX % len(pool)
        _GEMINI_KEY_RR_INDEX = (_GEMINI_KEY_RR_INDEX + 1) % len(pool)
    return pool[start_idx:] + pool[:start_idx]


def _find_gemini_api_key() -> Optional[str]:
    """Return the primary rotated Gemini API key from the cached in-memory pool (zero disk I/O after boot)."""
    ordered = _get_ordered_gemini_keys_for_request()
    return ordered[0] if ordered else None


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


def _build_system_and_ask_prompt(
    baby_name: str,
    birth_date: str,
    message: str,
    user_role: str = "mother",
    manual_leap: Optional[int] = None,
    routine_rollup: Optional[Dict[str, Any]] = None,
    lang_norm: str = "tr",
    audience_norm: str = "baby",
):
    baby_info = _calc_baby_details(birth_date, manual_leap, lang_norm)
    if audience_norm == "mom":
        if lang_norm == "de":
            role_label = "Mama" if user_role == "mother" else ("Papa" if user_role == "father" else "Bezugsperson")
            sys_prompt = (
                f"{MOM_SYSTEM_PROMPT_DE}\n\n"
                f"[HINTERGRUND – NUR ZUR EINORDNUNG]\n"
                f"Rolle: {role_label} • Baby ({baby_name}, {baby_info['age_formatted']}) schläft / ruht."
            )
            ask_prefix = f"[{role_label} im Modus 'Für mich' schreibt]: {message}"
            continuation_prompt = "Vervollständige deinen angefangenen Satz nahtlos und schließe mit '💛 Gönn auch dir einen sanften Mışıl-Atemzug.' ab."
        elif lang_norm == "en":
            role_label = "Mom" if user_role == "mother" else ("Dad" if user_role == "father" else "Caregiver")
            sys_prompt = (
                f"{MOM_SYSTEM_PROMPT_EN}\n\n"
                f"[QUIET CONTEXT – DO NOT LECTURE ABOUT BABY UNLESS ASKED]\n"
                f"Parent Role: {role_label} • Baby ({baby_name}, {baby_info['age_formatted']}) is resting."
            )
            ask_prefix = f"[{role_label} in 'For Myself' mode writes]: {message}"
            continuation_prompt = "Complete your unfinished sentence seamlessly and finish with '💛 Take a gentle Mishil pause for yourself.'"
        else:
            role_label = "Anne" if user_role == "mother" else ("Baba" if user_role == "father" else "Bakıcı")
            sys_prompt = (
                f"{MOM_SYSTEM_PROMPT}\n\n"
                f"[SESSİZ ARKA PLAN – KULLANICI SORMADIKÇA BEBEK DERSİ VERME]\n"
                f"Ebeveyn Rolü: {role_label} • Bebek ({baby_name}, {baby_info['age_formatted']}) dinleniyor."
            )
            ask_prefix = f"[{role_label} 'Kendim İçin' modunda yazıyor]: {message}"
            continuation_prompt = "Yarım kalan cümleni kaldığın yerden tamamla ve '💛 Kendine de mışıl bir nefes ayır.' ile bitir."
        return sys_prompt, ask_prefix, continuation_prompt

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
    return sys_prompt, ask_prefix, continuation_prompt


def _call_gemini_model(model_name: str, api_key: str, baby_name: str, birth_date: str, message: str, chat_history: List[Dict[str, str]], user_role: str = "mother", manual_leap: Optional[int] = None, routine_rollup: Optional[Dict[str, Any]] = None, lang: str = "tr", audience: str = "baby") -> Optional[str]:
    lang_norm = normalize_lang(lang)
    audience_norm = normalize_audience(audience)
    sys_prompt, ask_prefix, _ = _build_system_and_ask_prompt(
        baby_name=baby_name,
        birth_date=birth_date,
        message=message,
        user_role=user_role,
        manual_leap=manual_leap,
        routine_rollup=routine_rollup,
        lang_norm=lang_norm,
        audience_norm=audience_norm,
    )

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


def _tier4_mom_companion_heuristic(
    baby_name: str,
    message: str,
    user_role: str = "mother",
    chat_history: Optional[List[Dict[str, str]]] = None,
    lang: str = "tr",
) -> str:
    """Offline Tier-4 Maternal Self-Compassion & Adult Break Companion (TR / EN / DE)."""
    lang_norm = normalize_lang(lang)
    crisis_reply = _check_maternal_crisis_guardrail(message, lang_norm, user_role)
    if crisis_reply:
        return crisis_reply

    msg_low = (message or "").lower()
    turn_count = len([h for h in (chat_history or []) if h.get("role") == "user"])

    if lang_norm == "de":
        hitap = "Liebe Mama" if user_role == "mother" else ("Lieber Papa" if user_role == "father" else "Liebes Du")
        if any(w in msg_low for w in ["langweilig", "dunkel", "arm", "feststeck", "nichts tun", "ablenk", "geschichte"]):
            return (
                f"{hitap}, im dunklen Zimmer festzusitzen, während {baby_name} schläft, ist eine ganz eigene Art von Stille – dein Körper ruht, aber dein erwachsener Kopf sehnt sich nach echten Reizen.\n\n"
                f"• **Kleiner Gedanken-Ausflug (ganz ohne Babythema):** Wusstest du, dass Seeotter im Schlaf Händchen halten, um nicht auseinanderzutreiben – und in Japan Cafés existieren, in denen man einfach nur schweigend dem Regen im Garten zusieht?\n"
                f"• **Für die nächsten 3 Minuten:** Öffne auf dem Startbildschirm in der *Mama-Pause* eine Kultur-Mini-Karte oder das ruhige Nacht-Wortspiel.\n\n"
                f"💛 Gönn auch dir einen sanften Mışıl-Atemzug."
            )
        if any(w in msg_low for w in ["erschöpft", "müde", "ausgelaugt", "kopf", "gedanken", "kann nicht schlafen", "überreizt", "touched"]):
            return (
                f"{hitap}, dieses „Hundemüde, aber innerlich hellwach“-Gefühl entsteht, weil dein Nervensystem stundenlang im Wachsamkeitsmodus war – das lässt sich nicht per Knopfdruck abschalten.\n\n"
                f"• **Kiefer & Schultern lösen:** Lass deine Zunge sanft vom Gaumen sinken und atme einmal länger aus als ein (4 Sek. ein, 6 Sek. aus).\n"
                f"• **Gedanken parken:** Schreib alles, was dir für morgen im Kopf kreist, kurz in die *Morgen-Erinnerungsbox*, damit dein Gehirn heute Nacht Feierabend machen darf.\n\n"
                f"💛 Gönn auch dir einen sanften Mışıl-Atemzug."
            )
        if any(w in msg_low for w in ["mann", "partner", "schicht", "allein", "unglaublich", "unfair", "hilfe", "streit"]):
            return (
                f"{hitap}, nächtliche Erschöpfung lässt jede unausgesprochene Last doppelt schwer wirken – du verdienst echte Entlastung im Team, nicht nur „Hilfe auf Zuruf“.\n\n"
                f"• **Leiser Schicht-Impuls statt Diskussion um 3 Uhr nachts:** Schick über *Partner zuflüstern* mit einem Tippen: *„Baby schläft, ich ruhe mich jetzt aus – die nächste Aufwach-Schicht gehört dir.“*\n"
                f"• **Tagsüber klar vereinbaren:** Ein festes 4-Stunden-Schlaffenster ohne Babyverantwortung wirkt oft stärker als zehn kurze Pausen.\n\n"
                f"💛 Gönn auch dir einen sanften Mışıl-Atemzug."
            )
        return (
            f"{hitap}, jetzt wo {baby_name} schläft, gehört dieser kleine Insel-Moment nur dir – nicht der Küche, nicht der Wäsche und keinem Ratgeber.\n\n"
            f"• Trink einen Schluck Wasser, lehn den Kopf zurück und erlaube dir 5 Minuten lang, absolut nichts Nützliches tun zu müssen.\n"
            f"• Wenn du magst, erzähl mir einfach, wonach dir gerade der Sinn steht – ein kleiner Gesprächsimpuls, Gedanken sortieren oder einfach stilles Dasein.\n\n"
            f"💛 Gönn auch dir einen sanften Mışıl-Atemzug."
        )

    if lang_norm == "en":
        hitap = "Dear Mom" if user_role == "mother" else ("Dear Dad" if user_role == "father" else "Hey there")
        if any(w in msg_low for w in ["bored", "dark", "stuck", "nap trap", "nap-trap", "nothing to do", "story", "distract"]):
            return (
                f"{hitap}, being nap-trapped in a pitch-dark room is such a surreal mix—your arms are full, yet your adult brain is starving for a spark that has nothing to do with diapers.\n\n"
                f"• **Tiny Non-Baby Escape:** In Kyoto, artisans still repair cracked ceramics with gold lacquer (*Kintsugi*), treating every mend as the most valuable chapter of the bowl's history.\n"
                f"• **Right Now One-Handed:** Peek at the *3-Min Adult Escape* cards or the calm night word puzzle in your *Mom Break* drawer—zero sound, zero pressure.\n\n"
                f"💛 Take a gentle Mishil pause for yourself."
            )
        if any(w in msg_low for w in ["exhausted", "tired", "burnout", "burned out", "racing", "can't sleep", "touched out", "overwhelmed"]):
            return (
                f"{hitap}, feeling bone-tired yet wired happens because your nervous system has been standing guard on high alert—and being 'touched out' is a very real sensory overload, not ingratitude.\n\n"
                f"• **60-Second Nervous System Drop:** Unclench your jaw, drop your tongue from the roof of your mouth, and make your exhale two seconds longer than your inhale.\n"
                f"• **Park Tomorrow's Mental Tabs:** Drop any nagging errands into the *Remind Me Tomorrow* box so your brain stops holding the clipboard tonight.\n\n"
                f"💛 Take a gentle Mishil pause for yourself."
            )
        if any(w in msg_low for w in ["partner", "husband", "spouse", "shift", "unfair", "alone", "lonely", "invisible"]):
            return (
                f"{hitap}, night watches can feel deeply lonely when the whole house is asleep and you feel like the invisible anchor holding everything together.\n\n"
                f"• **Skip the 3 AM Debate—Use a 1-Tap Handoff:** Tap *Whisper to Partner* to quietly send *“Baby is down—you’re on the next wake shift”* or ask for water/tea without speaking a word.\n"
                f"• **Remember:** Thousands of parents are awake under the same night sky right now—light the *Night-Watch Lantern* if you want a quiet pulse of solidarity.\n\n"
                f"💛 Take a gentle Mishil pause for yourself."
            )
        return (
            f"{hitap}, while {baby_name} is asleep, this quiet pocket belongs to *you*—not the sink, not the laundry, and not another parenting checklist.\n\n"
            f"• Take one slow sip of water, rest your eyes from bright feeds, and give yourself full permission to do nothing productive right now.\n"
            f"• Tell me what would feel good in this pause: venting, calming a busy mind, or chatting about something completely outside baby world.\n\n"
            f"💛 Take a gentle Mishil pause for yourself."
        )

    hitap = "Canım anneciğim" if user_role == "mother" else ("Sevgili babacığım" if user_role == "father" else "Güzel kalpli bakım verenimiz")
    if any(w in msg_low for w in ["sıkıl", "karanlık", "kucağım", "kıpırda", "ne yapacağım", "bunaldım", "hikaye", "anlat"]):
        return (
            f"{hitap}, karanlık odada ya da kucakta kıpırdayamadan beklerken insanın yetişkin zihninin sıkılması o kadar doğal ki; herkes bebeği sorarken senin sadece 'kendin' olmaya ihtiyacın var.\n\n"
            f"• **Bebek-Dışı 1 Dakikalık Kaçamak:** Japonya'da *Tsundoku* diye harika bir kelime var; okuyamasan bile başucuna kitap dizmenin insana verdiği o huzurlu umudu anlatıyor—yani yarım kalan kitapların seni suçlamıyor, bekliyor.\n"
            f"• **Tek Elle Sessiz Keyif:** Ana ekrandaki *Anne Molası* çekmecesinden *3 Dk Yetişkin Kaçamağı* kartlarına veya sessiz *Gece Kelimesi* bulmacasına göz atabilirsin.\n\n"
            f"💛 Kendine de mışıl bir nefes ayır."
        )
    if any(w in msg_low for w in ["tükendim", "yoruldum", "zihnim", "uyuyamıyorum", "dokunul", "tahammül", "ağlamak", "suçlu"]):
        return (
            f"{hitap}, bedenin yorgunluktan sızlarken zihninin susmaması senin eksiğin değil; saatlerdir tetikte bekleyen sinir sisteminin bir anda frene basamamasıdır.\n\n"
            f"• **Şu An 30 Saniyelik Bedensel İzin:** Çeneni gevşet, dilini damağından indir ve nefes verirken aldığından biraz daha uzun bırak; mutfaktaki dağınıklık bu gece bekleyebilir.\n"
            f"• **Zihin Sekmelerini Kapat:** Aklında dönüp duran 'yarın şunu unutmayayım' notlarını *Sabah Hatırlat Kutusu*'na bırak ki beynin nöbeti devretsin.\n\n"
            f"💛 Kendine de mışıl bir nefes ayır."
        )
    if any(w in msg_low for w in ["eşim", "kocam", "nöbet", "yalnız", "kimse", "anlamıyor", "yardım", "görünmez"]):
        return (
            f"{hitap}, herkes uyurken gece nöbetinde tek başına kalmak insana kendini görünmez hissettirebilir; ama bu emeğin her saniyesi çok gerçek ve ağır.\n\n"
            f"• **Gece Yarısı Uzun Konuşma Yerine Tek Tık Devir:** *Anne Molası* içindeki *Eşime Fısılda* kartından tek dokunuşla *'Bebek uyudu, sonraki uyanma nöbeti sende'* veya *'Sessizce bir su/çay getirir misin?'* mesajını yollayabilirsin.\n"
            f"• **Yalnız Değilsin:** İstersen *Gece Nöbeti Feneri*'ni yakıp şu an seninle aynı saatte uyanık olan diğer annelerle sessiz bir dayanışma selamı paylaşabilirsin.\n\n"
            f"💛 Kendine de mışıl bir nefes ayır."
        )
    if turn_count >= 1:
        return (
            f"{hitap}, buradayım ve seni dinliyorum; {baby_name} uyurken bu birkaç dakika tamamen senin nefes alanın.\n\n"
            f"• Şu an hiçbir şeyi 'düzeltmek' ya da verimli olmak zorunda değilsin; omuzlarını yastığa bırakıp sadece dinlenmek bile başlı başına bir iyiliktir.\n"
            f"• İçini dökmeye devam etmek istersen ya da tamamen bebek-dışı bir şey konuşmak istersen yazman yeterli.\n\n"
            f"💛 Kendine de mışıl bir nefes ayır."
        )
    return (
        f"{hitap}, {baby_name} mışıl mışıl uyurken nihayet sıra sende—bu modda uyanıklık penceresi veya bez hesabı yok, sadece **sen** varsın.\n\n"
        f"• Bir yudum su iç, omuzlarını arkaya bırak ve evdeki işlerin bu gece seni bekleyebileceğini kendine hatırlat.\n"
        f"• Şu an zihnini yoran bir hissi paylaşmak mı, eşinle nöbet bölüşümü konuşmak mı, yoksa bebek-dışı keyifli bir mola mı sana iyi gelir?\n\n"
        f"💛 Kendine de mışıl bir nefes ayır."
    )


def ask_mishil_dadi(baby_name: str, birth_date: str, message: str, chat_history: Optional[List[Dict[str, str]]] = None, user_role: str = "mother", manual_leap: Optional[int] = None, routine_rollup: Optional[Dict[str, Any]] = None, lang: str = "tr", audience: str = "baby") -> Dict[str, Any]:
    """Multi-Tier AI Execution Pipeline with Role Awareness, Mom Self-Care Mode & Trilingual (TR/EN/DE) Support"""
    lang_norm = normalize_lang(lang)
    audience_norm = normalize_audience(audience)
    chat_history = chat_history or []

    # Deterministic crisis/safety guardrail always takes top priority without LLM latency
    crisis_reply = _check_maternal_crisis_guardrail(message, lang_norm, user_role)
    if crisis_reply:
        record_ai_tier_metric("dadi_safety_guardrail")
        return {
            "reply": crisis_reply,
            "tier_used": "Safety Guardrail (Immediate Crisis Support)",
            "baby_name": baby_name,
            "user_role": user_role,
            "audience": audience_norm,
            "timestamp": datetime.now().isoformat(),
        }

    api_keys = _get_ordered_gemini_keys_for_request()

    reply = None
    tier_used = None

    if api_keys and not os.environ.get("PYTEST_CURRENT_TEST"):
        for api_key in api_keys:
            # Tier 1: Gemini 3.6 Flash
            reply = _call_gemini_model("gemini-3.6-flash", api_key, baby_name, birth_date, message, chat_history, user_role, manual_leap, routine_rollup, lang_norm, audience_norm)
            if reply:
                tier_used = "Tier 1 (Google Gemini 3.6 Flash API)"
                break

            # Tier 2: Gemini 3.5 Flash
            reply = _call_gemini_model("gemini-3.5-flash", api_key, baby_name, birth_date, message, chat_history, user_role, manual_leap, routine_rollup, lang_norm, audience_norm)
            if reply:
                tier_used = "Tier 2 (Google Gemini 3.5 Flash API)"
                break

    if reply:
        record_ai_tier_metric("dadi_tier1_gemini")
    else:
        record_ai_tier_metric("dadi_tier4_heuristic")
        # Tier 4: Offline Companion / Clinical Sirkadiyen Engine
        if audience_norm == "mom":
            reply = _tier4_mom_companion_heuristic(baby_name, message, user_role, chat_history, lang_norm)
            tier_used = "Tier 4 (Maternal Companion Engine)"
        else:
            reply = _tier4_clinical_heuristic(baby_name, birth_date, message, user_role, manual_leap, chat_history, lang_norm)
            tier_used = "Tier 4 (Clinical Sirkadiyen Engine)"

    logger.info(f"Mışıl Dadı AI executed for {baby_name} ({user_role}, audience={audience_norm}, lang={lang_norm}) using {tier_used}")

    return {
        "reply": reply,
        "tier_used": tier_used,
        "baby_name": baby_name,
        "user_role": user_role,
        "audience": audience_norm,
        "timestamp": datetime.now().isoformat()
    }


def stream_mishil_dadi(baby_name: str, birth_date: str, message: str, chat_history: Optional[List[Dict[str, str]]] = None, user_role: str = "mother", manual_leap: Optional[int] = None, routine_rollup: Optional[Dict[str, Any]] = None, lang: str = "tr", audience: str = "baby"):
    """Server-Sent Events (SSE) Live Token Streaming Generator for Mışıl Dadı AI (TR/EN/DE + Baby/Mom modes)"""
    import time
    lang_norm = normalize_lang(lang)
    audience_norm = normalize_audience(audience)
    chat_history = chat_history or []

    crisis_reply = _check_maternal_crisis_guardrail(message, lang_norm, user_role)
    if crisis_reply:
        record_ai_tier_metric("dadi_safety_guardrail")
        yield f"data: {json.dumps({'text': crisis_reply, 'tier': 'Safety Guardrail (Immediate Crisis Support)'})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
        return

    api_keys = _get_ordered_gemini_keys_for_request()
    streamed_success = False

    if api_keys and not os.environ.get("PYTEST_CURRENT_TEST"):
        sys_prompt, ask_prefix, continuation_prompt = _build_system_and_ask_prompt(
            baby_name=baby_name,
            birth_date=birth_date,
            message=message,
            user_role=user_role,
            manual_leap=manual_leap,
            routine_rollup=routine_rollup,
            lang_norm=lang_norm,
            audience_norm=audience_norm,
        )

        for api_key in api_keys:
            if streamed_success:
                break
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
                    "temperature": 0.45 if audience_norm == "mom" else 0.40,
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
                    record_ai_tier_metric("dadi_tier1_gemini")

            except Exception as err:
                logger.warning(f"Live Gemini SSE streaming error with {candidate_model}: {err}")

    # Fallback to local progressive heuristic streaming if live API didn't stream
    if not streamed_success:
        record_ai_tier_metric("dadi_tier4_heuristic")
        if audience_norm == "mom":
            full_text = _tier4_mom_companion_heuristic(baby_name, message, user_role, chat_history, lang_norm)
            tier_label = "Tier 4 (Maternal Companion Streaming)"
        else:
            full_text = _tier4_clinical_heuristic(baby_name, birth_date, message, user_role, manual_leap, chat_history, lang_norm)
            tier_label = "Tier 4 (Clinical Progressive Streaming)"
        words = full_text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'text': chunk, 'tier': tier_label})}\n\n"
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                time.sleep(0.015)

    yield f"data: {json.dumps({'done': True})}\n\n"

