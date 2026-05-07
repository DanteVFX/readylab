"""
Comando para crear un escenario de demo en vivo.
Crea una cita para mañana con todos los protocol events reprogramados
para que ocurran en los próximos minutos.

Uso:
  python manage.py demo_protocol
  python manage.py demo_protocol --phone "+51987379193" --name "Carlos Demo"
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from lab.models import (
    Patient, Appointment, ProtocolEvent, PreparationStatus,
    EVENT_PENDING, EVENT_SENT, EVENT_RESPONDED,
    STATUS_SCHEDULED,
)


class Command(BaseCommand):
    help = "Crea un escenario de demo con protocol events inmediatos"

    def add_arguments(self, parser):
        parser.add_argument("--name",  default="María García Demo", help="Nombre del paciente")
        parser.add_argument("--phone", default="+51987379193",      help="Teléfono (tu WhatsApp)")
        parser.add_argument("--exam",  default="Perfil lipídico",   help="Tipo de examen")

    def handle(self, *args, **options):
        now = timezone.now()

        # 1. Crear paciente
        patient, created = Patient.objects.get_or_create(
            phone=options["phone"],
            defaults={"name": options["name"]},
        )
        if not created:
            patient.name = options["name"]
            patient.save()

        self.stdout.write(f"\n{'═'*60}")
        self.stdout.write(f"  ReadyLab — Demo Protocol Setup")
        self.stdout.write(f"{'═'*60}")
        self.stdout.write(f"  Paciente: {patient.name}")
        self.stdout.write(f"  Teléfono: {patient.phone}")

        # 2. Crear cita para mañana 8:00 AM
        tomorrow_8am = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        appt = Appointment(
            patient=patient,
            exam_type=options["exam"],
            scheduled_at=tomorrow_8am,
            breakfast_type="light",
            lunch_type="normal",
            dinner_type="normal",
        )
        appt.save()

        self.stdout.write(f"  Examen:   {appt.exam_type}")
        self.stdout.write(f"  Cita:     {tomorrow_8am:%d/%m/%Y %H:%M}")
        self.stdout.write(f"  Ayuno:    {appt.total_fasting_hours}h")
        self.stdout.write(f"{'─'*60}")

        # 3. Reprogramar protocol events para los próximos minutos
        events = ProtocolEvent.objects.filter(appointment=appt).order_by("scheduled_at")

        schedule = [
            (0, "Guía preventiva — se envía AHORA"),
            (2, "Check de almuerzo — se envía en 2 min"),
            (4, "Check de cena — se envía en 4 min"),
            (6, "Recordatorio de ayuno — se envía en 6 min"),
        ]

        for i, event in enumerate(events):
            if i < len(schedule):
                mins, desc = schedule[i]
                event.scheduled_at = now + timedelta(minutes=mins)
                event.save()
                self.stdout.write(f"  ⏱️  +{mins} min | {desc}")
                self.stdout.write(f"       Tipo: {event.event_type}")
                self.stdout.write(f"       Token: {event.response_token}")
                if "meal_check" in event.event_type:
                    self.stdout.write(f"       Link respuesta:")
                    self.stdout.write(f"         http://localhost:8000/meal-check/{event.response_token}/?response=light")
                    self.stdout.write(f"         http://localhost:8000/meal-check/{event.response_token}/?response=normal")
                    self.stdout.write(f"         http://localhost:8000/meal-check/{event.response_token}/?response=high_fat")
                self.stdout.write("")

        self.stdout.write(f"{'═'*60}")
        self.stdout.write(f"  ✅ Demo lista. No necesitas hacer nada más.")
        self.stdout.write(f"")
        self.stdout.write(f"  1. Abre el dashboard → http://localhost:8000")
        self.stdout.write(f"  2. Los mensajes se envían solos cada 2 minutos")
        self.stdout.write(f"  3. Mira la terminal del servidor para ver los mensajes salir")
        self.stdout.write(f"  4. Cuando llegue el de almuerzo o cena, abre el link")
        self.stdout.write(f"     desde tu celular para responder")
        self.stdout.write(f"  5. El dashboard se actualiza solo cada 5 segundos")
        self.stdout.write(f"{'═'*60}\n")
