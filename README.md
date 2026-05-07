# ReadyLab — MVP Hackathon

Plataforma preanalítica que automatiza la preparación del paciente antes de análisis clínicos.

## Instalación rápida (5 minutos)

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Migraciones
python manage.py migrate

# 3. Datos de prueba
python manage.py shell < lab/seed.py

# 4. Superusuario admin
python manage.py createsuperuser
# o usar el que ya existe: admin / admin123

# 5. Arrancar servidor
python manage.py runserver
```

Abre: http://localhost:8000

## URLs clave

| URL | Descripción |
|-----|-------------|
| `/` | Dashboard del laboratorio |
| `/admin/` | Django admin (admin / admin123) |
| `/api/appointments/` | GET lista de citas con conteos |
| `/api/appointments/create/` | POST crear nueva cita |
| `/api/appointments/<id>/remind/` | POST enviar recordatorio manual |
| `/api/exam-rules/` | GET reglas de ayuno por examen |
| `/api/trigger-engine/` | POST ejecutar motor de estados ahora |
| `/confirm/<token>/` | GET confirmación del paciente (link del SMS) |

## Flujo del demo (3 minutos)

1. Mostrar dashboard con pacientes en diferentes estados
2. Clic en tarjetas de conteo para filtrar por estado
3. Crear nueva cita con `+ Nuevo paciente` — elegir examen con ayuno
4. Mostrar que calcula el inicio de ayuno automáticamente
5. Llamar `POST /api/trigger-engine/` para forzar transición de estados en vivo
6. Abrir link de confirmación desde celular → estado cambia a Confirmed en 5s

## Arquitectura

```
readylab/
├── readylab/           # Configuración Django
│   ├── settings.py
│   └── urls.py
├── lab/                # App principal
│   ├── models.py       # Patient, Appointment, PreparationStatus, ReminderLog
│   ├── engine.py       # Motor de estados + APScheduler
│   ├── serializers.py  # DRF serializers
│   ├── views.py        # API REST + dashboard + confirmación
│   ├── admin.py        # Django admin
│   └── seed.py         # Datos de prueba
└── templates/
    ├── dashboard.html  # Dashboard del laboratorio
    └── confirm.html    # Página de confirmación del paciente
```

## Motor de estados

```
Scheduled → Prep Started   cuando now >= fasting_start - 1h   (envía SMS)
Prep Started → No Response cuando han pasado 30 min sin confirmar
No Response → At Risk      cuando faltan ≤ 60 min para la cita
* → Confirmed              cuando el paciente abre /confirm/<token>/
```

## Reglas de ayuno (FASTING_RULES en models.py)

| Examen | Ayuno | Horas |
|--------|-------|-------|
| Glucosa en ayuno | Sí | 8 h |
| Perfil lipídico | Sí | 12 h |
| Química sanguínea 6/24 | Sí | 8 h |
| Hemoglobina glucosilada | Sí | 8 h |
| BH completa | No | — |
| Examen general de orina | No | — |

## Para producción (después del hackathon)

- Reemplazar `simulate_send()` en `engine.py` con Twilio SMS o WhatsApp Business API
- Cambiar SQLite por PostgreSQL en `settings.py`
- Agregar autenticación de laboratorio con `django-allauth`
- Desplegar en Railway, Render, o Fly.io (gratis tier disponible)
