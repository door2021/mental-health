"""
Database models for Mental Health Assessment System
"""
from django.db import models
from django.utils import timezone


class AssessmentSession(models.Model):
    """
    Tracks individual assessment sessions with status and metadata
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('requires_review', 'Requires Review'),
    ]

    id = models.AutoField(primary_key=True)
    user_identifier = models.CharField(max_length=255, help_text="Anonymous identifier for the user")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Assessment {self.id} - {self.user_identifier} ({self.status})"

    def get_responses_by_category(self):
        """Group responses by category"""
        responses = {}
        for response in self.responses.all():
            if response.question_category not in responses:
                responses[response.question_category] = []
            responses[response.question_category].append(response)
        return responses

    def is_complete(self):
        """Check if all required categories have responses"""
        required_categories = ['mood', 'stress', 'sleep', 'anxiety', 'daily_activities', 'concerns']
        existing_categories = set(self.responses.values_list('question_category', flat=True))
        return all(cat in existing_categories for cat in required_categories)


class AssessmentResponse(models.Model):
    """
    Stores individual responses to assessment questions
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
    Generated summary for professional review
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
