from datetime import datetime, timezone
import io
import csv
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, Header
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.base import get_db
from app.db.models import Feedback
from app.models.schemas import FeedbackCreate, FeedbackResponse, BaseResponse
from app.core.logging import get_logger

logger = get_logger("feedback")

router = APIRouter(prefix="/feedback", tags=["Anne Geri Bildirimi & 5 Yıldız Çarkı"])

ADMIN_PINS = {"MISIL-REV-9842", "MISILREV2026", "984271"}


def verify_admin_pin(
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
) -> bool:
    entered_pin = (pin or x_admin_pin or "").strip().upper()
    return entered_pin in ADMIN_PINS


@router.post("", response_model=BaseResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=BaseResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Kullanıcının uygulama içi memnuniyet/zorlanma geri bildirimini kaydeder.
    Mağazaya gitmeyen anne şikayetleri ve geliştirme önerileri burada toplanır.
    """
    client_ip = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "unknown")
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    try:
        fb = Feedback(
            message=payload.message.strip(),
            sentiment=payload.sentiment or "needs_improvement",
            baby_age_months=payload.baby_age_months,
            contact_info=payload.contact_info.strip() if payload.contact_info else None,
            platform=payload.platform or "ios",
            app_version=payload.app_version,
            ip_address=client_ip,
        )
        db.add(fb)
        db.commit()
        db.refresh(fb)
        logger.info(f"New mother feedback received [ID: {fb.id}, sentiment: {fb.sentiment}, age: {fb.baby_age_months}m]")
        return BaseResponse(success=True, message="Geri bildiriminiz sevgiyle alındı. Miniğinize mışıl mışıl uykular dileriz.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving feedback: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Geri bildirim kaydedilirken bir hata oluştu.",
        )


@router.get("/list", response_model=List[FeedbackResponse])
async def list_feedbacks(
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """JSON API: Yönetici PIN doğrulamasıyla tüm geri bildirimleri listeler."""
    if not verify_admin_pin(pin, x_admin_pin):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz veya eksik Yönetici PIN kodu.")

    feedbacks = db.query(Feedback).order_by(desc(Feedback.created_at)).limit(limit).all()
    return feedbacks


@router.get("/export.csv")
async def export_feedbacks_csv(
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Geri bildirimleri CSV (Excel) dosyası olarak dışa aktarır."""
    if not verify_admin_pin(pin, x_admin_pin):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz Yönetici PIN kodu.")

    feedbacks = db.query(Feedback).order_by(desc(Feedback.created_at)).all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["ID", "Tarih (UTC)", "Duygu / Durum", "Bebek Yaşı (Ay)", "İletişim", "Platform", "Sürüm", "Mesaj"])

    for fb in feedbacks:
        dt_str = fb.created_at.strftime("%Y-%m-%d %H:%M:%S") if fb.created_at else ""
        writer.writerow([
            fb.id,
            dt_str,
            fb.sentiment,
            fb.baby_age_months or "",
            fb.contact_info or "",
            fb.platform,
            fb.app_version or "",
            fb.message.replace("\n", " "),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=misil_baby_feedbacks.csv"},
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def feedback_dashboard_page(
    pin: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Şık, koyu modlu, mobil uyumlu Anne Geri Bildirimleri Yönetici Paneli.
    """
    is_authed = verify_admin_pin(pin)
    if not is_authed:
        # PIN Giriş Ekranı
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html lang="tr">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>Yönetici Girişi — Mışıl Baby</title>
          <link rel="preconnect" href="https://fonts.googleapis.com">
          <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
          <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Sora:wght@600;700&display=swap" rel="stylesheet">
          <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
              background: #07090E radial-gradient(circle at 50% 20%, #151D33 0%, #07090E 75%);
              color: #FFF;
              font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
              min-height: 100vh;
              display: flex;
              align-items: center;
              justify-content: center;
              padding: 20px;
            }}
            .card {{
              background: rgba(18, 23, 38, 0.85);
              border: 1px solid rgba(255, 255, 255, 0.1);
              backdrop-filter: blur(16px);
              border-radius: 20px;
              padding: 36px 28px;
              width: 100%;
              max-width: 380px;
              text-align: center;
              box-shadow: 0 20px 40px rgba(0,0,0,0.5);
            }}
            .moon {{ font-size: 40px; margin-bottom: 12px; }}
            h2 {{ font-family: 'Sora', sans-serif; font-size: 20px; font-weight: 700; margin-bottom: 8px; color: #FFF; }}
            p {{ color: #8E99B0; font-size: 13px; line-height: 1.5; margin-bottom: 24px; }}
            input {{
              width: 100%;
              padding: 14px 16px;
              border-radius: 12px;
              border: 1px solid rgba(232, 168, 85, 0.3);
              background: rgba(0, 0, 0, 0.4);
              color: #FFF;
              font-size: 16px;
              font-weight: 600;
              text-align: center;
              letter-spacing: 2px;
              margin-bottom: 16px;
              outline: none;
              transition: border-color 0.2s;
            }}
            input:focus {{ border-color: #E8A855; }}
            button {{
              width: 100%;
              padding: 14px;
              border-radius: 12px;
              border: none;
              background: linear-gradient(135deg, #E8A855 0%, #D48828 100%);
              color: #07090E;
              font-size: 15px;
              font-weight: 700;
              cursor: pointer;
              transition: transform 0.15s, opacity 0.2s;
            }}
            button:active {{ transform: scale(0.98); }}
            .err {{ color: #FF6B6B; font-size: 12px; margin-top: 12px; display: {'block' if pin else 'none'}; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="moon">🌙</div>
            <h2>Mışıl Geri Bildirim Paneli</h2>
            <p>Anne mesajlarını ve mağaza koruma bildirimlerini görüntülemek için PIN kodunuzu giriniz.</p>
            <form method="GET">
              <input type="password" name="pin" placeholder="Yönetici PIN" autofocus autocomplete="off" />
              <button type="submit">Panele Giriş Yap</button>
            </form>
            <div class="err">❌ Geçersiz PIN kodu. Lütfen tekrar deneyin.</div>
          </div>
        </body>
        </html>
        """)

    # PIN Doğru — Gösterge Paneli
    feedbacks = db.query(Feedback).order_by(desc(Feedback.created_at)).all()
    total_count = len(feedbacks)
    now_utc = datetime.now(timezone.utc)
    
    # Son 24 saat sayısı
    last_24h_count = sum(1 for fb in feedbacks if fb.created_at and (now_utc - fb.created_at.replace(tzinfo=timezone.utc if fb.created_at.tzinfo is None else fb.created_at.tzinfo)).total_seconds() <= 86400)

    rows_html = ""
    for fb in feedbacks:
        dt_str = fb.created_at.strftime("%d.%m.%Y %H:%M") if fb.created_at else "—"
        
        # Platform rozeti
        plat = (fb.platform or "ios").lower()
        if "ios" in plat or "apple" in plat:
            plat_badge = '<span class="badge badge-ios">🍏 iOS</span>'
        elif "android" in plat:
            plat_badge = '<span class="badge badge-android">🤖 Android</span>'
        else:
            plat_badge = '<span class="badge badge-web">🌐 Web</span>'

        # Duygu rozeti
        sent = (fb.sentiment or "").lower()
        if "awake" in sent or "still_awake" in sent:
            sent_badge = '<span class="badge badge-awake">🥱 Uyuyamadı</span>'
        elif "needs" in sent:
            sent_badge = '<span class="badge badge-warn">🟡 Zorlandık</span>'
        else:
            sent_badge = '<span class="badge badge-info">💡 Öneri/İstek</span>'

        # Bebek yaşı
        age_str = f"👶 {fb.baby_age_months} Aylık" if fb.baby_age_months is not None else "👶 Yaş Belirtilmedi"
        contact_str = f'<span class="contact-pill">💬 {fb.contact_info}</span>' if fb.contact_info else ""

        rows_html += f"""
        <div class="feedback-card">
          <div class="feedback-header">
            <div class="feedback-meta">
              <span class="time">{dt_str}</span>
              {plat_badge}
              {sent_badge}
              <span class="badge badge-age">{age_str}</span>
            </div>
            {contact_str}
          </div>
          <div class="feedback-body">
            "{fb.message}"
          </div>
        </div>
        """

    if not rows_html:
        rows_html = """
        <div class="empty-state">
          <div class="empty-moon">🌙</div>
          <h3>Henüz bir anne geri bildirimi yok</h3>
          <p>Uygulamada uykusuzluk veya zorlanma bildiren annelerin mesajları burada güvenle listelenecektir.</p>
        </div>
        """

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Mışıl Baby — Anne Geri Bildirimleri Paneli</title>
      <link rel="preconnect" href="https://fonts.googleapis.com">
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Sora:wght@600;700&display=swap" rel="stylesheet">
      <style>
        :root {{
          --bg: #07090E;
          --card-bg: rgba(18, 23, 38, 0.75);
          --card-border: rgba(255, 255, 255, 0.08);
          --accent: #E8A855;
          --accent-soft: rgba(232, 168, 85, 0.15);
          --text-main: #FFFFFF;
          --text-muted: #8E99B0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background-color: var(--bg);
          background-image: radial-gradient(circle at 50% 0%, #151D33 0%, var(--bg) 65%);
          color: var(--text-main);
          font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
          min-height: 100vh;
          padding: 24px 16px 60px;
        }}
        .container {{
          max-width: 800px;
          margin: 0 auto;
        }}
        .header {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 16px;
          margin-bottom: 24px;
          padding-bottom: 16px;
          border-bottom: 1px solid var(--card-border);
        }}
        .brand {{
          display: flex;
          align-items: center;
          gap: 12px;
        }}
        .brand-icon {{
          font-size: 32px;
        }}
        .brand h1 {{
          font-family: 'Sora', sans-serif;
          font-size: 20px;
          font-weight: 700;
          color: #FFF;
          letter-spacing: -0.3px;
        }}
        .brand p {{
          color: var(--text-muted);
          font-size: 13px;
        }}
        .actions {{
          display: flex;
          gap: 10px;
        }}
        .btn {{
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 10px 16px;
          border-radius: 10px;
          font-size: 13px;
          font-weight: 600;
          text-decoration: none;
          cursor: pointer;
          transition: all 0.2s;
        }}
        .btn-export {{
          background: rgba(232, 168, 85, 0.15);
          border: 1px solid rgba(232, 168, 85, 0.3);
          color: var(--accent);
        }}
        .btn-export:hover {{
          background: var(--accent);
          color: #07090E;
        }}
        .stats-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 12px;
          margin-bottom: 24px;
        }}
        .stat-card {{
          background: var(--card-bg);
          border: 1px solid var(--card-border);
          border-radius: 14px;
          padding: 18px;
          backdrop-filter: blur(12px);
        }}
        .stat-label {{
          color: var(--text-muted);
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 6px;
        }}
        .stat-val {{
          font-family: 'Sora', sans-serif;
          font-size: 26px;
          font-weight: 700;
          color: #FFF;
        }}
        .stat-sub {{
          font-size: 11px;
          color: #10B981;
          margin-top: 4px;
        }}
        .search-box {{
          width: 100%;
          padding: 12px 16px;
          border-radius: 12px;
          border: 1px solid var(--card-border);
          background: rgba(18, 23, 38, 0.5);
          color: #FFF;
          font-size: 14px;
          margin-bottom: 16px;
          outline: none;
        }}
        .search-box:focus {{
          border-color: var(--accent);
        }}
        .feedback-card {{
          background: var(--card-bg);
          border: 1px solid var(--card-border);
          border-radius: 14px;
          padding: 18px;
          margin-bottom: 12px;
          backdrop-filter: blur(12px);
          transition: transform 0.15s, border-color 0.2s;
        }}
        .feedback-card:hover {{
          border-color: rgba(232, 168, 85, 0.3);
          transform: translateY(-1px);
        }}
        .feedback-header {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 12px;
        }}
        .feedback-meta {{
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          gap: 6px;
        }}
        .time {{
          font-size: 12px;
          color: var(--text-muted);
          font-weight: 500;
          margin-right: 4px;
        }}
        .badge {{
          font-size: 11px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 6px;
          letter-spacing: 0.2px;
        }}
        .badge-ios {{ background: rgba(59, 130, 246, 0.15); color: #60A5FA; border: 1px solid rgba(59, 130, 246, 0.3); }}
        .badge-android {{ background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .badge-web {{ background: rgba(139, 92, 246, 0.15); color: #A78BFA; border: 1px solid rgba(139, 92, 246, 0.3); }}
        .badge-awake {{ background: rgba(245, 158, 11, 0.15); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.3); }}
        .badge-warn {{ background: rgba(239, 68, 68, 0.15); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.3); }}
        .badge-info {{ background: rgba(14, 165, 233, 0.15); color: #38BDF8; border: 1px solid rgba(14, 165, 233, 0.3); }}
        .badge-age {{ background: rgba(255, 255, 255, 0.05); color: #C9CEDC; border: 1px solid rgba(255, 255, 255, 0.1); }}
        .contact-pill {{
          font-size: 12px;
          font-weight: 600;
          color: var(--accent);
          background: var(--accent-soft);
          padding: 3px 10px;
          border-radius: 20px;
        }}
        .feedback-body {{
          font-size: 14px;
          color: #E2E8F0;
          line-height: 1.6;
          font-style: italic;
          background: rgba(0, 0, 0, 0.25);
          padding: 12px 14px;
          border-radius: 8px;
          border-left: 3px solid var(--accent);
        }}
        .empty-state {{
          text-align: center;
          padding: 60px 20px;
          background: var(--card-bg);
          border: 1px dashed var(--card-border);
          border-radius: 16px;
        }}
        .empty-moon {{ font-size: 48px; margin-bottom: 12px; }}
        .empty-state h3 {{ font-size: 18px; margin-bottom: 6px; }}
        .empty-state p {{ color: var(--text-muted); font-size: 13px; max-width: 420px; margin: 0 auto; }}
      </style>
      <script>
        function filterFeedbacks() {{
          const query = document.getElementById('search-input').value.toLowerCase();
          const cards = document.querySelectorAll('.feedback-card');
          cards.forEach(card => {{
            const text = card.innerText.toLowerCase();
            card.style.display = text.includes(query) ? 'block' : 'none';
          }});
        }}
      </script>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <div class="brand">
            <span class="brand-icon">🌙</span>
            <div>
              <h1>Mışıl Baby Anne Geri Bildirimleri</h1>
              <p>5 Yıldız Koruma & Gece Nöbeti Gözlem Paneli</p>
            </div>
          </div>
          <div class="actions" style="display:flex; gap:8px; flex-wrap:wrap;">
            <a href="/api/v1/analytics/dashboard?pin={pin}" class="btn" style="background:rgba(59,130,246,0.18); color:#60A5FA; border:1px solid rgba(59,130,246,0.35); text-decoration:none; padding:10px 14px; border-radius:10px; font-size:13px; font-weight:700;">📊 Reklam & Tıklama Kokpiti</a>
            <a href="/api/v1/feedback/export.csv?pin={pin}" class="btn btn-export">📥 CSV Olarak İndir</a>
          </div>
        </div>

        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-label">Toplam Bildirim</div>
            <div class="stat-val">{total_count}</div>
            <div class="stat-sub">Sistem Arşivi</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Son 24 Saat</div>
            <div class="stat-val">{last_24h_count}</div>
            <div class="stat-sub">Aktif Nöbetler</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Mağaza Koruması</div>
            <div class="stat-val">Aktif 🛡️</div>
            <div class="stat-sub">Negatif filtreleme devrede</div>
          </div>
        </div>

        <input type="text" id="search-input" class="search-box" placeholder="Geri bildirimlerde ara (kelime, ay, platform)..." onkeyup="filterFeedbacks()" />

        <div id="feedbacks-list">
          {rows_html}
        </div>
      </div>
    </body>
    </html>
    """)

