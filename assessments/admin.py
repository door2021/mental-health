"""
Django admin configuration for assessment models
"""
from django.contrib import admin
from .models import (
    # New scale-based models
    PsychometricScale,
    ScaleItem,
    SeverityCutoff,
    ScaleResponse,
    ScaleScore,
    FreeTextResponse,
    GroundedSummary,
    # Session and legacy models
    AssessmentSession,
    AssessmentResponse,
    AssessmentSummary,
)


# =============================================================================
# PSYCHOMETRIC SCALE ADMIN
# =============================================================================

class ScaleItemInline(admin.TabularInline):
    model = ScaleItem
    extra = 0
    fields = ['item_number', 'question_text', 'min_value', 'max_value',
              'is_reverse_scored', 'is_critical', 'critical_threshold']
    ordering = ['item_number']


class SeverityCutoffInline(admin.TabularInline):
    model = SeverityCutoff
    extra = 0
    fields = ['severity_level', 'min_score', 'max_score', 'clinical_interpretation']
    ordering = ['min_score']


@admin.register(PsychometricScale)
class PsychometricScaleAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'scale_type', 'min_score', 'max_score',
                    'is_active', 'order', 'item_count']
    list_filter = ['scale_type', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['order', 'code']
    inlines = [ScaleItemInline, SeverityCutoffInline]

    fieldsets = (
        ('Scale Information', {
            'fields': ('code', 'name', 'description', 'scale_type')
        }),
        ('Scoring', {
            'fields': ('min_score', 'max_score')
        }),
        ('Configuration', {
            'fields': ('is_active', 'order')
        }),
        ('Citation', {
            'fields': ('citation',),
            'classes': ('collapse',)
        }),
    )

    def item_count(self, obj):
        return obj.get_item_count()
    item_count.short_description = 'Items'


@admin.register(ScaleItem)
class ScaleItemAdmin(admin.ModelAdmin):
    list_display = ['scale', 'item_number', 'question_preview', 'is_reverse_scored',
                    'is_critical', 'critical_threshold']
    list_filter = ['scale', 'is_reverse_scored', 'is_critical']
    search_fields = ['question_text', 'scale__code']
    ordering = ['scale', 'item_number']

    def question_preview(self, obj):
        return obj.question_text[:60] + '...' if len(obj.question_text) > 60 else obj.question_text
    question_preview.short_description = 'Question'


@admin.register(SeverityCutoff)
class SeverityCutoffAdmin(admin.ModelAdmin):
    list_display = ['scale', 'severity_level', 'min_score', 'max_score', 'interpretation_preview']
    list_filter = ['scale', 'severity_level']
    ordering = ['scale', 'min_score']

    def interpretation_preview(self, obj):
        return obj.clinical_interpretation[:60] + '...' if len(obj.clinical_interpretation) > 60 else obj.clinical_interpretation
    interpretation_preview.short_description = 'Interpretation'


# =============================================================================
# SCALE RESPONSE AND SCORE ADMIN
# =============================================================================

@admin.register(ScaleResponse)
class ScaleResponseAdmin(admin.ModelAdmin):
    list_display = ['session', 'item', 'numeric_value', 'scored_value', 'timestamp', 'has_verbatim']
    list_filter = ['item__scale', 'timestamp']
    search_fields = ['session__id', 'item__scale__code']
    readonly_fields = ['scored_value', 'timestamp']
    ordering = ['-timestamp']

    def has_verbatim(self, obj):
        return bool(obj.verbatim_text)
    has_verbatim.boolean = True
    has_verbatim.short_description = 'Has Text'


@admin.register(ScaleScore)
class ScaleScoreAdmin(admin.ModelAdmin):
    list_display = ['session', 'scale', 'total_score', 'max_possible_score',
                    'severity_level', 'has_critical_response', 'computed_at']
    list_filter = ['scale', 'severity_level', 'has_critical_response']
    search_fields = ['session__id', 'scale__code']
    readonly_fields = ['computed_at']
    ordering = ['-computed_at']

    fieldsets = (
        ('Score Information', {
            'fields': ('session', 'scale', 'total_score', 'max_possible_score',
                      'percentage_score', 'severity_level')
        }),
        ('Clinical Details', {
            'fields': ('clinical_interpretation', 'subscale_scores')
        }),
        ('Critical Flags', {
            'fields': ('has_critical_response', 'critical_item_details')
        }),
        ('Metadata', {
            'fields': ('computed_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(FreeTextResponse)
class FreeTextResponseAdmin(admin.ModelAdmin):
    list_display = ['session', 'context_type', 'related_scale', 'response_preview', 'timestamp']
    list_filter = ['context_type', 'related_scale', 'timestamp']
    search_fields = ['session__id', 'response_text']
    readonly_fields = ['timestamp']

    def response_preview(self, obj):
        return obj.response_text[:80] + '...' if len(obj.response_text) > 80 else obj.response_text
    response_preview.short_description = 'Response'


# =============================================================================
# GROUNDED SUMMARY ADMIN
# =============================================================================

@admin.register(GroundedSummary)
class GroundedSummaryAdmin(admin.ModelAdmin):
    list_display = ['session', 'completion_status', 'is_verified',
                    'requires_professional_review', 'created_at']
    list_filter = ['completion_status', 'is_verified', 'requires_professional_review']
    search_fields = ['session__id', 'narrative_summary']
    readonly_fields = ['created_at', 'updated_at', 'verification_timestamp']

    fieldsets = (
        ('Session', {
            'fields': ('session',)
        }),
        ('Computed Scores (NO LLM)', {
            'fields': ('score_summary', 'severity_summary'),
            'description': 'Deterministic scores computed from responses'
        }),
        ('Narrative Summary (LLM-Generated)', {
            'fields': ('narrative_summary', 'cited_quotes'),
            'description': 'LLM-generated content that is fact-checked'
        }),
        ('Verification Results', {
            'fields': ('is_verified', 'verification_errors', 'verification_warnings',
                      'verification_timestamp'),
            'classes': ('collapse',)
        }),
        ('Review Status', {
            'fields': ('requires_professional_review', 'review_reasons',
                      'completion_status', 'missing_scales')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# =============================================================================
# SESSION ADMIN (Updated)
# =============================================================================

class ScaleResponseInline(admin.TabularInline):
    model = ScaleResponse
    extra = 0
    readonly_fields = ['item', 'numeric_value', 'scored_value', 'timestamp']
    can_delete = False
    max_num = 0  # Prevents adding new inline items


class ScaleScoreInline(admin.TabularInline):
    model = ScaleScore
    extra = 0
    readonly_fields = ['scale', 'total_score', 'severity_level', 'has_critical_response']
    can_delete = False
    max_num = 0


@admin.register(AssessmentSession)
class AssessmentSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user_identifier', 'status', 'phase', 'is_legacy',
                    'completion_pct', 'created_at', 'updated_at']
    list_filter = ['status', 'phase', 'created_at']
    search_fields = ['user_identifier', 'id']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['assigned_scales']
    inlines = [ScaleScoreInline]

    fieldsets = (
        ('Session Information', {
            'fields': ('user_identifier', 'status', 'phase')
        }),
        ('Scale-Based Assessment', {
            'fields': ('assigned_scales', 'current_scale', 'current_item_number'),
            'description': 'Configuration for new scale-based assessments'
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def is_legacy(self, obj):
        return obj.is_legacy_format()
    is_legacy.boolean = True
    is_legacy.short_description = 'Legacy'

    def completion_pct(self, obj):
        return f"{obj.get_completion_percentage()}%"
    completion_pct.short_description = 'Complete'


# =============================================================================
# LEGACY MODEL ADMIN
# =============================================================================

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
