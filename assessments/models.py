"""
Database models for Mental Health Assessment System
Includes both legacy models and new psychometric scale-based models
"""
from django.db import models
from django.utils import timezone


# =============================================================================
# PSYCHOMETRIC SCALE MODELS (New Scale-Based System)
# =============================================================================

class PsychometricScale(models.Model):
    """
    Stores validated psychometric scale definitions.
    Data-driven approach - scales are configured in the database, not hardcoded.
    """
    SCALE_TYPE_CHOICES = [
        ('depression', 'Depression'),
        ('anxiety', 'Anxiety'),
        ('stress', 'Stress'),
        ('sleep', 'Sleep/Insomnia'),
    ]

    code = models.CharField(max_length=20, unique=True, help_text="Short code e.g., 'PHQ9', 'GAD7'")
    name = models.CharField(max_length=255, help_text="Full name e.g., 'Patient Health Questionnaire-9'")
    description = models.TextField(blank=True)
    scale_type = models.CharField(max_length=20, choices=SCALE_TYPE_CHOICES)
    min_score = models.IntegerField(default=0)
    max_score = models.IntegerField()
    citation = models.TextField(blank=True, help_text="Academic reference for the scale")
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0, help_text="Order in which scales are administered")
    created_at = models.DateTimeField(default=timezone.now, blank=True)
    updated_at = models.DateTimeField(default=timezone.now, blank=True)

    class Meta:
        ordering = ['order', 'code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def get_item_count(self):
        return self.items.count()


class ScaleItem(models.Model):
    """
    Individual questions within a psychometric scale.
    """
    scale = models.ForeignKey(
        PsychometricScale,
        on_delete=models.CASCADE,
        related_name='items'
    )
    item_number = models.PositiveIntegerField()
    question_text = models.TextField()
    response_options = models.JSONField(
        help_text='List of options: [{"value": 0, "label": "Not at all"}, ...]'
    )
    min_value = models.IntegerField(default=0)
    max_value = models.IntegerField(default=3)
    is_reverse_scored = models.BooleanField(
        default=False,
        help_text="If true, scoring is reversed (e.g., max_value - response)"
    )
    weight = models.FloatField(default=1.0, help_text="Weight multiplier for scoring")
    subscale = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional grouping within scale (e.g., 'cognitive', 'somatic')"
    )
    is_critical = models.BooleanField(
        default=False,
        help_text="If true, responses above threshold trigger immediate review (e.g., suicide item)"
    )
    critical_threshold = models.IntegerField(
        null=True,
        blank=True,
        help_text="Value at or above which response is flagged (for critical items)"
    )

    class Meta:
        ordering = ['scale', 'item_number']
        unique_together = ['scale', 'item_number']

    def __str__(self):
        return f"{self.scale.code} Q{self.item_number}"

    def get_scored_value(self, raw_value):
        """
        Compute the scored value, handling reverse scoring.
        """
        if self.is_reverse_scored:
            return self.max_value - raw_value
        return raw_value


class SeverityCutoff(models.Model):
    """
    Clinical cutoff points for severity classification.
    """
    SEVERITY_CHOICES = [
        ('minimal', 'Minimal/None'),
        ('mild', 'Mild'),
        ('moderate', 'Moderate'),
        ('moderately_severe', 'Moderately Severe'),
        ('severe', 'Severe'),
    ]

    scale = models.ForeignKey(
        PsychometricScale,
        on_delete=models.CASCADE,
        related_name='cutoffs'
    )
    severity_level = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    min_score = models.IntegerField()
    max_score = models.IntegerField()
    clinical_interpretation = models.TextField(
        help_text="Clinical meaning of this severity level"
    )
    recommended_action = models.TextField(
        blank=True,
        help_text="Recommended clinical action for this severity"
    )

    class Meta:
        ordering = ['scale', 'min_score']
        unique_together = ['scale', 'severity_level']

    def __str__(self):
        return f"{self.scale.code}: {self.severity_level} ({self.min_score}-{self.max_score})"


# =============================================================================
# SESSION MODEL (Updated with scale support)
# =============================================================================

