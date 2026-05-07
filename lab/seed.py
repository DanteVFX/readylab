"""
Script para poblar la base de datos con datos de prueba realistas.
Ejecutar con: python manage.py shell < lab/seed.py
O también: python manage.py runscript seed  (si usas django-extensions)
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'readylab.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from lab.models import Patient, Appointment, PreparationStatus

from lab.models import ProtocolEvent

# Limpia datos anteriores
ProtocolEvent.objects.all().delete()
PreparationStatus.objects.all().delete()
Appointment.objects.all().delete()
Patient.objects.all().delete()

now = timezone.now()

SEED_DATA = [
    # (nombre, teléfono, examen, delta_horas, estado_forzado)
    ("Ana Torres",       "+52 55 1001 0001", "Glucosa en ayuno",       1.0,  "At Risk"),
    ("Luis Mendoza",     "+52 55 1001 0002", "Perfil lipídico",        1.5,  "No Response"),
    ("Carmen Ruiz",      "+52 55 1001 0003", "BH completa",            2.0,  "Confirmed"),
    ("Jorge Salinas",    "+52 55 1001 0004", "Química sanguínea 6",    2.5,  "Prep Started"),
    ("Elena Vargas",     "+52 55 1001 0005", "Glucosa en ayuno",       3.0,  "Scheduled"),
    ("Miguel Flores",    "+52 55 1001 0006", "Perfil lipídico",        4.0,  "Confirmed"),
    ("Rosa Jiménez",     "+52 55 1001 0007", "BH completa",            5.0,  "Prep Started"),
    ("Pedro Castillo",   "+52 55 1001 0008", "Química sanguínea 24",   5.5,  "Confirmed"),
    ("Laura Herrera",    "+52 55 1001 0009", "Glucosa en ayuno",       6.0,  "Scheduled"),
    ("Diego Morales",    "+52 55 1001 0010", "Perfil lipídico",        7.0,  "Confirmed"),
    ("Sofía León",       "+52 55 1001 0011", "Hemoglobina glucosilada", 8.0, "Scheduled"),
]

for name, phone, exam, delta, forced_status in SEED_DATA:
    patient = Patient.objects.create(name=name, phone=phone)
    appt = Appointment(
        patient=patient,
        exam_type=exam,
        scheduled_at=now + timedelta(hours=delta),
    )
    appt.save()  # save() calcula ayuno automáticamente

    # Fuerza el estado para el demo
    prep = appt.status
    prep.status = forced_status
    prep.save()

print(f"✅ {len(SEED_DATA)} citas de prueba creadas correctamente.")
print("\nEstados:")
for s, count in [
    ("At Risk",      1), ("No Response", 1), ("Confirmed",    4),
    ("Prep Started", 2), ("Scheduled",   3),
]:
    print(f"  {s}: {count}")
