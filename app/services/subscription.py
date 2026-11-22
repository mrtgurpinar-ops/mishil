from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import User, Subscription, SubscriberLedger, SubscriptionLifecycleEvent, FamilyGroup
from app.models.enums import SubscriptionStatus, SubscriptionPlan
from app.models.schemas import SubscriptionResponse

logger = get_logger("subscription")


class SubscriptionService:
    """Subscription lifecycle, paid introductory offer and RevenueCat webhook synchronization."""

    @classmethod
    def calculate_status(cls, user: User, subscription: Optional[Subscription]) -> Dict[str, Any]:
        """Determine active status, remaining period days, and effective subscription tier."""
        now = datetime.now(timezone.utc)

        def _ensure_utc(dt_val: Optional[datetime]) -> Optional[datetime]:
            if dt_val is None:
                return None
            return dt_val.replace(tzinfo=timezone.utc) if dt_val.tzinfo is None else dt_val

        # 1. Active or Grace Period paid subscription
        if subscription and subscription.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE_PERIOD):
            period_end = _ensure_utc(getattr(subscription, "current_period_end", None))
            if subscription.status == SubscriptionStatus.ACTIVE and period_end and period_end <= now:
                return {
                    "status": SubscriptionStatus.EXPIRED,
                    "plan": subscription.plan,
                    "trial_ends_at": period_end,
                    "is_active": False,
                    "days_left_in_trial": 0,
                }
            return {
                "status": subscription.status,
                "plan": subscription.plan,
                "trial_ends_at": period_end,
                "is_active": True,
                "days_left_in_trial": None,
            }

        # 2. Cancelled auto-renew subscription still within its paid billing period
        if subscription and subscription.status == SubscriptionStatus.CANCELLED:
            end_dt = _ensure_utc(getattr(subscription, "current_period_end", None))
            if end_dt and end_dt > now:
                delta = end_dt - now
                days_left = max(0, delta.days + (1 if delta.seconds > 0 else 0))
                return {
                    "status": SubscriptionStatus.CANCELLED,
                    "plan": subscription.plan,
                    "trial_ends_at": end_dt,
                    "is_active": True,
                    "days_left_in_trial": days_left,
                }
            return {
                "status": SubscriptionStatus.EXPIRED,
                "plan": subscription.plan,
                "trial_ends_at": end_dt,
                "is_active": False,
                "days_left_in_trial": 0,
            }

        # 3. Free trials are retired in v4.55.0+ (legacy trial_ends_at no longer grants active access)
        legacy_trial_dt = _ensure_utc(
            subscription.trial_ends_at if (subscription and subscription.trial_ends_at) else user.trial_ends_at
        )
        return {
            "status": SubscriptionStatus.EXPIRED,
            "plan": subscription.plan if subscription else None,
            "trial_ends_at": legacy_trial_dt,
            "is_active": False,
            "days_left_in_trial": 0,
        }

    @classmethod
    def start_trial(cls, db: Session, user: User) -> SubscriptionResponse:
        """Free trials are permanently retired in v4.55.0 (Hard Paywall + Paid Intro Offer)."""
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Ücretsiz deneme modeli sona ermiştir. Lütfen mağaza üzerinden Mışıl VIP aboneliğinizi başlatın.",
        )

    @classmethod
    def process_revenuecat_webhook(
        cls, db: Session, payload: Dict[str, Any], auth_header: Optional[str]
    ) -> Dict[str, Any]:
        """
        Verify webhook authorization header and process RevenueCat event types.
        Event types: INITIAL_PURCHASE, RENEWAL, CANCELLATION, EXPIRATION, PRODUCT_CHANGE
        """
        # Validate Webhook Authorization Secret (fail-closed in production if default secret was left unchanged)
        expected_secret = (settings.REVENUECAT_WEBHOOK_SECRET or "").strip()
        is_prod_env = settings.ENVIRONMENT.strip().lower() == "production"
        if is_prod_env and expected_secret in ("", "rc_webhook_secret_example_key"):
            logger.error("RevenueCat webhook rejected: REVENUECAT_WEBHOOK_SECRET is not configured in production.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook secret is not configured on server.",
            )
        if expected_secret:
            if not auth_header or (auth_header != expected_secret and auth_header != f"Bearer {expected_secret}"):
                logger.warning("Unauthorized RevenueCat webhook attempt")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid RevenueCat webhook secret authorization."
                )

        event_data = payload.get("event", {})
        event_type = event_data.get("type")
        app_user_id = event_data.get("app_user_id") or event_data.get("original_app_user_id")
        raw_product_id = str(event_data.get("new_product_id") or event_data.get("product_id") or "")
        product_id = raw_product_id.split(":")[0].strip() if ":" in raw_product_id else raw_product_id.strip()
        store_raw = str(event_data.get("store") or "").upper()
        period_type = str(event_data.get("period_type") or "NORMAL").upper()
        country_code = str(event_data.get("country_code") or "TR").upper()
        currency_code = str(event_data.get("currency") or "TRY").upper()
        price_usd_raw = float(event_data.get("price") or 0.0)
        price_in_purchased_currency = float(
            event_data.get("price_in_purchased_currency")
            if event_data.get("price_in_purchased_currency") is not None
            else price_usd_raw
        )
        fx_rates = {
            "TRY": 1.0,
            "EUR": 37.50,
            "USD": 34.50,
            "GBP": 43.50,
            "AUD": 22.50,
            "CAD": 25.00,
            "CHF": 39.50,
            "PLN": 8.70,
            "RON": 7.55,
            "BRL": 6.00,
            "MXN": 1.72,
            "INR": 0.41,
            "AED": 9.40,
            "SAR": 9.20,
            "AZN": 20.30,
            "GEL": 12.60,
            "CZK": 1.48,
            "UAH": 0.83,
            "HUF": 0.094,
            "KZT": 0.070,
            "UZS": 0.0027,
            "PHP": 0.59,
            "EGP": 0.70,
            "PKR": 0.124,
            "IDR": 0.0022,
            "COP": 0.0080,
        }
        if currency_code in fx_rates:
            price_in_try = round(price_in_purchased_currency * fx_rates[currency_code], 2)
        elif price_usd_raw != 0.0:
            price_in_try = round(price_usd_raw * fx_rates["USD"], 2)
        else:
            price_in_try = round(price_in_purchased_currency, 2)
        try:
            from app.api.v1.endpoints.analytics import get_dynamic_proceeds_ratio
            default_takehome = get_dynamic_proceeds_ratio("android" if "PLAY" in store_raw else "ios")
        except Exception:
            default_takehome = 0.727 if "PLAY" in store_raw else 0.55417
        takehome_pct = float(event_data.get("takehome_percentage") or default_takehome)
        if takehome_pct > 1.0:
            takehome_pct = takehome_pct / 100.0

        logger.info(f"Processing RevenueCat event {event_type} for user_id={app_user_id} store={store_raw} product={product_id}")

        if not app_user_id:
            return {"status": "ignored", "reason": "No app_user_id in payload"}

        pid_low = product_id.lower().strip()
        is_annual_prod = (
            "yearly" in pid_low
            or "annual" in pid_low
            or pid_low in ("misil", "6809228257")
            or pid_low.startswith("misil:")
        )
        platform_str = "android" if ("PLAY" in store_raw or pid_low in ("misil", "misilaylik") or pid_low.startswith("misil")) and not pid_low.startswith("misil_") else "ios"
        if "APP_STORE" in store_raw or "MAC_APP_STORE" in store_raw:
            platform_str = "ios"
        elif "PLAY_STORE" in store_raw:
            platform_str = "android"

        # Upsert SubscriberLedger & SubscriptionLifecycleEvent for Founder Dashboard (even for anonymous users)
        try:
            raw_sub_uid = str(event_data.get("original_transaction_id") or event_data.get("transaction_id") or app_user_id).strip()
            sub_uid = (raw_sub_uid.split("..")[0] if raw_sub_uid.startswith("GPA.") else raw_sub_uid)[:128]
            now_dt = datetime.now(timezone.utc)
            purchased_ms = event_data.get("purchased_at_ms")
            exp_ms = event_data.get("expiration_at_ms")
            start_dt = datetime.fromtimestamp(float(purchased_ms) / 1000.0, tz=timezone.utc) if purchased_ms else now_dt
            exp_dt = (
                datetime.fromtimestamp(float(exp_ms) / 1000.0, tz=timezone.utc)
                if exp_ms
                else (start_dt + timedelta(days=7 if period_type == "TRIAL" else (365 if is_annual_prod else 30)))
            )
            start_str = start_dt.strftime("%Y-%m-%d")
            exp_str = exp_dt.strftime("%Y-%m-%d")

            std_catalog_by_ccy = {
                "TRY": (149.99, 599.99),
                "CHF": (5.00, 25.00),
                "EUR": (4.99, 29.99),
                "USD": (4.99, 24.99),
                "GBP": (4.99, 24.99),
                "CAD": (6.99, 34.99),
                "AUD": (7.99, 39.99),
                "PLN": (14.99, 69.99),
                "RON": (14.99, 69.99),
                "BRL": (14.90, 59.90),
                "MXN": (49.00, 249.00),
                "INR": (149.00, 699.00),
                "AED": (17.99, 89.99),
                "SAR": (19.99, 99.99),
                "AZN": (4.29, 21.99),
                "KZT": (1290.00, 5990.00),
                "UZS": (31900.00, 149000.00),
            }
            if currency_code in std_catalog_by_ccy and currency_code in fx_rates:
                m_std_local, y_std_local = std_catalog_by_ccy[currency_code]
                exp_gross = round((y_std_local if is_annual_prod else m_std_local) * fx_rates[currency_code], 2)
            elif price_in_try > 0 and not (
                not is_annual_prod and period_type in ("INTRO", "INTRODUCTORY")
            ):
                exp_gross = price_in_try
            elif price_in_try > 0:
                exp_gross = 149.99 if currency_code == "TRY" else round(price_in_try * 3.0, 2)
            else:
                exp_gross = 599.99 if is_annual_prod else 149.99
            try:
                from app.api.v1.endpoints.analytics import get_dynamic_proceeds_ratio
                plat_ratio = get_dynamic_proceeds_ratio(platform_str)
            except Exception:
                plat_ratio = 0.727 if platform_str == "android" else 0.55417
            exp_net = round(exp_gross * (takehome_pct if 0.45 <= takehome_pct <= 0.90 else plat_ratio), 2)

            cancel_reason = str(event_data.get("cancel_reason") or "").upper()
            is_refund = event_type == "CANCELLATION" and (
                cancel_reason == "CUSTOMER_SUPPORT" or price_in_purchased_currency < 0
            )
            is_intro_paid = bool(
                not is_annual_prod
                and price_in_purchased_currency > 0.0
                and period_type in ("INTRO", "INTRODUCTORY")
            )

            ledger_row = db.query(SubscriberLedger).filter(SubscriberLedger.subscriber_id == sub_uid).first()
            already_paid_row = bool(ledger_row and ledger_row.status == "paid_active" and (ledger_row.customer_price_try or 0.0) > 0)

            if event_type == "EXPIRATION":
                ledger_status = "cancelled"
                auto_renew = False
            elif event_type == "CANCELLATION":
                if already_paid_row and not is_refund and exp_dt > now_dt:
                    ledger_status = "paid_active"
                    auto_renew = False
                else:
                    ledger_status = "cancelled"
                    auto_renew = False
            elif period_type == "PROMOTIONAL" and price_in_purchased_currency <= 0.0:
                ledger_status = "offer_code_trial"
                auto_renew = True
            elif period_type == "TRIAL" or (price_in_purchased_currency <= 0.0 and event_type == "INITIAL_PURCHASE"):
                ledger_status = "intro_free_trial"
                auto_renew = True
            else:
                ledger_status = "paid_active"
                auto_renew = True

            realized_gross = (
                round(price_in_try, 2)
                if ledger_status == "paid_active" and price_in_try > 0
                else (exp_gross if ledger_status == "paid_active" and not already_paid_row else 0.0)
            )
            realized_net = round(realized_gross * takehome_pct, 2) if realized_gross > 0 else 0.0
            plan_lbl = (
                ("Mışıl Baby Yıllık VIP (Android)" if is_annual_prod else "Mışıl Baby Aylık VIP (Android)")
                if platform_str == "android"
                else ("Mışıl Yıllık VIP" if is_annual_prod else "Mışıl Aylık Esnek")
            )

            if ledger_status == "offer_code_trial":
                offer_type_val = "offer_code"
                offer_code_lbl = event_data.get("presented_offering_id")
            elif ledger_status == "intro_free_trial":
                offer_type_val = "intro_7d_trial"
                offer_code_lbl = None
            elif is_intro_paid and ledger_status == "paid_active":
                offer_type_val = "intro_1m_discounted"
                offer_code_lbl = "İlk Ay İndirimli Başlangıç"
            elif ledger_row and ledger_row.offer_type == "intro_1m_discounted" and event_type in ("CANCELLATION", "EXPIRATION"):
                offer_type_val = "intro_1m_discounted"
                offer_code_lbl = ledger_row.offer_code_name
            else:
                offer_type_val = "standard_paid"
                offer_code_lbl = None

            prod_id_resolved = product_id or (
                "misil"
                if platform_str == "android" and is_annual_prod
                else ("misilaylik" if platform_str == "android" else ("misil_annual" if is_annual_prod else "misil_monthly"))
            )
            if not ledger_row:
                ledger_row = SubscriberLedger(
                    subscriber_id=sub_uid,
                    rc_app_user_id=str(app_user_id)[:128] if app_user_id else None,
                    platform=platform_str,
                    product_id=prod_id_resolved,
                    plan_label=plan_lbl,
                    status=ledger_status,
                    offer_type=offer_type_val,
                    offer_code_name=offer_code_lbl,
                    started_date=start_str,
                    converted_or_renewed_date=start_str,
                    maturity_or_renewal_date=exp_str,
                    customer_price_try=realized_gross,
                    developer_proceeds_try=realized_net,
                    expected_next_price_try=exp_gross if auto_renew else 0.0,
                    expected_next_proceeds_try=exp_net if auto_renew else 0.0,
                    country=country_code,
                    device_type="Android" if platform_str == "android" else "iPhone",
                    auto_renew_enabled=auto_renew,
                )
                db.add(ledger_row)
            else:
                # Out-of-order koruması: daha eski bir olayın daha yeni bir iptal/dönüşüm durumunu ezmesini engelle
                is_stale_event = bool(
                    ledger_row.converted_or_renewed_date
                    and start_str < ledger_row.converted_or_renewed_date
                    and ledger_row.status == "cancelled"
                    and event_type == "INITIAL_PURCHASE"
                )
                if not is_stale_event:
                    prev_conv_date = ledger_row.converted_or_renewed_date
                    if app_user_id:
                        ledger_row.rc_app_user_id = str(app_user_id)[:128]
                    ledger_row.platform = platform_str
                    ledger_row.product_id = prod_id_resolved
                    ledger_row.plan_label = plan_lbl
                    ledger_row.status = ledger_status
                    ledger_row.offer_type = offer_type_val
                    if offer_code_lbl:
                        ledger_row.offer_code_name = offer_code_lbl
                    ledger_row.auto_renew_enabled = auto_renew
                    ledger_row.converted_or_renewed_date = start_str
                    ledger_row.maturity_or_renewal_date = exp_str
                    if is_refund:
                        ledger_row.customer_price_try = 0.0
                        ledger_row.developer_proceeds_try = 0.0
                    elif realized_gross > 0 and event_type not in ("CANCELLATION", "EXPIRATION", "PRODUCT_CHANGE"):
                        if event_type == "RENEWAL" and prev_conv_date != start_str:
                            ledger_row.customer_price_try = round((ledger_row.customer_price_try or 0.0) + realized_gross, 2)
                            ledger_row.developer_proceeds_try = round((ledger_row.developer_proceeds_try or 0.0) + realized_net, 2)
                        else:
                            ledger_row.customer_price_try = max(float(ledger_row.customer_price_try or 0.0), realized_gross)
                            ledger_row.developer_proceeds_try = max(float(ledger_row.developer_proceeds_try or 0.0), realized_net)
                    ledger_row.expected_next_price_try = exp_gross if auto_renew else 0.0
                    ledger_row.expected_next_proceeds_try = exp_net if auto_renew else 0.0

            # Kurucu Kokpiti _heal_ios_ledger_rows uyumu: iadesiz CANCELLATION'da :will_not_renew işareti bırak,
            # yeniden aktifleşmede (UNCANCELLATION / RENEWAL / INITIAL_PURCHASE) eski :will_not_renew kaydını temizle
            wnr_key = f"{sub_uid}:will_not_renew"[:128]
            if event_type == "CANCELLATION" and not is_refund and ledger_row.status == "paid_active":
                if not (
                    db.query(SubscriptionLifecycleEvent)
                    .filter(
                        SubscriptionLifecycleEvent.platform == platform_str,
                        SubscriptionLifecycleEvent.event_type == wnr_key,
                    )
                    .first()
                ):
                    db.add(
                        SubscriptionLifecycleEvent(
                            event_date=start_str,
                            platform=platform_str,
                            event_type=wnr_key,
                            product_id=prod_id_resolved,
                            plan_label=plan_lbl,
                            offer_code_name=ledger_row.offer_code_name,
                            country=country_code,
                            device_type="Android" if platform_str == "android" else "iPhone",
                            quantity=1,
                        )
                    )
            elif event_type in ("INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION", "PRODUCT_CHANGE"):
                db.query(SubscriptionLifecycleEvent).filter(
                    SubscriptionLifecycleEvent.platform == platform_str,
                    SubscriptionLifecycleEvent.event_type == wnr_key,
                ).delete(synchronize_session=False)

            evt_type_key = f"RC:{event_type}:{sub_uid}"[:128]
            if not (
                db.query(SubscriptionLifecycleEvent)
                .filter(
                    SubscriptionLifecycleEvent.event_date == start_str,
                    SubscriptionLifecycleEvent.event_type == evt_type_key,
                    SubscriptionLifecycleEvent.product_id == prod_id_resolved,
                )
                .first()
            ):
                db.add(
                    SubscriptionLifecycleEvent(
                        event_date=start_str,
                        platform=platform_str,
                        event_type=evt_type_key,
                        product_id=prod_id_resolved,
                        plan_label=plan_lbl,
                        offer_code_name=ledger_row.offer_code_name,
                        country=country_code,
                        device_type="Android" if platform_str == "android" else "iPhone",
                        quantity=1,
                    )
                )
            # Push-based FamilyGroup VIP senkronu: Kurucu aboneliği bittiğinde (EXPIRATION) veya iadeli iptalde
            # aile grubunun vip_active bayrağını anında düşür; yenileme/alım geldiğinde aktif tut.
            candidate_sub_ids = [s for s in {sub_uid, str(app_user_id).strip()} if s]
            if candidate_sub_ids:
                fam_rows = (
                    db.query(FamilyGroup)
                    .filter(FamilyGroup.vip_subscriber_id.in_(candidate_sub_ids))
                    .all()
                )
                for fg in fam_rows:
                    if ledger_status == "cancelled":
                        fg.vip_active = False
                        fg.vip_plan = "free"
                    elif ledger_status in ("paid_active", "offer_code_trial"):
                        fg.vip_active = True
                        fg.vip_plan = "yearly" if is_annual_prod else "monthly"

            db.commit()
            try:
                from app.api.v1.endpoints.analytics import invalidate_analytics_summary_cache
                invalidate_analytics_summary_cache(mark_reconcile=True)
            except Exception:
                pass
        except Exception as ledger_err:
            db.rollback()
            logger.error(f"SubscriberLedger upsert failed inside RevenueCat webhook: {ledger_err}", exc_info=True)

        # Find user
        user = None
        if str(app_user_id).isdigit():
            user = db.query(User).filter(User.id == int(app_user_id)).first()
        if not user:
            user = db.query(User).filter(User.email == str(app_user_id)).first()

        if not user:
            logger.warning(f"User not found for RevenueCat webhook: {app_user_id} (SubscriberLedger updated)")
            return {"status": "user_not_found", "app_user_id": app_user_id, "ledger_synced": True}

        sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        if not sub:
            sub = Subscription(user_id=user.id)
            db.add(sub)

        sub.provider_ref = event_data.get("original_transaction_id") or str(app_user_id)

        # Map product_id to Plan
        if is_annual_prod:
            sub.plan = SubscriptionPlan.YEARLY
        elif "weekly" in pid_low:
            sub.plan = SubscriptionPlan.WEEKLY
        elif "lifetime" in pid_low:
            sub.plan = SubscriptionPlan.LIFETIME
        else:
            sub.plan = SubscriptionPlan.MONTHLY

        # Update status and paid billing period end based on event type
        cancel_reason_u = str(event_data.get("cancel_reason") or "").upper()
        is_refund_u = event_type == "CANCELLATION" and (
            cancel_reason_u == "CUSTOMER_SUPPORT" or price_in_purchased_currency < 0
        )
        now_u = datetime.now(timezone.utc)
        exp_ms_u = event_data.get("expiration_at_ms")
        purchased_ms_u = event_data.get("purchased_at_ms")
        start_dt_u = datetime.fromtimestamp(float(purchased_ms_u) / 1000.0, tz=timezone.utc) if purchased_ms_u else now_u
        exp_dt_u = (
            datetime.fromtimestamp(float(exp_ms_u) / 1000.0, tz=timezone.utc)
            if exp_ms_u
            else (start_dt_u + timedelta(days=365 if is_annual_prod else 30))
        )

        if event_type in ["INITIAL_PURCHASE", "RENEWAL", "NON_RENEWING_PURCHASE", "UNCANCELLATION", "PRODUCT_CHANGE"]:
            sub.status = SubscriptionStatus.ACTIVE
            sub.current_period_end = exp_dt_u
            user.subscription_status = SubscriptionStatus.ACTIVE
        elif event_type == "CANCELLATION":
            if is_refund_u:
                sub.status = SubscriptionStatus.EXPIRED
                sub.current_period_end = now_u
                user.subscription_status = SubscriptionStatus.EXPIRED
            else:
                sub.status = SubscriptionStatus.CANCELLED
                sub.current_period_end = exp_dt_u
                user.subscription_status = (
                    SubscriptionStatus.CANCELLED if exp_dt_u > now_u else SubscriptionStatus.EXPIRED
                )
        elif event_type == "EXPIRATION":
            sub.status = SubscriptionStatus.EXPIRED
            sub.current_period_end = exp_dt_u
            user.subscription_status = SubscriptionStatus.EXPIRED
        elif event_type == "BILLING_ISSUE":
            sub.status = SubscriptionStatus.GRACE_PERIOD
            sub.current_period_end = exp_dt_u

        # Kullanıcı bazlı oluşturulmuş FamilyGroup kayıtlarını da anında senkronla
        is_sub_active_now = sub.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE_PERIOD) or (
            sub.status == SubscriptionStatus.CANCELLED and bool(sub.current_period_end and sub.current_period_end > now_u)
        )
        owner_fams = db.query(FamilyGroup).filter(FamilyGroup.created_by_user_id == user.id).all()
        for fg in owner_fams:
            fg.vip_active = is_sub_active_now
            fg.vip_plan = ("yearly" if is_annual_prod else "monthly") if is_sub_active_now else "free"

        db.commit()
        try:
            from app.api.v1.endpoints.analytics import invalidate_analytics_summary_cache
            invalidate_analytics_summary_cache(mark_reconcile=True)
        except Exception:
            pass
        return {"status": "success", "event_type": event_type, "user_id": user.id}
