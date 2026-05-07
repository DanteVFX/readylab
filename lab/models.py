import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta

# ─── Meal profile ───────────────────────────────────────────────────────────────
MEAL_LIGHT  = "light"
MEAL_NORMAL = "normal"
MEAL_HIGH_FAT = "high_fat"

MEAL_PROFILE_CHOICES = [
    (MEAL_LIGHT,    "Light Meal (ensalada, fruta, caldo)"),
    (MEAL_NORMAL,   "Normal Meal (comida regular)"),
    (MEAL_HIGH_FAT, "High Fat Meal (grasas, fritos, carnes)"),
]

# Exámenes sensibles a grasas → +2 h si High Fat Meal
MEAL_SENSITIVE_EXAMS = {"Perfil lipídico", "Química sanguínea 6", "Química sanguínea 24"}

def meal_extra_hours(meal_profile: str, exam_type: str) -> int:
    """Devuelve las horas extra de ayuno según el perfil de comida y el examen."""
    if meal_profile == MEAL_HIGH_FAT and exam_type in MEAL_SENSITIVE_EXAMS:
        return 2
    return 0


# ─── Riesgo preanalítico ────────────────────────────────────────────────────────
RISK_LOW      = "low"
RISK_ELEVATED = "elevated"

RISK_CHOICES = [
    (RISK_LOW,      "Low Risk"),
    (RISK_ELEVATED, "Elevated Risk"),
]

def compute_preanalytic_risk(dinner_type: str) -> str:
    """Regla simple: High Fat dinner → Elevated Risk, cualquier otra → Low."""
    return RISK_ELEVATED if dinner_type == MEAL_HIGH_FAT else RISK_LOW

# ─── Reglas preanalíticas por tipo de examen ───────────────────────────────────
FASTING_RULES = {
    "Glucosa en ayuno": {
        "required": True, "hours": 8,
        "instructions": "No consumas alimentos ni bebidas azucaradas. Solo agua.",
        "avoid": "dulces, jugos, refrescos, pan dulce, frutas muy dulces",
    },
    "Perfil lipídico": {
        "required": True, "hours": 12,
        "instructions": "Este examen mide las grasas en tu sangre (colesterol, triglicéridos). "
                        "Los lípidos de la comida tardan varias horas en procesarse, por eso "
                        "el ayuno es más largo que en otros exámenes.",
        "avoid": "frituras, mantequilla, quesos grasos, carnes grasas, comida rápida, alcohol",
    },
    "Química sanguínea 6": {
        "required": True, "hours": 8,
        "instructions": "Evalúa glucosa, urea, creatinina y más. Requiere ayuno estricto.",
        "avoid": "alimentos pesados, alcohol, exceso de sal",
    },
    "Química sanguínea 24": {
        "required": True, "hours": 8,
        "instructions": "Panel completo de 24 parámetros. Requiere ayuno estricto.",
        "avoid": "alimentos pesados, alcohol, exceso de sal",
    },
    "Hemoglobina glucosilada": {
        "required": True, "hours": 8,
        "instructions": "Mide el promedio de azúcar en sangre de los últimos 3 meses.",
        "avoid": "dulces, bebidas azucaradas",
    },
    "BH completa": {
        "required": False, "hours": 0,
        "instructions": "No requiere ayuno. Puedes comer con normalidad.",
        "avoid": "",
    },
    "Examen general de orina": {
        "required": False, "hours": 0,
        "instructions": "No requiere ayuno. Se recomienda recolectar la primera orina de la mañana.",
        "avoid": "",
    },
    "Prueba de función tiroidea": {
        "required": False, "hours": 0,
        "instructions": "No requiere ayuno. Si tomas levotiroxina, tómala después de la extracción.",
        "avoid": "",
    },
}

EXAM_CHOICES = [(k, k) for k in FASTING_RULES]

# ─── Estados del paciente ───────────────────────────────────────────────────────
STATUS_SCHEDULED       = "Scheduled"
STATUS_GUIDANCE_SENT   = "Guidance Sent"
STATUS_AWAITING_MEAL   = "Awaiting Meal"
STATUS_PREP_STARTED    = "Prep Started"
STATUS_CONFIRMED       = "Confirmed"
STATUS_NO_RESPONSE     = "No Response"
STATUS_NO_RESPONSE_RISK = "No Response Risk"
STATUS_AT_RISK         = "At Risk"

STATUS_CHOICES = [
    (STATUS_SCHEDULED,       "Programado"),
    (STATUS_GUIDANCE_SENT,   "Guía enviada"),
    (STATUS_AWAITING_MEAL,   "Esperando confirmación comida"),
    (STATUS_PREP_STARTED,    "En preparación"),
    (STATUS_CONFIRMED,       "Confirmado"),
    (STATUS_NO_RESPONSE,     "Sin respuesta"),
    (STATUS_NO_RESPONSE_RISK, "Riesgo sin respuesta"),
    (STATUS_AT_RISK,         "En riesgo"),
]


