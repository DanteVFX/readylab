from rest_framework import serializers
from .models import Patient, Appointment, ReminderLog, FASTING_RULES


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Patient
        fields = ["id", "name", "phone", "email", "created"]


class AppointmentCreateSerializer(serializers.ModelSerializer):
    """Usado para POST — solo campos que el laboratorio ingresa."""
    patient_first_name = serializers.CharField(write_only=True)
    patient_last_name  = serializers.CharField(write_only=True)
    patient_phone = serializers.CharField(write_only=True)
    patient_email = serializers.EmailField(write_only=True, required=False, default="")

    class Meta:
        model  = Appointment
        fields = ["patient_first_name", "patient_last_name",
                  "patient_phone", "patient_email",
                  "exam_type", "scheduled_at",
                  "breakfast_type", "lunch_type", "dinner_type"]

    def create(self, validated_data):
        first_name = validated_data.pop("patient_first_name")
        last_name  = validated_data.pop("patient_last_name")
        phone      = validated_data.pop("patient_phone")
        email      = validated_data.pop("patient_email", "")
        full_name  = f"{first_name} {last_name}"

        # Buscar por teléfono; si ya existe, actualizar nombre
        patient, created = Patient.objects.get_or_create(
            phone=phone,
            defaults={"name": full_name, "email": email},
        )
        if not created:
            patient.name  = full_name
            if email:
                patient.email = email
            patient.save()

        return Appointment.objects.create(patient=patient, **validated_data)


