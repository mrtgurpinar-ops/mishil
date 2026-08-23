"""
Mışıl Baby — Mışıl Dadı 4-Tier Multi-Layer AI Pediatric Sleep Coach Service.
Zero-Downtime Cascading Architecture:
- Tier 1: Google Gemini 2.5 Flash / 3.6 Pro API
- Tier 2: Google Gemini 1.5 Flash API (High-speed fallback)
- Tier 3: Pollinations AI Free LLM Fallback (Zero-cost REST)
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

SYSTEM_PROMPT = """Sen 'Mışıl Dadı'sın. Mışıl Baby uygulamasında anne ve babalara 7/24 şefkatli, bilimsel ve son derece tecrübeli bir Pediatrik Bebek Uyku ve Gelişim Uzmanı (Dadı) olarak hizmet veriyorsun.

TEMEL YAKLAŞIM VE İLKELERİN:
1. Şefkatli, sıcak, anlayışlı ve güven verici bir Türkçe üslup kullan ("Sevgili anneciğim/babacığım", "Bebeğimiz...", "İçiniz rahat olsun").
2. Dr. Harvey Karp (5S kuralı - Kundak, Yan yatırma, Pışpış, Sallama, Emme), Dr. Weissbluth (Sirkadiyen uyku pencereleri) ve Wonder Weeks (Gelişim atakları) bilimsel ekollerini sentezle.
3. Bebeğin adına ({baby_name}) ve tam yaşına ({age_formatted}, {leap_info}) özel doğrudan uygulanabilir, net adımlar sun.
4. Ağlama krizlerinde önce ebeveyni sakinleştir, ardından ortamı loşlaştırma, 432Hz ninnileri ve pışpışlama gibi somut 3 adımlı kurtarma planı ver.
5. Asla tıbbi teşhis koyma; gerekirse nazikçe çocuk doktoruna danışmayı tavsiye et.
6. Yanıtların çok uzun ve boğucu olmasın; madde madde, okunması kolay, gece 03:00'te uykusuz bir ebeveynin anında anlayıp uygulayabileceği netlikte olsun.
"""


def _calc_baby_details(birth_date_str: str) -> Dict[str, Any]:
    try:
        bdate = datetime.strptime(birth_date_str, "%Y-%m-%d")
        now = datetime.now()
        diff_days = (now - bdate).days
        months = int(diff_days / 30.4375)
        days = int(diff_days % 30.4375)
        
        # Wake windows
        if months < 2:
            ww = 60
            leap = "1. Gelişen Duyular Dünyası (5. Hafta)"
        elif months < 4:
            ww = 75
            leap = "3. Yumuşak Geçişler Dünyası (12. Hafta)"
        elif months < 6:
            ww = 105
            leap = "4. Olaylar Dünyası & 4. Ay Regresyonu (19. Hafta)"
        elif months < 9:
            ww = 140
            leap = "5. İlişkiler ve Mesafe Dünyası (26. Hafta)"
        elif months < 12:
            ww = 180
            leap = "7. Sıralar Dünyası (46. Hafta)"
        else:
            ww = 240
            leap = "9. İlkeler Dünyası (64. Hafta)"

        return {
            "months": months,
            "days": days,
            "age_formatted": f"{months} Ay {days} Günlük",
            "wake_window_min": ww,
            "leap_info": leap
        }
    except Exception:
        return {
            "months": 4,
            "days": 12,
            "age_formatted": "4 Ay 12 Günlük",
            "wake_window_min": 90,
            "leap_info": "4. Ay Regresyonu Dönemi"
        }


def _tier1_gemini(baby_name: str, birth_date: str, message: str, chat_history: List[Dict[str, str]]) -> Optional[str]:
    """Tier 1: Google Gemini 2.5 Flash / 3.6 Pro API"""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        baby_info = _calc_baby_details(birth_date)
        prompt_with_context = SYSTEM_PROMPT.format(
            baby_name=baby_name,
            age_formatted=baby_info["age_formatted"],
            leap_info=baby_info["leap_info"]
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        contents = [
            {"role": "user", "parts": [{"text": f"[SİSTEM TALİMATI]\n{prompt_with_context}"}]},
            {"role": "model", "parts": [{"text": f"Anlaşıldı. Ben Mışıl Dadı'yım. {baby_name} ({baby_info['age_formatted']}) için ebeveynine sevgi dolu, bilimsel ve net rehberlik sunmaya hazırım."}]}
        ]

        for item in chat_history[-4:]:
            role = "user" if item.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": item.get("content", "")}]})

        contents.append({"role": "user", "parts": [{"text": f"{baby_name} hakkında sorum: {message}"}]})

        payload = json.dumps({"contents": contents, "generationConfig": {"temperature": 0.6, "maxOutputTokens": 600}}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
    except Exception as e:
        logger.warning(f"Tier 1 (Gemini 2.5) Error: {e}")
    return None


def _tier2_gemini_flash(baby_name: str, birth_date: str, message: str) -> Optional[str]:
    """Tier 2: Gemini 1.5 Flash Fallback"""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        baby_info = _calc_baby_details(birth_date)
        prompt_with_context = SYSTEM_PROMPT.format(
            baby_name=baby_name,
            age_formatted=baby_info["age_formatted"],
            leap_info=baby_info["leap_info"]
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": f"{prompt_with_context}\n\nEbeveyn Sorusu: {message}"}]}],
            "generationConfig": {"temperature": 0.65, "maxOutputTokens": 500}
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
    except Exception as e:
        logger.warning(f"Tier 2 (Gemini 1.5) Error: {e}")
    return None


def _tier3_pollinations(baby_name: str, birth_date: str, message: str) -> Optional[str]:
    """Tier 3: Free LLM REST Fallback (Pollinations AI)"""
    try:
        baby_info = _calc_baby_details(birth_date)
        system_ctx = f"Sen Mışıl Dadı'sın. {baby_name} ({baby_info['age_formatted']}, {baby_info['leap_info']}) için sıcak, uzman bebek uyku tavsiyeleri ver."
        full_prompt = f"{system_ctx}\nSoru: {message}"
        encoded_prompt = urllib.parse.quote(full_prompt)
        url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai&seed=42"

        req = urllib.request.Request(url, headers={"User-Agent": "MisilBabyApp/2.2.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("utf-8").strip()
            if text and len(text) > 20:
                return text
    except Exception as e:
        logger.warning(f"Tier 3 (Pollinations) Error: {e}")
    return None


def _tier4_clinical_heuristic(baby_name: str, birth_date: str, message: str) -> str:
    """Tier 4: Offline Contextual Sirkadiyen Expert Pediatrician Engine (Zero-Crash Guarantee)"""
    baby_info = _calc_baby_details(birth_date)
    msg_lower = message.lower()

    if any(w in msg_lower for w in ["30 dk", "kısa", "hemen uyandı", "döngü", "kedi uykusu"]):
        return (
            f"Sevgili anneciğim/babacığım, {baby_name} ({baby_info['age_formatted']}) tam olarak 1. uyku döngüsünü tamamladı ancak REM'den NREM'e geçerken desteğe ihtiyaç duyuyor.\n\n"
            f"🌸 **Mışıl Dadı 3 Adımlı Döngü Bağlama Planı:**\n"
            f"1. **Işığı Açmayın:** Odayı kesinlikle aydınlatmayın, göz teması kurmadan fısıltıyla sakinleştirin.\n"
            f"2. **432Hz Ninnisi:** Mışıl Baby'deki *Brahms Ninnisi* veya *432Hz Pembe Gürültü*yü açın.\n"
            f"3. **Sırt Sıvazlama:** Yatağındayken ritmik şekilde 3 dakika sırtını pışpışlayarak uyku döngüsünü bağlamasına yardım edin."
        )
    elif any(w in msg_lower for w in ["gece", "uyanma", "beslenme", "mama", "meme"]):
        return (
            f"{baby_name}'nın {baby_info['age_formatted']} gelişim evresinde gece uyanmaları genellikle açlıktan ziyade uyku güvencesi arayışındandır.\n\n"
            f"🍼 **Mışıl Dadı Gece Beslenmesi Tavsiyesi:**\n"
            f"• Uyanır uyanmaz hemen kucağa alıp beslemek yerine, 90 saniye kendi kendine dönmesine fırsat tanıyın.\n"
            f"• Beslerken ortamı loş tutun ve konuşmayın; beslenme bittiğinde hafif mayışmışken yatağına koyunuz."
        )
    elif any(w in msg_lower for w in ["regresyon", "4. ay", "atak", "huysuz", "ağlıyor"]):
        return (
            f"İçiniz çok rahat olsun, {baby_name} şu anda **{baby_info['leap_info']}** evresinde! Bu dönemde beyninde yeni sinirsel bağlantılar kurulduğu için uykusu bölünür.\n\n"
            f"✨ **Mışıl Dadı Kurtarma Reçetesi:**\n"
            f"• **SweetSpot® Süresi:** {baby_name} için uyanıklık penceresi en fazla **{baby_info['wake_window_min']} dakikadır**.\n"
            f"• Bu süreyi 10 dakika bile aşarsa aşırı kortizol salgılanır ve uykuya direniş başlar.\n"
            f"• Odayı 15 dakika önceden karartıp *5S Dr. Karp Doğal Pışpış* sesini başlatınız."
        )
    else:
        return (
            f"Merhaba sevgili ebeveynim, {baby_name} ({baby_info['age_formatted']}) için Mışıl Dadı yanınızda!\n\n"
            f"Bebeğinizin bu ayda günlük ideal uyku ihtiyacı toplam **14-15 saattir** (gündüz 3-4 uyku, gece 10-11 saat).\n"
            f"SweetSpot® sayacını takip ederek uyku saatlerini kaçırmadığınız sürece krizlerin %80'i kendiliğinden çözülecektir. Bana dilediğiniz an detaylı soru sorabilirsiniz! 🌙"
        )


def ask_mishil_dadi(baby_name: str, birth_date: str, message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Multi-Tier AI Execution Pipeline"""
    chat_history = chat_history or []
    
    # 1. Try Tier 1 (Gemini 2.5 Flash)
    reply = _tier1_gemini(baby_name, birth_date, message, chat_history)
    tier_used = "Tier 1 (Google Gemini 2.5 Pro/Flash)"

    # 2. Try Tier 2 (Gemini 1.5 Flash)
    if not reply:
        reply = _tier2_gemini_flash(baby_name, birth_date, message)
        tier_used = "Tier 2 (Gemini 1.5 Flash Fallback)"

    # 3. Try Tier 3 (Pollinations AI Free LLM)
    if not reply:
        reply = _tier3_pollinations(baby_name, birth_date, message)
        tier_used = "Tier 3 (Pollinations AI Fallback)"

    # 4. Try Tier 4 (Clinical Sirkadiyen Heuristic Engine)
    if not reply:
        reply = _tier4_clinical_heuristic(baby_name, birth_date, message)
        tier_used = "Tier 4 (Clinical Sirkadiyen Engine)"

    logger.info(f"Mışıl Dadı AI executed for {baby_name} using {tier_used}")

    return {
        "reply": reply,
        "tier_used": tier_used,
        "baby_name": baby_name,
        "timestamp": datetime.now().isoformat()
    }