class Patient(models.Model):
    name    = models.CharField("Nombre completo", max_length=120)
    phone   = models.CharField("Teléfono", max_length=20)
    email   = models.EmailField("Correo electrónico", blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Paciente"
        verbose_name_plural = "Pacientes"
        ordering = ["-created"]

    def __str__(self):
        return self.name


class Appointment(models.Model):
    patient         = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="appointments")
    exam_type       = models.CharField("Tipo de análisis", max_length=60, choices=EXAM_CHOICES)
    scheduled_at    = models.DateTimeField("Fecha y hora de cita")
    fasting_required  = models.BooleanField("Requiere ayuno", default=False)
    fasting_hours     = models.PositiveIntegerField("Horas de ayuno base", default=0)
    fasting_start     = models.DateTimeField("Inicio de ayuno", null=True, blank=True)
    # Perfil alimentario completo del paciente (3 comidas)
    breakfast_type    = models.CharField(
        "Desayuno", max_length=10, choices=MEAL_PROFILE_CHOICES, default=MEAL_LIGHT,
    )
    lunch_type        = models.CharField(
        "Almuerzo", max_length=10, choices=MEAL_PROFILE_CHOICES, default=MEAL_NORMAL,
    )
    dinner_type       = models.CharField(
        "Cena (última comida)", max_length=10, choices=MEAL_PROFILE_CHOICES, default=MEAL_NORMAL,
    )
    preanalytic_risk  = models.CharField(
        "Riesgo preanalítico", max_length=10, choices=RISK_CHOICES, default=RISK_LOW,
    )
    # Retrocompatibilidad: meal_profile apunta a dinner (la comida relevante)
    meal_profile      = models.CharField(
        "Perfil de última comida",
        max_length=10,
        choices=MEAL_PROFILE_CHOICES,
        default=MEAL_NORMAL,
    )
    meal_extra_hours  = models.PositiveIntegerField("Horas extra por comida", default=0)
    confirm_token     = models.UUIDField("Token de confirmación", default=uuid.uuid4, unique=True)
    created         = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cita"
        verbose_name_plural = "Citas"
        ordering = ["scheduled_at"]

    def save(self, *args, **kwargs):
        # 1. Reglas base por tipo de examen
        rule = FASTING_RULES.get(self.exam_type, {"required": False, "hours": 0})
        self.fasting_required = rule["required"]
        self.fasting_hours    = rule["hours"]

        # 2. Sincronizar meal_profile con dinner (la comida relevante para ayuno)
        self.meal_profile = self.dinner_type

        # 3. Riesgo preanalítico basado en la cena
        self.preanalytic_risk = compute_preanalytic_risk(self.dinner_type)

        # 4. Ajuste dinámico por perfil de comida
        self.meal_extra_hours = meal_extra_hours(self.meal_profile, self.exam_type)
        total_hours = self.fasting_hours + self.meal_extra_hours

        if self.fasting_required:
            self.fasting_start = self.scheduled_at - timedelta(hours=total_hours)
        else:
            self.fasting_start = None
        super().save(*args, **kwargs)
        # Crea el estado inicial si no existe
        PreparationStatus.objects.get_or_create(
            appointment=self,
            defaults={"status": STATUS_SCHEDULED}
        )

        # Genera eventos del protocolo si es nueva (sin eventos previos)
        if not self.protocol_events.exists():
            create_protocol_events(self)

    @property
    def risk_label(self):
        """Etiqueta legible del riesgo preanalítico."""
        return "Elevated" if self.preanalytic_risk == RISK_ELEVATED else "Low"

    @property
    def total_fasting_hours(self):
        """Horas base + horas extra por perfil de comida."""
        return self.fasting_hours + self.meal_extra_hours

    @property
    def current_status(self):
        try:
            return self.status.status
        except PreparationStatus.DoesNotExist:
            return STATUS_SCHEDULED

    @property
    def minutes_to_appointment(self):
        delta = self.scheduled_at - timezone.now()
        return int(delta.total_seconds() / 60)

    def __str__(self):
        return f"{self.patient.name} — {self.exam_type} ({self.scheduled_at:%d/%m %H:%M})"


class PreparationStatus(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="status")
    status      = models.CharField("Estado", max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Estado de preparación"
        verbose_name_plural = "Estados de preparación"

    def __str__(self):
        return f"{self.appointment} → {self.status}"


class ReminderLog(models.Model):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="reminders")
    message     = models.TextField("Mensaje enviado")
    channel     = models.CharField("Canal", max_length=20, default="SMS")
    sent_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Recordatorio"
        verbose_name_plural = "Recordatorios"
        ordering = ["-sent_at"]

    def __str__(self):
        return f"[{self.channel}] {self.appointment.patient.name} — {self.sent_at:%H:%M}"