class AssessmentSession(models.Model):
    """
    Tracks individual assessment sessions with status and metadata.
    Updated to support both legacy free-form and new scale-based assessments.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('requires_review', 'Requires Review'),
    ]

    PHASE_CHOICES = [
        ('introduction', 'Introduction'),
        ('scales', 'Administering Scales'),
        ('follow_up', 'Follow-up Questions'),
        ('summary', 'Generating Summary'),
        ('review', 'Professional Review'),
        ('completed', 'Completed'),
    ]

    id = models.AutoField(primary_key=True)
    user_identifier = models.CharField(max_length=255, help_text="Anonymous identifier for the user")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)

    # New fields for scale-based assessment
    assigned_scales = models.ManyToManyField(
        PsychometricScale,
        blank=True,
        related_name='sessions',
        help_text="Scales assigned to this assessment"
    )
    current_scale = models.ForeignKey(
        PsychometricScale,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_sessions',
        help_text="Scale currently being administered"
    )
    current_item_number = models.PositiveIntegerField(
        default=1,
        help_text="Current item number within the current scale"
    )
    phase = models.CharField(
        max_length=20,
        choices=PHASE_CHOICES,
        default='introduction',
        help_text="Current phase of the assessment workflow"
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Assessment {self.id} - {self.user_identifier} ({self.status})"

    def is_legacy_format(self):
        """Check if this is a legacy (pre-scale) assessment"""
        return self.metadata.get('legacy_format', False) or not self.assigned_scales.exists()

    def get_responses_by_category(self):
        """Group legacy responses by category (for backwards compatibility)"""
        responses = {}
        for response in self.responses.all():
            if response.question_category not in responses:
                responses[response.question_category] = []
            responses[response.question_category].append(response)
        return responses

    def is_complete(self):
        """Check if assessment is complete"""
        if self.is_legacy_format():
            # Legacy check
            required_categories = ['mood', 'stress', 'sleep', 'anxiety', 'daily_activities', 'concerns']
            existing_categories = set(self.responses.values_list('question_category', flat=True))
            return all(cat in existing_categories for cat in required_categories)
        else:
            # Scale-based check
            return self.phase == 'completed'

    def get_completion_percentage(self):
        """Calculate completion percentage for scale-based assessments"""
        if self.is_legacy_format():
            required_categories = ['mood', 'stress', 'sleep', 'anxiety', 'daily_activities', 'concerns']
            existing_categories = set(self.responses.values_list('question_category', flat=True))
            return int((len(existing_categories) / len(required_categories)) * 100)

        total_items = sum(scale.get_item_count() for scale in self.assigned_scales.all())
        if total_items == 0:
            return 0
        completed_items = self.scale_responses.count()
        return int((completed_items / total_items) * 100)


# =============================================================================
# SCALE RESPONSE MODELS (New)
# =============================================================================

class ScaleResponse(models.Model):
    """
    Individual item responses with numeric Likert values.
    Stores both raw value and computed scored value (for reverse-scored items).
    """
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name='scale_responses'
    )
    item = models.ForeignKey(
        ScaleItem,
        on_delete=models.CASCADE,
        related_name='responses'
    )
    numeric_value = models.IntegerField(help_text="Raw numeric response (0-3 or 0-4 typically)")
    verbatim_text = models.TextField(
        blank=True,
        default='',
        help_text="Optional free-text elaboration on the response"
    )
    scored_value = models.IntegerField(
        help_text="Computed score after reverse scoring if applicable"
    )
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['session', 'item__scale', 'item__item_number']
        unique_together = ['session', 'item']

    def __str__(self):
        return f"{self.session.id} - {self.item}: {self.numeric_value}"

    def save(self, *args, **kwargs):
        # Auto-compute scored_value on save
        self.scored_value = self.item.get_scored_value(self.numeric_value)
        super().save(*args, **kwargs)


class ScaleScore(models.Model):
    """
    Computed scores per scale for a session.
    All scoring is deterministic (NO LLM) - computed from ScaleResponse values.
    """
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name='scale_scores'
    )
    scale = models.ForeignKey(
        PsychometricScale,
        on_delete=models.CASCADE,
        related_name='scores'
    )
    total_score = models.IntegerField()
    max_possible_score = models.IntegerField()
    percentage_score = models.FloatField()
    severity_level = models.CharField(max_length=20, blank=True)
    clinical_interpretation = models.TextField(blank=True)
    subscale_scores = models.JSONField(
        default=dict,
        blank=True,
        help_text="Subscale scores if applicable"
    )
    has_critical_response = models.BooleanField(default=False)
    critical_item_details = models.JSONField(
        default=list,
        blank=True,
        help_text="Details of any critical item responses"
    )
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['session', 'scale__order']
        unique_together = ['session', 'scale']

    def __str__(self):
        return f"{self.session.id} - {self.scale.code}: {self.total_score} ({self.severity_level})"


class FreeTextResponse(models.Model):
    """
    Optional follow-up responses after scales are complete.
    Stored verbatim without LLM interpretation in the scoring path.
    """
    CONTEXT_CHOICES = [
        ('clarification', 'Clarification'),
        ('additional_concerns', 'Additional Concerns'),
        ('follow_up', 'Follow-up'),
    ]

    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name='free_text_responses'
    )
    context_type = models.CharField(max_length=30, choices=CONTEXT_CHOICES)
    prompt_text = models.TextField(help_text="The question/prompt that was asked")
    response_text = models.TextField(help_text="Verbatim user response")
    related_scale = models.ForeignKey(
        PsychometricScale,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Scale this follow-up relates to, if any"
    )
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['session', 'timestamp']

    def __str__(self):
        return f"{self.session.id} - {self.context_type}: {self.response_text[:50]}"


# =============================================================================
# GROUNDED SUMMARY MODEL (New - with verification)
# =============================================================================

class GroundedSummary(models.Model):
    """
    Summary with hallucination safeguards.
    Replaces AssessmentSummary for scale-based assessments.

    Key features:
    - Stores computed scores separately from narrative
    - Tracks cited quotes for verification
    - Records verification results
    """
    COMPLETION_STATUS_CHOICES = [
        ('complete', 'Complete'),
        ('partial', 'Partial'),
        ('incomplete', 'Incomplete'),
    ]

    session = models.OneToOneField(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name='grounded_summary',
        primary_key=True
    )

    # Computed data (deterministic, NO LLM)
    score_summary = models.JSONField(
        default=dict,
        help_text="Computed scores from ScaleScore records"
    )
    severity_summary = models.JSONField(
        default=dict,
        help_text="Severity levels per scale"
    )

    # LLM-generated content (will be verified)
    narrative_summary = models.TextField(
        blank=True,
        help_text="LLM-generated narrative (must be verified)"
    )
    cited_quotes = models.JSONField(
        default=list,
        help_text="Verbatim responses referenced in narrative"
    )

    # Verification results
    is_verified = models.BooleanField(default=False)
    verification_errors = models.JSONField(
        default=list,
        help_text="Errors found during fact-checking"
    )
    verification_warnings = models.JSONField(
        default=list,
        help_text="Warnings found during fact-checking"
    )
    verification_timestamp = models.DateTimeField(null=True, blank=True)

    # Review flags
    requires_professional_review = models.BooleanField(default=False)
    review_reasons = models.JSONField(
        default=list,
        help_text="Reasons for requiring professional review"
    )

    # Status
    completion_status = models.CharField(
        max_length=20,
        choices=COMPLETION_STATUS_CHOICES,
        default='incomplete'
    )
    missing_scales = models.JSONField(
        default=list,
        help_text="Scales that were not completed"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Grounded summaries"

    def __str__(self):
        verified_status = "Verified" if self.is_verified else "Unverified"
        return f"GroundedSummary for Assessment {self.session.id} ({verified_status})"


# =============================================================================
# LEGACY MODELS (Kept for backwards compatibility)
# =============================================================================

class AssessmentResponse(models.Model):
    """
    Stores individual responses to legacy assessment questions.
    DEPRECATED: Use ScaleResponse for new scale-based assessments.
    """
    CATEGORY_CHOICES = [
        ('mood', 'Mood'),
        ('stress', 'Stress'),
        ('sleep', 'Sleep'),
        ('anxiety', 'Anxiety'),
        ('daily_activities', 'Daily Activities'),
        ('concerns', 'Concerns'),
    ]

    id = models.AutoField(primary_key=True)
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name='responses'
    )
    question_category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    question_text = models.TextField()
    response_text = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.session.id} - {self.question_category}: {self.response_text[:50]}"


class AssessmentSummary(models.Model):
    """
    Generated summary for professional review (legacy model).
    DEPRECATED: Use GroundedSummary for new scale-based assessments.
    """
    COMPLETION_STATUS_CHOICES = [
        ('complete', 'Complete'),
        ('partial', 'Partial'),
        ('incomplete', 'Incomplete'),
    ]

    session = models.OneToOneField(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name='summary',
        primary_key=True
    )
    summary_text = models.TextField()
    missing_info = models.JSONField(default=list, blank=True)
    areas_for_review = models.JSONField(default=list, blank=True)
    completion_status = models.CharField(
        max_length=20,
        choices=COMPLETION_STATUS_CHOICES,
        default='incomplete'
    )
    flagged_for_professional = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Assessment summaries"

    def __str__(self):
        return f"Summary for Assessment {self.session.id}"
