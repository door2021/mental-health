"""
Django admin configuration for assessment models
"""
from django.contrib import admin
from .models import AssessmentSession, AssessmentResponse, AssessmentSummary


@admin.register(AssessmentSession)
class AssessmentSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user_identifier', 'status', 'created_at', 'updated_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user_identifier', 'id']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Session Information', {
            'fields': ('user_identifier', 'status')
        }),
        ('Metadata', {
            'fields': ('metadata',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AssessmentResponse)
class AssessmentResponseAdmin(admin.ModelAdmin):
    list_display = ['id', 'session', 'question_category', 'timestamp', 'response_preview']
    list_filter = ['question_category', 'timestamp']
    search_fields = ['session__id', 'response_text']
    readonly_fields = ['timestamp']

    def response_preview(self, obj):
        return obj.response_text[:100] + '...' if len(obj.response_text) > 100 else obj.response_text
    response_preview.short_description = 'Response'


@admin.register(AssessmentSummary)
class AssessmentSummaryAdmin(admin.ModelAdmin):
    list_display = ['session', 'completion_status', 'flagged_for_professional', 'created_at']
    list_filter = ['completion_status', 'flagged_for_professional', 'created_at']
    search_fields = ['session__id', 'summary_text']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Summary', {
            'fields': ('session', 'summary_text', 'completion_status')
        }),
        ('Review Information', {
            'fields': ('missing_info', 'areas_for_review', 'flagged_for_professional')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
