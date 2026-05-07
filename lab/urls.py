from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),

    # Confirmación del paciente (link en el SMS)
    path("confirm/<uuid:token>/", views.confirm_preparation, name="confirm"),

    # API REST
    path("api/appointments/",           views.appointments_list,   name="api-list"),
    path("api/appointments/create/",    views.appointments_create, name="api-create"),
    path("api/appointments/<int:appointment_id>/remind/",
                                        views.send_manual_reminder, name="api-remind"),
    path("api/exam-rules/",             views.exam_rules,          name="api-rules"),
    path("api/appointments/<int:appointment_id>/protocol/",
                                        views.protocol_events_list, name="api-protocol"),
    path("api/protocol-event/<int:event_id>/send/",
                                        views.send_protocol_event, name="api-send-event"),
    path("api/protocol-event/<int:event_id>/resend/",
                                        views.resend_protocol_event, name="api-resend-event"),
    path("api/trigger-engine/",         views.trigger_engine,      name="api-trigger"),

    # Patient-facing meal check response
    path("meal-check/<uuid:token>/",    views.meal_check_respond,  name="meal-check"),
]
