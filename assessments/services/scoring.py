"""
Deterministic Scoring Engine for Psychometric Scales

CRITICAL: This module contains NO LLM calls.
All scoring is algorithmic and deterministic.
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from django.utils import timezone


@dataclass
class ScoreResult:
    """Result of scoring a single scale"""
    scale_code: str
    total_score: int
    max_possible_score: int
    percentage_score: float
    severity_level: str
    clinical_interpretation: str
    subscale_scores: Dict[str, int] = field(default_factory=dict)
    has_critical_response: bool = False
    critical_item_details: List[Dict] = field(default_factory=list)
    items_answered: int = 0
    items_total: int = 0


@dataclass
class AllScoresResult:
    """Result of scoring all scales for a session"""
    scores: Dict[str, ScoreResult]
    overall_requires_review: bool
    review_reasons: List[str]
    completion_status: str
    missing_scales: List[str]


class ScoringEngine:
    """
    Pure algorithmic scoring engine - NO LLM involvement.

    This class is responsible for:
    1. Computing total scores from individual responses
    2. Handling reverse-scored items
    3. Computing subscale scores
    4. Looking up severity levels from cutoff tables
    5. Flagging critical items
    """

    def compute_scale_score(self, session, scale) -> ScoreResult:
        """
        Compute the score for a single scale.

        Args:
            session: AssessmentSession instance
            scale: PsychometricScale instance

        Returns:
            ScoreResult with computed scores and severity
        """
        from assessments.models import ScaleResponse, SeverityCutoff

        # Get all responses for this scale in this session
        responses = ScaleResponse.objects.filter(
            session=session,
            item__scale=scale
        ).select_related('item')

        # Get all items for this scale
        items = scale.items.all()
        items_total = items.count()
        items_answered = responses.count()

        # Compute total score (using scored_value which handles reverse scoring)
        total_score = sum(r.scored_value for r in responses)

        # Compute max possible score
        max_possible_score = sum(
            item.max_value * item.weight
            for item in items
        )

        # Compute percentage
        percentage_score = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0

        # Compute subscale scores
        subscale_scores = {}
        for response in responses:
            if response.item.subscale:
                subscale = response.item.subscale
                if subscale not in subscale_scores:
                    subscale_scores[subscale] = 0
                subscale_scores[subscale] += response.scored_value

        # Look up severity level
        severity_level = ''
        clinical_interpretation = ''

        try:
            cutoff = SeverityCutoff.objects.get(
                scale=scale,
                min_score__lte=total_score,
                max_score__gte=total_score
            )
            severity_level = cutoff.severity_level
            clinical_interpretation = cutoff.clinical_interpretation
        except SeverityCutoff.DoesNotExist:
            # Fallback if no cutoff matches
            severity_level = 'unknown'
            clinical_interpretation = f'Score {total_score} does not match defined severity cutoffs'
        except SeverityCutoff.MultipleObjectsReturned:
            # If multiple cutoffs match, take the first one
            cutoff = SeverityCutoff.objects.filter(
                scale=scale,
                min_score__lte=total_score,
                max_score__gte=total_score
            ).first()
            if cutoff:
                severity_level = cutoff.severity_level
                clinical_interpretation = cutoff.clinical_interpretation

        # Check for critical items
        has_critical_response = False
        critical_item_details = []

        for response in responses:
            if response.item.is_critical:
                threshold = response.item.critical_threshold
                if threshold is not None and response.numeric_value >= threshold:
                    has_critical_response = True
                    critical_item_details.append({
                        'item_number': response.item.item_number,
                        'question': response.item.question_text[:100],
                        'response_value': response.numeric_value,
                        'threshold': threshold,
                        'verbatim': response.verbatim_text if response.verbatim_text else None
                    })

        return ScoreResult(
            scale_code=scale.code,
            total_score=total_score,
            max_possible_score=int(max_possible_score),
            percentage_score=round(percentage_score, 1),
            severity_level=severity_level,
            clinical_interpretation=clinical_interpretation,
            subscale_scores=subscale_scores,
            has_critical_response=has_critical_response,
            critical_item_details=critical_item_details,
            items_answered=items_answered,
            items_total=items_total
        )

    def save_score(self, session, scale, result: ScoreResult):
        """
        Persist the computed score to the database.

        Args:
            session: AssessmentSession instance
            scale: PsychometricScale instance
            result: ScoreResult to persist

        Returns:
            ScaleScore model instance
        """
        from assessments.models import ScaleScore

        score, created = ScaleScore.objects.update_or_create(
            session=session,
            scale=scale,
            defaults={
                'total_score': result.total_score,
                'max_possible_score': result.max_possible_score,
                'percentage_score': result.percentage_score,
                'severity_level': result.severity_level,
                'clinical_interpretation': result.clinical_interpretation,
                'subscale_scores': result.subscale_scores,
                'has_critical_response': result.has_critical_response,
                'critical_item_details': result.critical_item_details,
                'computed_at': timezone.now()
            }
        )
        return score

    def compute_all_scores(self, session) -> AllScoresResult:
        """
        Compute scores for all assigned scales in a session.

        Args:
            session: AssessmentSession instance

        Returns:
            AllScoresResult with all computed scores
        """
        from assessments.models import ScaleResponse

        scores = {}
        review_reasons = []
        missing_scales = []

        for scale in session.assigned_scales.all().order_by('order'):
            # Check if scale has responses
            response_count = ScaleResponse.objects.filter(
                session=session,
                item__scale=scale
            ).count()

            if response_count == 0:
                missing_scales.append(scale.code)
                continue

            # Compute score
            result = self.compute_scale_score(session, scale)
            scores[scale.code] = result

            # Save to database
            self.save_score(session, scale, result)

            # Check for review requirements
            if result.has_critical_response:
                for detail in result.critical_item_details:
                    review_reasons.append(
                        f"Critical response on {scale.code} Q{detail['item_number']}: "
                        f"value {detail['response_value']} >= threshold {detail['threshold']}"
                    )

            # Flag severe scores for review
            if result.severity_level in ['severe', 'moderately_severe']:
                review_reasons.append(
                    f"{scale.code} indicates {result.severity_level} level "
                    f"(score: {result.total_score}/{result.max_possible_score})"
                )

        # Determine completion status
        total_assigned = session.assigned_scales.count()
        total_completed = len(scores)

        if total_completed == 0:
            completion_status = 'incomplete'
        elif total_completed < total_assigned:
            completion_status = 'partial'
        else:
            completion_status = 'complete'

        return AllScoresResult(
            scores=scores,
            overall_requires_review=len(review_reasons) > 0,
            review_reasons=review_reasons,
            completion_status=completion_status,
            missing_scales=missing_scales
        )

    def get_score_summary_dict(self, session) -> Dict[str, Any]:
        """
        Get a dictionary summary of all scores suitable for JSON storage.

        Args:
            session: AssessmentSession instance

        Returns:
            Dict with score data
        """
        from assessments.models import ScaleScore

        scores = ScaleScore.objects.filter(session=session).select_related('scale')

        return {
            score.scale.code: {
                'total_score': score.total_score,
                'max_possible_score': score.max_possible_score,
                'percentage_score': score.percentage_score,
                'severity_level': score.severity_level,
                'clinical_interpretation': score.clinical_interpretation,
                'subscale_scores': score.subscale_scores,
                'has_critical_response': score.has_critical_response,
                'critical_item_details': score.critical_item_details
            }
            for score in scores
        }

    def get_severity_summary_dict(self, session) -> Dict[str, str]:
        """
        Get a dictionary mapping scale codes to severity levels.

        Args:
            session: AssessmentSession instance

        Returns:
            Dict mapping scale code to severity level
        """
        from assessments.models import ScaleScore

        scores = ScaleScore.objects.filter(session=session).select_related('scale')

        return {
            score.scale.code: score.severity_level
            for score in scores
        }


# Singleton instance
scoring_engine = ScoringEngine()
