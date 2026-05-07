from django.contrib import admin
from .models import Patient, Appointment, PreparationStatus, ReminderLog, ProtocolEvent


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display  = ["name", "phone", "email", "created"]
    search_fields = ["name", "phone"]


class PreparationStatusInline(admin.TabularInline):
    model      = PreparationStatus
    extra      = 0
    can_delete = False

class ReminderLogInline(admin.TabularInline):
    model      = ReminderLog
    extra      = 0
    readonly_fields = ["message", "channel", "sent_at"]
    can_delete = False

class ProtocolEventInline(admin.TabularInline):
    model      = ProtocolEvent
    extra      = 0
    readonly_fields = ["event_type", "scheduled_at", "status", "response",
                       "sent_at", "responded_at", "retry_count", "response_token"]
    can_delete = False


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display  = ["patient", "exam_type", "scheduled_at",
                     "fasting_required", "fasting_hours",
                     "breakfast_type", "lunch_type", "dinner_type",
                     "preanalytic_risk", "fasting_start", "current_status"]
    list_filter   = ["fasting_required", "exam_type", "dinner_type", "preanalytic_risk", "status__status"]
    search_fields = ["patient__name"]
    readonly_fields = ["fasting_required", "fasting_hours", "meal_extra_hours",
                       "preanalytic_risk", "fasting_start", "confirm_token"]
    inlines       = [PreparationStatusInline, ProtocolEventInline, ReminderLogInline]

    def current_status(self, obj):
        return obj.current_status
    current_status.short_description = "Estado"


@admin.register(ProtocolEvent)
class ProtocolEventAdmin(admin.ModelAdmin):
    list_display  = ["appointment", "event_type", "scheduled_at", "status", "response", "retry_count"]
    list_filter   = ["event_type", "status"]
    search_fields = ["appointment__patient__name"]
    readonly_fields = ["response_token", "sent_at", "responded_at"]


@admin.register(PreparationStatus)
class PreparationStatusAdmin(admin.ModelAdmin):
    list_display = ["appointment", "status", "updated_at"]
    list_filter  = ["status"]


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ["appointment", "channel", "sent_at"]
    readonly_fields = ["sent_at"]
