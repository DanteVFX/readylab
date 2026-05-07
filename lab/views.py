from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from datetime import timedelta

from .models import (Appointment, PreparationStatus, ProtocolEvent, FASTING_RULES,
                     MEAL_PROFILE_CHOICES, meal_extra_hours,
                     STATUS_CONFIRMED, STATUS_SCHEDULED,
                     EVENT_SENT, EVENT_RESPONDED, EVENT_EXPIRED)
from .serializers import (AppointmentListSerializer, AppointmentCreateSerializer,
                           ReminderLogSerializer, ProtocolEventSerializer)
from .engine import transition_states


# ─── Dashboard ─────────────────────────────────────────────────────────────────

def dashboard(request):
    """Sirve el dashboard HTML."""
    return render(request, "dashboard.html")


# ─── Endpoint de confirmación del paciente ─────────────────────────────────────

def confirm_preparation(request, token):
    """
    El paciente abre este link desde su celular.
    Cambia el estado a Confirmed.
    """
    appt = get_object_or_404(Appointment, confirm_token=token)
    prep, _ = PreparationStatus.objects.get_or_create(appointment=appt)

    if prep.status != STATUS_CONFIRMED:
        prep.status = STATUS_CONFIRMED
        prep.save()
        message = "confirmed"
    else:
        message = "already_confirmed"

    return render(request, "confirm.html", {
        "appointment": appt,
        "message": message,
    })


# ─── API: Citas ────────────────────────────────────────────────────────────────

@api_view(["GET"])
def appointments_list(request):
    """
    GET /api/appointments/
    Parámetros opcionales:
      ?status=At Risk
      ?date=today  (default)
    """
    now = timezone.now()

    # Muestra todas las citas (sin filtro de fecha para evitar problemas de timezone)
    qs = Appointment.objects.all().select_related("patient", "status").order_by("scheduled_at")

    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status__status=status_filter)

    serializer = AppointmentListSerializer(qs, many=True)

    # Conteo de estados para las tarjetas del dashboard
    counts = {
        "Scheduled":    qs.filter(status__status="Scheduled").count(),
        "Prep Started": qs.filter(status__status="Prep Started").count(),
        "Confirmed":    qs.filter(status__status="Confirmed").count(),
        "No Response":  qs.filter(status__status="No Response").count(),
        "At Risk":      qs.filter(status__status="At Risk").count(),
    }

    # Compliance: % de citas confirmadas del total
    total = qs.count() or 1
    confirmed_count = counts.get("Confirmed", 0)
    compliance_pct = round(confirmed_count / total * 100)

    # Upcoming automations (next 5 pending protocol events)
    upcoming_events = ProtocolEvent.objects.filter(
        status="pending",
        scheduled_at__gte=now,
        scheduled_at__lte=now + timedelta(hours=24),
    ).select_related("appointment__patient").order_by("scheduled_at")[:5]

    automations = [
        {
            "time": e.scheduled_at.strftime("%H:%M"),
            "label": {
                "guidance": "Guidance",
                "meal_check_lunch": "Meal check",
                "meal_check_dinner": "Dinner check",
                "followup_retry": "Follow-up retry",
                "fasting_reminder": "Fasting reminder",
            }.get(e.event_type, e.event_type),
            "patient": e.appointment.patient.name,
        }
        for e in upcoming_events
    ]

    # Errors prevented = confirmed patients that had elevated risk
    errors_prevented = qs.filter(
        status__status="Confirmed",
        preanalytic_risk="elevated",
    ).count()

    return Response({
        "counts": counts,
        "compliance_pct": compliance_pct,
        "errors_prevented": errors_prevented,
        "automations": automations,
        "appointments": serializer.data,
    })