# ─── Protocolo automatizado de seguimiento ─────────────────────────────────────

EVENT_GUIDANCE        = "guidance"          # Día anterior: guía preventiva
EVENT_MEAL_CHECK_LUNCH = "meal_check_lunch" # Mismo día: check de almuerzo
EVENT_MEAL_CHECK_DINNER = "meal_check_dinner" # Check de cena
EVENT_FOLLOWUP_RETRY  = "followup_retry"    # Re-envío por no respuesta
EVENT_FASTING_REMINDER = "fasting_reminder" # Recordatorio de inicio de ayuno

EVENT_TYPE_CHOICES = [
    (EVENT_GUIDANCE,          "Guía preventiva"),
    (EVENT_MEAL_CHECK_LUNCH,  "Check almuerzo"),
    (EVENT_MEAL_CHECK_DINNER, "Check cena"),
    (EVENT_FOLLOWUP_RETRY,    "Re-envío follow-up"),
    (EVENT_FASTING_REMINDER,  "Recordatorio ayuno"),
]

EVENT_PENDING   = "pending"
EVENT_SENT      = "sent"
EVENT_RESPONDED = "responded"
EVENT_EXPIRED   = "expired"

EVENT_STATUS_CHOICES = [
    (EVENT_PENDING,   "Pendiente"),
    (EVENT_SENT,      "Enviado"),
    (EVENT_RESPONDED, "Respondido"),
    (EVENT_EXPIRED,   "Expirado"),
]


class ProtocolEvent(models.Model):
    """
    Cada evento programado en el protocolo de seguimiento del paciente.
    Se crean al registrar la cita y se ejecutan por el scheduler.
    """
    appointment   = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="protocol_events")
    event_type    = models.CharField("Tipo de evento", max_length=24, choices=EVENT_TYPE_CHOICES)
    scheduled_at  = models.DateTimeField("Hora programada")
    status        = models.CharField("Estado", max_length=12, choices=EVENT_STATUS_CHOICES, default=EVENT_PENDING)
    message       = models.TextField("Mensaje", blank=True)
    response      = models.CharField("Respuesta del paciente", max_length=20, blank=True)
    response_token = models.UUIDField("Token de respuesta", default=uuid.uuid4, unique=True)
    sent_at       = models.DateTimeField(null=True, blank=True)
    responded_at  = models.DateTimeField(null=True, blank=True)
    retry_count   = models.PositiveIntegerField(default=0)
    created       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento de protocolo"
        verbose_name_plural = "Eventos de protocolo"
        ordering = ["scheduled_at"]

    @property
    def is_done(self):
        return self.status in (EVENT_RESPONDED, EVENT_EXPIRED)

    def __str__(self):
        return f"[{self.event_type}] {self.appointment.patient.name} @ {self.scheduled_at:%d/%m %H:%M} ({self.status})"