class AppointmentListSerializer(serializers.ModelSerializer):
    """Usado para GET — incluye datos calculados para el dashboard."""
    patient_name    = serializers.CharField(source="patient.name")
    patient_phone   = serializers.CharField(source="patient.phone")
    status          = serializers.CharField(source="current_status")
    minutes_to_appt = serializers.IntegerField(source="minutes_to_appointment")
    fasting_start_fmt   = serializers.SerializerMethodField()
    total_fasting_hours = serializers.IntegerField()
    meal_profile_label  = serializers.SerializerMethodField()
    risk_label          = serializers.CharField()
    breakfast_label     = serializers.SerializerMethodField()
    lunch_label         = serializers.SerializerMethodField()
    dinner_label        = serializers.SerializerMethodField()
    journey_steps       = serializers.SerializerMethodField()
    protocol_actions    = serializers.SerializerMethodField()

    class Meta:
        model  = Appointment
        fields = [
            "id", "patient_name", "patient_phone",
            "exam_type", "scheduled_at", "fasting_required",
            "fasting_hours", "meal_profile", "meal_profile_label",
            "breakfast_type", "breakfast_label",
            "lunch_type", "lunch_label",
            "dinner_type", "dinner_label",
            "preanalytic_risk", "risk_label",
            "meal_extra_hours", "total_fasting_hours",
            "fasting_start", "fasting_start_fmt",
            "status", "minutes_to_appt", "confirm_token",
            "journey_steps",
            "protocol_actions",
        ]

    def get_meal_profile_label(self, obj):
        labels = {"light": "Light Meal", "normal": "Normal Meal", "high_fat": "High Fat Meal"}
        return labels.get(obj.meal_profile, obj.meal_profile)

    MEAL_LABELS = {"light": "Light Meal", "normal": "Normal Meal", "high_fat": "High Fat Meal"}

    def get_breakfast_label(self, obj):
        return self.MEAL_LABELS.get(obj.breakfast_type, obj.breakfast_type)

    def get_lunch_label(self, obj):
        return self.MEAL_LABELS.get(obj.lunch_type, obj.lunch_type)

    def get_dinner_label(self, obj):
        return self.MEAL_LABELS.get(obj.dinner_type, obj.dinner_type)

    def get_journey_steps(self, obj):
        """Genera los pasos del patient journey para el accordion."""
        from .models import ProtocolEvent
        events = ProtocolEvent.objects.filter(appointment=obj).order_by("scheduled_at")
        MEAL_ESP = {"light": "Comida ligera", "normal": "Comida normal", "high_fat": "Alta en grasas"}
        steps = []
        for e in events:
            label = {
                "guidance":          "Guía enviada",
                "meal_check_lunch":  "Almuerzo registrado",
                "meal_check_dinner": "Cena registrada",
                "followup_retry":    "Seguimiento enviado",
                "fasting_reminder":  "Recordatorio de ayuno",
            }.get(e.event_type, e.event_type)

            time_str = e.scheduled_at.strftime("%H:%M") if e.scheduled_at else ""

            if e.status == "responded":
                resp_label = MEAL_ESP.get(e.response, e.response)
                steps.append({"label": label, "done": True, "response": resp_label,
                              "time": e.responded_at.strftime("%H:%M") if e.responded_at else time_str,
                              "status": "responded"})
            elif e.status == "sent":
                steps.append({"label": label, "done": True, "response": "",
                              "time": e.sent_at.strftime("%H:%M") if e.sent_at else time_str,
                              "status": "sent"})
            elif e.status == "expired":
                steps.append({"label": label + " (sin respuesta)", "done": False, "response": "",
                              "time": time_str, "status": "expired"})
            else:
                steps.append({"label": label, "done": False, "response": "",
                              "time": time_str, "status": "pending"})

        if obj.fasting_required:
            from django.utils import timezone
            fasting_started = obj.fasting_start and timezone.now() >= obj.fasting_start
            steps.append({
                "label": "Ayuno " + ("iniciado" if fasting_started else "pendiente"),
                "done": fasting_started, "response": "",
                "time": obj.fasting_start.strftime("%H:%M") if obj.fasting_start else "",
                "status": "done" if fasting_started else "pending",
            })
        return steps

    def get_protocol_actions(self, obj):
        """Devuelve los eventos de almuerzo y cena que se pueden enviar manualmente."""
        from .models import ProtocolEvent, EVENT_MEAL_CHECK_LUNCH, EVENT_MEAL_CHECK_DINNER, EVENT_PENDING, EVENT_SENT, EVENT_RESPONDED
        actions = []
        for event in ProtocolEvent.objects.filter(
            appointment=obj,
            event_type__in=[EVENT_MEAL_CHECK_LUNCH, EVENT_MEAL_CHECK_DINNER],
        ).order_by("scheduled_at"):
            actions.append({
                "event_id": event.id,
                "type": event.event_type,
                "label": "Enviar check almuerzo (3 PM)" if event.event_type == EVENT_MEAL_CHECK_LUNCH else "Enviar check cena (7 PM)",
                "status": event.status,
                "can_send": event.status == EVENT_PENDING,
                "waiting_response": event.status == EVENT_SENT,
                "can_resend": event.status == EVENT_SENT,
                "responded": event.status == EVENT_RESPONDED,
                "response": event.response,
                "response_token": str(event.response_token),
            })
        return actions

    def get_fasting_start_fmt(self, obj):
        if obj.fasting_start:
            return obj.fasting_start.strftime("%H:%M")
        return "—"


class ReminderLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ReminderLog
        fields = ["id", "message", "channel", "sent_at"]


class ExamRulesSerializer(serializers.Serializer):
    """Expone las reglas de ayuno para que el frontend las use."""
    exam_type = serializers.CharField()
    required  = serializers.BooleanField()
    hours     = serializers.IntegerField()


# ─── Protocol Event serializer ──────────────────────────────────────────────────
from .models import ProtocolEvent

class ProtocolEventSerializer(serializers.ModelSerializer):
    event_label = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()

    class Meta:
        model  = ProtocolEvent
        fields = ["id", "event_type", "event_label", "scheduled_at",
                  "status", "status_label", "response", "sent_at", "responded_at"]

    EVENT_LABELS = {
        "guidance": "Guidance Sent",
        "meal_check_lunch": "Lunch Check",
        "meal_check_dinner": "Dinner Check",
        "followup_retry": "Follow-up Retry",
        "fasting_reminder": "Fasting Reminder",
    }
    STATUS_LABELS = {
        "pending": "Pending", "sent": "Sent",
        "responded": "Responded", "expired": "Expired",
    }

    def get_event_label(self, obj):
        return self.EVENT_LABELS.get(obj.event_type, obj.event_type)

    def get_status_label(self, obj):
        return self.STATUS_LABELS.get(obj.status, obj.status)