@csrf_exempt
@api_view(["POST"])
def appointments_create(request):
    """
    POST /api/appointments/
    Body JSON:
    {
      "patient_name": "María García",
      "patient_phone": "+52 55 1234 5678",
      "patient_email": "maria@email.com",
      "exam_type": "Glucosa en ayuno",
      "scheduled_at": "2024-11-15T09:00:00"
    }
    """
    serializer = AppointmentCreateSerializer(data=request.data)
    if serializer.is_valid():
        appt = serializer.save()
        response_data = AppointmentListSerializer(appt).data

        # Include welcome message for phone simulator
        from .models import ProtocolEvent, EVENT_GUIDANCE
        guidance = ProtocolEvent.objects.filter(
            appointment=appt, event_type=EVENT_GUIDANCE
        ).first()
        if guidance:
            response_data["welcome_message"] = guidance.message.replace(
                "{base_url}", f"{request.scheme}://{request.get_host()}"
            )

        return Response(response_data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def send_manual_reminder(request, appointment_id):
    """
    POST /api/appointments/<id>/remind/
    Envía un recordatorio manual desde el dashboard.
    Devuelve wa_link si el modo es whatsapp_link (para abrir en el browser).
    """
    from django.conf import settings as django_settings
    from .engine import simulate_send, build_reminder_message
    import urllib.parse

    appt = get_object_or_404(Appointment, pk=appointment_id)

    if appt.fasting_required:
        msg = build_reminder_message(appt)
        confirm_url = f"{request.scheme}://{request.get_host()}/confirm/{appt.confirm_token}/"
        final_msg = msg.format(confirm_url=confirm_url)
        simulate_send(appt, final_msg)

        response_data = {"ok": True, "message": "Reminder sent"}

        # Si está en modo whatsapp_link, incluir el link en la respuesta
        mode = getattr(django_settings, "READYLAB_MESSAGING", "console")
        if mode == "whatsapp_link":
            phone = appt.patient.phone.replace(" ", "").replace("-", "").replace("+", "")
            response_data["wa_link"] = f"https://wa.me/{phone}?text={urllib.parse.quote(final_msg)}"

        return Response(response_data)
    return Response({"ok": False, "message": "No preparation required for this exam"})


# ─── API: Reglas de exámenes ────────────────────────────────────────────────────

@api_view(["GET"])
def exam_rules(request):
    """
    GET /api/exam-rules/
    Devuelve las reglas de ayuno para poblar el formulario del frontend.
    """
    from .models import MEAL_SENSITIVE_EXAMS
    rules = [
        {
            "exam_type":       k,
            "required":        v["required"],
            "hours":           v["hours"],
            "meal_sensitive":  k in MEAL_SENSITIVE_EXAMS,   # +2h si High Fat Meal
        }
        for k, v in FASTING_RULES.items()
    ]
    return Response(rules)


# ─── API: Patient meal-check response (simulates WhatsApp reply) ──────────────

@api_view(["GET"])
def meal_check_respond(request, token):
    """
    GET /meal-check/<uuid:token>/?response=high_fat
    El paciente abre este link para reportar su comida.
    En el demo, el juez puede abrirlo desde el celular.
    """
    event = get_object_or_404(ProtocolEvent, response_token=token)
    meal_response = request.GET.get("response", "normal")

    if meal_response not in ("light", "normal", "high_fat"):
        meal_response = "normal"

    event.status = EVENT_RESPONDED
    event.response = meal_response
    event.responded_at = timezone.now()
    event.save()

    # Actualizar appointment según tipo de evento
    appt = event.appointment
    from .models import EVENT_MEAL_CHECK_LUNCH, EVENT_MEAL_CHECK_DINNER
    if event.event_type == EVENT_MEAL_CHECK_LUNCH:
        appt.lunch_type = meal_response
    elif event.event_type in (EVENT_MEAL_CHECK_DINNER, "followup_retry"):
        appt.dinner_type = meal_response
    appt.save()  # recalcula riesgo y ayuno

    labels = {"light": "Comida ligera", "normal": "Comida normal", "high_fat": "Alta en grasas"}
    return render(request, "meal_response.html", {
        "appointment": appt,
        "event": event,
        "meal_label": labels.get(meal_response, meal_response),
    })


# ─── API: Protocol events for an appointment ─────────────────────────────────

@api_view(["GET"])
def protocol_events_list(request, appointment_id):
    """GET /api/appointments/<id>/protocol/"""
    appt = get_object_or_404(Appointment, pk=appointment_id)
    events = ProtocolEvent.objects.filter(appointment=appt).order_by("scheduled_at")
    return Response(ProtocolEventSerializer(events, many=True).data)


# ─── API: Enviar un evento del protocolo manualmente desde el dashboard ───────

@api_view(["POST"])
def send_protocol_event(request, event_id):
    """
    POST /api/protocol-event/<id>/send/
    El laboratorio presiona el botón en el dashboard para enviar
    el check de almuerzo o cena al paciente ahora mismo.
    """
    from .engine import simulate_send
    from .models import (ProtocolEvent, PreparationStatus,
                         EVENT_PENDING, EVENT_SENT,
                         STATUS_AWAITING_MEAL)

    event = get_object_or_404(ProtocolEvent, pk=event_id)

    if event.status != EVENT_PENDING:
        return Response({"ok": False, "message": "Este mensaje ya fue enviado"})

    # Inyectar base_url en los links
    base_url = f"{request.scheme}://{request.get_host()}"
    msg = event.message.replace("{base_url}", base_url)

    # Enviar
    simulate_send(event.appointment, msg)
    event.status = EVENT_SENT
    event.sent_at = timezone.now()
    event.save()

    # Actualizar estado de la cita
    try:
        prep = event.appointment.status
        if prep.status in ("Scheduled", "Guidance Sent"):
            prep.status = STATUS_AWAITING_MEAL
            prep.save()
    except PreparationStatus.DoesNotExist:
        pass

    response_data = {
        "ok": True,
        "message": "Mensaje enviado al paciente",
        "wa_message": msg,
        "response_token": str(event.response_token),
        "event_type": event.event_type,
        "patient_name": event.appointment.patient.name,
    }

    from django.conf import settings as django_settings
    mode = getattr(django_settings, "READYLAB_MESSAGING", "console")
    if mode == "whatsapp_link":
        import urllib.parse
        phone = event.appointment.patient.phone.replace(" ", "").replace("-", "").replace("+", "")
        response_data["wa_link"] = f"https://wa.me/{phone}?text={urllib.parse.quote(msg)}"

    return Response(response_data)


# ─── API: Reenviar un evento del protocolo (no respondido) ─────────────────────

@api_view(["POST"])
def resend_protocol_event(request, event_id):
    """
    POST /api/protocol-event/<id>/resend/
    Reenvia un mensaje que ya fue enviado pero el paciente no respondió.
    Resetea el estado a PENDING para que se pueda enviar de nuevo.
    """
    from .engine import simulate_send
    from .models import ProtocolEvent, EVENT_SENT, EVENT_PENDING

    event = get_object_or_404(ProtocolEvent, pk=event_id)

    if event.status != EVENT_SENT:
        return Response({"ok": False, "message": "Este evento no está esperando respuesta"})

    # Inyectar base_url y enviar
    base_url = f"{request.scheme}://{request.get_host()}"
    msg = event.message.replace("{base_url}", base_url)
    simulate_send(event.appointment, msg)

    # Actualizar sent_at pero mantener en SENT
    event.sent_at = timezone.now()
    event.save()

    response_data = {
        "ok": True,
        "message": "Notificación reenviada al paciente",
        "wa_message": msg,
        "response_token": str(event.response_token),
        "event_type": event.event_type,
        "patient_name": event.appointment.patient.name,
    }

    from django.conf import settings as django_settings
    mode = getattr(django_settings, "READYLAB_MESSAGING", "console")
    if mode == "whatsapp_link":
        import urllib.parse
        phone = event.appointment.patient.phone.replace(" ", "").replace("-", "").replace("+", "")
        response_data["wa_link"] = f"https://wa.me/{phone}?text={urllib.parse.quote(msg)}"

    return Response(response_data)


# ─── API: Trigger manual del scheduler (útil para el demo) ────────────────────

@api_view(["POST"])
def trigger_engine(request):
    """
    POST /api/trigger-engine/
    Fuerza una evaluación del motor de estados ahora mismo.
    Útil para demos en vivo sin esperar 60 segundos.
    """
    transition_states()
    return Response({"ok": True, "message": "Motor ejecutado manualmente"})