def create_protocol_events(appointment):
    """
    Genera todos los eventos del protocolo al crear una cita.
    Los mensajes incluyen links para que el paciente responda con un clic.
    El {base_url} se reemplaza al momento de enviar.
    """
    appt_dt = appointment.scheduled_at
    day_before_morning = (appt_dt - timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    day_before_lunch   = (appt_dt - timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
    day_before_dinner  = (appt_dt - timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)

    nombre = appointment.patient.name.split()[0]
    examen = appointment.exam_type
    horas  = appointment.fasting_hours
    hora_cita = appt_dt.strftime("%H:%M")

    # Se crean los eventos; los tokens de respuesta se generan automáticamente
    # Obtener indicaciones específicas del examen
    rule = FASTING_RULES.get(examen, {})
    instrucciones = rule.get("instructions", "")
    evitar = rule.get("avoid", "")

    if horas > 0:
        # Examen CON ayuno
        guidance_msg = (
            f"👋 *¡Bienvenido a ReadyLab!*\n\n"
            f"Hola {nombre}, soy tu asistente de preparación para tu examen de laboratorio.\n\n"
            f"🗓️ Tu cita de *{examen}* es *mañana a las {hora_cita}*.\n\n"
            f"📋 *Sobre tu examen:*\n"
            f"{instrucciones}\n\n"
            f"⏱️ *Ayuno requerido:* {horas} horas\n\n"
            f"*¿Qué debes hacer hoy?*\n"
            f"• Sigue tu alimentación normal durante el día\n"
            f"• Puedes tomar agua sin problema\n"
            f"• Toma tus medicamentos como de costumbre\n"
        )
        if evitar:
            guidance_msg += f"\n⚠️ *Evita hoy:* {evitar}\n"
        guidance_msg += (
            f"\nMás tarde te preguntaré sobre tus comidas para calcular "
            f"tu ayuno de forma personalizada. 🙂"
        )
    else:
        # Examen SIN ayuno
        guidance_msg = (
            f"👋 *¡Bienvenido a ReadyLab!*\n\n"
            f"Hola {nombre}, soy tu asistente de preparación para tu examen de laboratorio.\n\n"
            f"🗓️ Tu cita de *{examen}* es *mañana a las {hora_cita}*.\n\n"
            f"✅ *Buenas noticias:* este examen *no requiere ayuno*.\n\n"
            f"📋 *Indicaciones:*\n"
            f"{instrucciones}\n\n"
            f"¡Te esperamos mañana! 🙂"
        )

    guidance_event = ProtocolEvent(
        appointment=appointment,
        event_type=EVENT_GUIDANCE,
        scheduled_at=day_before_morning,
        message=guidance_msg,
    )

    lunch_event = ProtocolEvent(
        appointment=appointment,
        event_type=EVENT_MEAL_CHECK_LUNCH,
        scheduled_at=day_before_lunch,
    )

    dinner_event = ProtocolEvent(
        appointment=appointment,
        event_type=EVENT_MEAL_CHECK_DINNER,
        scheduled_at=day_before_dinner,
    )

    events = [guidance_event, lunch_event, dinner_event]

    if appointment.fasting_start:
        fasting_event = ProtocolEvent(
            appointment=appointment,
            event_type=EVENT_FASTING_REMINDER,
            scheduled_at=appointment.fasting_start - timedelta(hours=1),
            message=(
                f"⏰ *ReadyLab — ¡Tu ayuno está por comenzar!*\n\n"
                f"Hola {nombre}, en una hora inicia tu período de ayuno.\n\n"
                f"🕐 *Inicio de ayuno:* {appointment.fasting_start:%H:%M} hrs\n"
                f"⏱️ *Duración:* {appointment.total_fasting_hours} horas\n"
                f"🗓️ *Tu cita:* mañana a las {hora_cita}\n\n"
                f"A partir de las {appointment.fasting_start:%H:%M} no consumas alimentos ni bebidas, excepto agua.\n\n"
                f"¡Estás muy cerca! Gracias por prepararte con ReadyLab. 💪"
            ),
        )
        events.append(fasting_event)

    ProtocolEvent.objects.bulk_create(events)

    # Ahora que tienen PK y tokens, generar mensajes con links para los meal checks
    for event in ProtocolEvent.objects.filter(
        appointment=appointment,
        event_type__in=[EVENT_MEAL_CHECK_LUNCH, EVENT_MEAL_CHECK_DINNER],
    ):
        token = event.response_token

        if event.event_type == EVENT_MEAL_CHECK_LUNCH:
            event.message = (
                f"🍽️ *ReadyLab — ¿Ya almorzaste?*\n\n"
                f"Hola {nombre}, cuéntanos cómo fue tu almuerzo de hoy.\n"
                f"Toca la opción que mejor lo describa:\n\n"
                f"🥗 *Almuerzo ligero* (ensalada, fruta, sopa, pollo a la plancha)\n"
                f"→ {{base_url}}/meal-check/{token}/?response=light\n\n"
                f"🍛 *Almuerzo normal* (arroz, menestra, carne, guiso casero)\n"
                f"→ {{base_url}}/meal-check/{token}/?response=normal\n\n"
                f"🍔 *Almuerzo pesado* (frituras, cerdo, comida rápida, buffet)\n"
                f"→ {{base_url}}/meal-check/{token}/?response=high_fat"
            )
        else:
            event.message = (
                f"🌙 *ReadyLab — ¿Ya cenaste?*\n\n"
                f"Hola {nombre}, cuéntanos cómo fue tu cena.\n"
                f"Esta es tu última comida antes del ayuno.\n\n"
                f"🥗 *Cena ligera* (ensalada, yogurt, fruta, caldo)\n"
                f"→ {{base_url}}/meal-check/{token}/?response=light\n\n"
                f"🍛 *Cena normal* (comida casera, arroz, pollo)\n"
                f"→ {{base_url}}/meal-check/{token}/?response=normal\n\n"
                f"🍔 *Cena pesada* (frituras, carnes grasas, comida rápida)\n"
                f"→ {{base_url}}/meal-check/{token}/?response=high_fat\n\n"
                f"⚠️ Si cenaste pesado, tu ayuno se extenderá automáticamente para proteger la precisión de tus resultados."
            )
        event.save()
