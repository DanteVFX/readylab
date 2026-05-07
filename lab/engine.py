"""
Motor de estados preanalíticos de ReadyLab.
Incluye protocolo automatizado de seguimiento.
"""
import logging
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


def build_reminder_message(appointment):
    fasting_start = appointment.fasting_start
    exam          = appointment.exam_type
    patient_name  = appointment.patient.name.split()[0]
    total_hours   = appointment.total_fasting_hours
    scheduled     = appointment.scheduled_at
    extra         = appointment.meal_extra_hours

    base_msg = (
        f"Hola {patient_name}, te recordamos que tu análisis de {exam} "
        f"está programado para las {scheduled:%H:%M}. "
        f"Debes iniciar tu ayuno de {total_hours} horas a las {fasting_start:%H:%M}."
    )
    if extra > 0:
        base_msg += f" Nota: se añadieron {extra}h extra por tu última comida alta en grasas."
    return base_msg + " Confirma tu preparación aquí: {confirm_url}"


def simulate_send(appointment, message, channel="WhatsApp"):
    """
    Envía mensaje al paciente.
    Estrategia configurable vía READYLAB_MESSAGING en settings.py:
      - "console"    → solo imprime en terminal (default, sin config)
      - "twilio"     → envío real vía Twilio WhatsApp Sandbox o SMS
      - "whatsapp_link" → genera link wa.me (útil para demo manual)
    """
    from django.conf import settings
    from lab.models import ReminderLog
    phone = appointment.patient.phone

    mode = getattr(settings, "READYLAB_MESSAGING", "console")

    # ── Modo 1: Console (simulado) ─────────────────────────────────────────
    if mode == "console":
        logger.info(f"[{channel} → {phone}] {message}")
        print(f"\n📱 {channel} → {phone}\n{message}\n{'─'*60}")

    # ── Modo 2: Twilio WhatsApp Sandbox (Content Templates) ──────────────
    elif mode == "twilio":
        try:
            from twilio.rest import Client
            account_sid = settings.TWILIO_ACCOUNT_SID
            auth_token  = settings.TWILIO_AUTH_TOKEN
            from_number = settings.TWILIO_FROM_NUMBER
            client = Client(account_sid, auth_token)

            # Limpiar teléfono
            to_number = phone.replace(" ", "").replace("-", "")
            if not to_number.startswith("+"):
                to_number = "+51" + to_number
            if channel == "WhatsApp":
                to_number = f"whatsapp:{to_number}"

            # Intentar envío con Content Template (requerido por WhatsApp sandbox)
            content_sid = getattr(settings, "TWILIO_CONTENT_SID", "")

            if content_sid:
                # Extraer datos de la cita para las variables del template
                appt_date = appointment.scheduled_at.strftime("%d/%m")
                appt_time = appointment.scheduled_at.strftime("%I:%M %p").lstrip("0").lower()
                content_vars = f'{{"1":"{appt_date}","2":"{appt_time}"}}'

                tw_msg = client.messages.create(
                    from_=from_number,
                    to=to_number,
                    content_sid=content_sid,
                    content_variables=content_vars,
                )
            else:
                # Fallback: envío con body (funciona si el paciente escribió primero)
                tw_msg = client.messages.create(
                    body=message,
                    from_=from_number,
                    to=to_number,
                )

            logger.info(f"[Twilio {channel} → {phone}] SID: {tw_msg.sid}")
            print(f"\n✅ Twilio {channel} → {phone} | SID: {tw_msg.sid}")
        except Exception as e:
            logger.error(f"[Twilio ERROR] {e}")
            print(f"\n❌ Twilio error: {e}")

    # ── Modo 3: WhatsApp Web link (abre wa.me en el browser) ───────────────
    elif mode == "whatsapp_link":
        import urllib.parse
        clean_phone = phone.replace(" ", "").replace("-", "").replace("+", "")
        encoded_msg = urllib.parse.quote(message)
        wa_link = f"https://wa.me/{clean_phone}?text={encoded_msg}"
        logger.info(f"[WhatsApp Link] {wa_link}")
        print(f"\n📱 WhatsApp link → {phone}")
        print(f"   {wa_link}\n{'─'*60}")

    # Siempre guardar en log
    ReminderLog.objects.create(appointment=appointment, message=message, channel=channel)


def process_protocol_events():
    """Procesa eventos de protocolo: envío, retries, expiración."""
    from lab.models import (
        ProtocolEvent, PreparationStatus,
        EVENT_PENDING, EVENT_SENT, EVENT_EXPIRED,
        EVENT_GUIDANCE, EVENT_MEAL_CHECK_LUNCH, EVENT_MEAL_CHECK_DINNER,
        EVENT_FOLLOWUP_RETRY,
        STATUS_GUIDANCE_SENT, STATUS_AWAITING_MEAL, STATUS_NO_RESPONSE_RISK,
    )

    now = timezone.now()
    processed = 0

    # 1. Enviar pendientes cuya hora llegó
    for event in ProtocolEvent.objects.filter(
        status=EVENT_PENDING, scheduled_at__lte=now,
    ).select_related("appointment__patient", "appointment__status"):
        appt = event.appointment
        # Inyectar base_url en los links de los mensajes
        msg = event.message.replace("{base_url}", "http://localhost:8000")
        simulate_send(appt, msg)
        event.status, event.sent_at = EVENT_SENT, now
        event.save()
        processed += 1

        try:
            prep = appt.status
        except PreparationStatus.DoesNotExist:
            continue

        if event.event_type == EVENT_GUIDANCE and prep.status == "Scheduled":
            prep.status = STATUS_GUIDANCE_SENT
            prep.save()
        elif event.event_type in (EVENT_MEAL_CHECK_LUNCH, EVENT_MEAL_CHECK_DINNER):
            if prep.status in ("Scheduled", "Guidance Sent"):
                prep.status = STATUS_AWAITING_MEAL
                prep.save()

    # 2. Retry: enviados sin respuesta >60 min
    for event in ProtocolEvent.objects.filter(
        status=EVENT_SENT,
        event_type__in=[EVENT_MEAL_CHECK_LUNCH, EVENT_MEAL_CHECK_DINNER, EVENT_FOLLOWUP_RETRY],
        sent_at__lte=now - timedelta(minutes=60),
    ).select_related("appointment__patient", "appointment__status"):
        if event.retry_count >= 1:
            event.status = EVENT_EXPIRED
            event.save()
            try:
                prep = event.appointment.status
                if prep.status not in ("Confirmed",):
                    prep.status = STATUS_NO_RESPONSE_RISK
                    prep.save()
            except PreparationStatus.DoesNotExist:
                pass
        else:
            name = event.appointment.patient.name.split()[0]
            # Reutilizar el token del evento original para el retry
            token = event.response_token
            retry = ProtocolEvent(
                appointment=event.appointment,
                event_type=EVENT_FOLLOWUP_RETRY,
                scheduled_at=now,
                message=(
                    f"📩 *ReadyLab — Te escribimos de nuevo*\n\n"
                    f"Hola {name}, aún no recibimos tu respuesta sobre tu comida.\n"
                    f"Necesitamos este dato para calcular tu ayuno correctamente.\n\n"
                    f"¿Cómo fue tu última comida?\n\n"
                    f"🥗 *Ligera* → http://localhost:8000/meal-check/{token}/?response=light\n\n"
                    f"🍛 *Normal* → http://localhost:8000/meal-check/{token}/?response=normal\n\n"
                    f"🍔 *Pesada* → http://localhost:8000/meal-check/{token}/?response=high_fat\n\n"
                    f"Solo toma un segundo. ¡Gracias! 🙏"
                ),
                retry_count=1,
            )
            retry.save()
            simulate_send(event.appointment, retry.message)
            retry.status, retry.sent_at = EVENT_SENT, now
            retry.save()
            event.status = EVENT_EXPIRED
            event.save()
        processed += 1

    if processed:
        logger.info(f"[Protocol] {processed} eventos procesados.")


def transition_states():
    """Motor principal ampliado con estados del protocolo."""
    from lab.models import (
        Appointment, PreparationStatus,
        STATUS_SCHEDULED, STATUS_PREP_STARTED, STATUS_CONFIRMED,
        STATUS_NO_RESPONSE, STATUS_AT_RISK,
        STATUS_GUIDANCE_SENT, STATUS_AWAITING_MEAL, STATUS_NO_RESPONSE_RISK,
    )

    now = timezone.now()
    appointments = Appointment.objects.filter(
        scheduled_at__gte=now - timedelta(hours=2)
    ).select_related("patient", "status")

    transitioned = 0
    for appt in appointments:
        try:
            prep = appt.status
        except PreparationStatus.DoesNotExist:
            prep = PreparationStatus.objects.create(appointment=appt)

        current = prep.status
        if current == STATUS_CONFIRMED:
            continue

        # Estados tempranos → Prep Started cuando toca ayuno
        if current in (STATUS_SCHEDULED, STATUS_GUIDANCE_SENT, STATUS_AWAITING_MEAL):
            if appt.fasting_required and appt.fasting_start:
                if now >= appt.fasting_start - timedelta(hours=1):
                    msg = build_reminder_message(appt)
                    url = f"http://localhost:8000/confirm/{appt.confirm_token}/"
                    simulate_send(appt, msg.format(confirm_url=url))
                    prep.status = STATUS_PREP_STARTED
                    prep.save()
                    transitioned += 1

        elif current == STATUS_PREP_STARTED:
            if appt.fasting_start:
                grace = appt.fasting_start - timedelta(hours=1) + timedelta(minutes=30)
                if now >= grace:
                    prep.status = STATUS_NO_RESPONSE
                    prep.save()
                    transitioned += 1

        elif current in (STATUS_NO_RESPONSE, STATUS_NO_RESPONSE_RISK):
            if now >= appt.scheduled_at - timedelta(hours=1):
                prep.status = STATUS_AT_RISK
                prep.save()
                transitioned += 1

    process_protocol_events()
    if transitioned:
        logger.info(f"[Scheduler] {transitioned} transiciones aplicadas.")


def start_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        import atexit
        scheduler = BackgroundScheduler()
        scheduler.add_job(transition_states, trigger=IntervalTrigger(seconds=10),
                          id="state_engine", name="ReadyLab Engine", replace_existing=True)
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())
        logger.info("[Scheduler] Motor iniciado (cada 10 s).")
    except Exception as e:
        logger.error(f"[Scheduler] Error: {e}")
