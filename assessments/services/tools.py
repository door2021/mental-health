"""
LangGraph Agent Tools for Mental Health Assessment

Updated for scale-based assessment with hallucination safeguards.
Includes both legacy tools and new scale-aware tools.
"""
from typing import Dict, List, Any, Optional
from langchain_core.tools import tool

from .scoring import scoring_engine
from .validation import response_validator, distress_detector
from .verification import summary_verifier


# =============================================================================
# NEW SCALE-AWARE TOOLS
# =============================================================================

@tool
def get_next_scale_item(session_id: str, scale_code: str, item_number: int) -> Dict[str, Any]:
    """
    Retrieve a specific scale item from the database.

    Args:
        session_id: Assessment session ID
        scale_code: Scale code (e.g., 'PHQ9', 'GAD7')
        item_number: Item number within the scale (1-indexed)

    Returns:
        Dictionary with item details including question text and response options
    """
    from assessments.models import PsychometricScale, ScaleItem

    try:
        scale = PsychometricScale.objects.get(code=scale_code)
        item = ScaleItem.objects.get(scale=scale, item_number=item_number)

        return {
            'status': 'success',
            'item': {
                'id': item.id,
                'scale_code': scale_code,
                'scale_name': scale.name,
                'item_number': item_number,
                'total_items': scale.items.count(),
                'question_text': item.question_text,
                'response_options': item.response_options,
                'min_value': item.min_value,
                'max_value': item.max_value,
                'is_critical': item.is_critical,
                'critical_threshold': item.critical_threshold
            }
        }
    except PsychometricScale.DoesNotExist:
        return {
            'status': 'error',
            'message': f'Scale not found: {scale_code}'
        }
    except ScaleItem.DoesNotExist:
        # Check if we've completed the scale
        try:
            scale = PsychometricScale.objects.get(code=scale_code)
            total = scale.items.count()
            if item_number > total:
                return {
                    'status': 'scale_complete',
                    'message': f'Scale {scale_code} complete (all {total} items answered)',
                    'total_items': total
                }
        except PsychometricScale.DoesNotExist:
            pass
        return {
            'status': 'error',
            'message': f'Item {item_number} not found for scale {scale_code}'
        }


@tool
def store_scale_response(
    session_id: str,
    item_id: int,
    numeric_value: int,
    verbatim_text: str = ""
) -> Dict[str, Any]:
    """
    Store a Likert scale response.

    Args:
        session_id: Assessment session ID
        item_id: ScaleItem ID
        numeric_value: Numeric response (0-3 or 0-4)
        verbatim_text: Optional free-text elaboration

    Returns:
        Dictionary with storage status and any validation warnings
    """
    from assessments.models import AssessmentSession, ScaleItem, ScaleResponse

    try:
        session = AssessmentSession.objects.get(id=session_id)
        item = ScaleItem.objects.get(id=item_id)

        # Validate the response
        validation = response_validator.validate_numeric_response(item, numeric_value)

        if not validation.valid:
            return {
                'status': 'validation_error',
                'errors': validation.errors,
                'warnings': validation.warnings
            }

        # Store the response (scored_value computed on save)
        response, created = ScaleResponse.objects.update_or_create(
            session=session,
            item=item,
            defaults={
                'numeric_value': numeric_value,
                'verbatim_text': verbatim_text,
                'scored_value': item.get_scored_value(numeric_value)
            }
        )

        result = {
            'status': 'success',
            'response_id': response.id,
            'numeric_value': numeric_value,
            'scored_value': response.scored_value,
            'is_critical': validation.is_critical,
            'warnings': validation.warnings
        }

        if validation.is_critical:
            result['critical_message'] = validation.critical_message

        return result

    except AssessmentSession.DoesNotExist:
        return {'status': 'error', 'message': f'Session not found: {session_id}'}
    except ScaleItem.DoesNotExist:
        return {'status': 'error', 'message': f'Item not found: {item_id}'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@tool
def compute_scale_score(session_id: str, scale_code: str) -> Dict[str, Any]:
    """
    Compute the total score for a completed scale.
    Uses deterministic scoring (NO LLM).

    Args:
        session_id: Assessment session ID
        scale_code: Scale code (e.g., 'PHQ9')

    Returns:
        Dictionary with computed score, severity level, and clinical interpretation
    """
    from assessments.models import AssessmentSession, PsychometricScale

    try:
        session = AssessmentSession.objects.get(id=session_id)
        scale = PsychometricScale.objects.get(code=scale_code)

        # Compute score using the scoring engine
        result = scoring_engine.compute_scale_score(session, scale)

        # Save to database
        scoring_engine.save_score(session, scale, result)

        return {
            'status': 'success',
            'scale_code': scale_code,
            'total_score': result.total_score,
            'max_possible_score': result.max_possible_score,
            'percentage_score': result.percentage_score,
            'severity_level': result.severity_level,
            'clinical_interpretation': result.clinical_interpretation,
            'subscale_scores': result.subscale_scores,
            'has_critical_response': result.has_critical_response,
            'critical_item_details': result.critical_item_details,
            'items_answered': result.items_answered,
            'items_total': result.items_total
        }

    except AssessmentSession.DoesNotExist:
        return {'status': 'error', 'message': f'Session not found: {session_id}'}
    except PsychometricScale.DoesNotExist:
        return {'status': 'error', 'message': f'Scale not found: {scale_code}'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@tool
def get_session_scores(session_id: str) -> Dict[str, Any]:
    """
    Retrieve all computed scores for a session.

    Args:
        session_id: Assessment session ID

    Returns:
        Dictionary with all scale scores and overall status
    """
    from assessments.models import AssessmentSession, ScaleScore

    try:
        session = AssessmentSession.objects.get(id=session_id)

        scores = ScaleScore.objects.filter(session=session).select_related('scale')

        score_data = {}
        has_critical = False
        requires_review = False
        review_reasons = []

        for score in scores:
            score_data[score.scale.code] = {
                'total_score': score.total_score,
                'max_possible_score': score.max_possible_score,
                'percentage_score': score.percentage_score,
                'severity_level': score.severity_level,
                'clinical_interpretation': score.clinical_interpretation,
                'has_critical_response': score.has_critical_response
            }

            if score.has_critical_response:
                has_critical = True
                requires_review = True
                for detail in score.critical_item_details:
                    review_reasons.append(
                        f"Critical response on {score.scale.code} Q{detail.get('item_number')}"
                    )

            if score.severity_level in ['severe', 'moderately_severe']:
                requires_review = True
                review_reasons.append(
                    f"{score.scale.code} indicates {score.severity_level} level"
                )

        # Check completion
        assigned = session.assigned_scales.count()
        completed = scores.count()

        return {
            'status': 'success',
            'session_id': session_id,
            'scores': score_data,
            'scales_completed': completed,
            'scales_assigned': assigned,
            'completion_percentage': int((completed / assigned * 100)) if assigned > 0 else 0,
            'has_critical_response': has_critical,
            'requires_professional_review': requires_review,
            'review_reasons': review_reasons
        }

    except AssessmentSession.DoesNotExist:
        return {'status': 'error', 'message': f'Session not found: {session_id}'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@tool
def verify_summary_grounding(session_id: str) -> Dict[str, Any]:
    """
    Verify that a generated summary is factually grounded.
    Checks for hallucinations in scores, severity claims, and quotes.

    Args:
        session_id: Assessment session ID

    Returns:
        Dictionary with verification results including any errors found
    """
    from assessments.models import AssessmentSession, GroundedSummary

    try:
        session = AssessmentSession.objects.get(id=session_id)
        summary = GroundedSummary.objects.get(session=session)

        # Run verification
        result = summary_verifier.verify(session, summary.narrative_summary)

        # Save results
        summary_verifier.save_verification_results(session, result)

        return {
            'status': 'success',
            'is_verified': result.is_valid,
            'errors': result.errors,
            'warnings': result.warnings,
            'score_claims_checked': len(result.score_claims),
            'severity_claims_checked': len(result.severity_claims),
            'quote_claims_checked': len(result.quote_claims)
        }

    except AssessmentSession.DoesNotExist:
        return {'status': 'error', 'message': f'Session not found: {session_id}'}
    except GroundedSummary.DoesNotExist:
        return {'status': 'error', 'message': 'No summary found for session'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@tool
def check_free_text_distress(text: str) -> Dict[str, Any]:
    """
    Check free-text response for distress signals.
    Uses keyword-based detection (NO LLM).

    Args:
        text: Free-text response to check

    Returns:
        Dictionary with distress detection results
    """
    return distress_detector.check_free_text(text)


# =============================================================================
# LEGACY TOOLS (Kept for backwards compatibility)
# =============================================================================

# In-memory storage for responses during agent execution
_responses_cache = {}


@tool
def store_response(session_id: str, category: str, question: str, response: str) -> Dict[str, Any]:
    """
    Store a response to a legacy assessment question.
    DEPRECATED: Use store_scale_response for new assessments.

    Args:
        session_id: Unique identifier for the assessment session
        category: Question category (mood, stress, sleep, anxiety, daily_activities, concerns)
        question: The question that was asked
        response: The user's response

    Returns:
        Dictionary with status and stored response details
    """
    from assessments.models import AssessmentSession, AssessmentResponse

    try:
        session = AssessmentSession.objects.get(id=session_id)

        # Create the response
        assessment_response = AssessmentResponse.objects.create(
            session=session,
            question_category=category,
            question_text=question,
            response_text=response
        )

        # Also cache for quick access during conversation
        if session_id not in _responses_cache:
            _responses_cache[session_id] = []
        _responses_cache[session_id].append({
            'category': category,
            'question': question,
            'response': response
        })

        return {
            'status': 'success',
            'message': f'Response stored for category: {category}',
            'response_id': assessment_response.id
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


@tool
def retrieve_responses(session_id: str) -> Dict[str, Any]:
    """
    Retrieve all responses for a given assessment session.
    Works with both legacy and scale-based responses.

    Args:
        session_id: Unique identifier for the assessment session

    Returns:
        Dictionary containing all responses grouped by category/scale
    """
    from assessments.models import AssessmentSession, ScaleResponse

    try:
        session = AssessmentSession.objects.get(id=session_id)

        # Check if this is a scale-based session
        if not session.is_legacy_format():
            # Return scale responses
            responses = ScaleResponse.objects.filter(session=session).select_related('item__scale')

            grouped_responses = {}
            for response in responses:
                scale_code = response.item.scale.code
                if scale_code not in grouped_responses:
                    grouped_responses[scale_code] = []
                grouped_responses[scale_code].append({
                    'item_number': response.item.item_number,
                    'question': response.item.question_text,
                    'numeric_value': response.numeric_value,
                    'scored_value': response.scored_value,
                    'verbatim_text': response.verbatim_text,
                    'timestamp': response.timestamp.isoformat()
                })

            return {
                'status': 'success',
                'session_id': session_id,
                'format': 'scale_based',
                'responses': grouped_responses,
                'total_responses': responses.count()
            }
        else:
            # Return legacy responses
            responses = session.responses.all().order_by('timestamp')

            grouped_responses = {}
            for response in responses:
                if response.question_category not in grouped_responses:
                    grouped_responses[response.question_category] = []
                grouped_responses[response.question_category].append({
                    'question': response.question_text,
                    'response': response.response_text,
                    'timestamp': response.timestamp.isoformat()
                })

            return {
                'status': 'success',
                'session_id': session_id,
                'format': 'legacy',
                'responses': grouped_responses,
                'total_responses': responses.count()
            }

    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'responses': {}
        }


@tool
def validate_response(category: str, response: str) -> Dict[str, Any]:
    """
    Validate a legacy response for completeness and consistency.
    DEPRECATED: Use store_scale_response which includes validation.

    Args:
        category: The question category
        response: The user's response text

    Returns:
        Dictionary with validation status and any errors
    """
    errors = []
    warnings = []

    # Check for minimum length
    if len(response.strip()) < 3:
        errors.append("Response is too short. Please provide more detail.")
        return {
            'valid': False,
            'errors': errors,
            'warnings': warnings
        }

    # Check for meaningful content (not just "ok", "fine", etc.)
    minimal_responses = ['ok', 'fine', 'good', 'bad', 'yes', 'no', 'idk', 'dunno']
    if response.strip().lower() in minimal_responses:
        warnings.append("Response is quite brief. More detail would be helpful for assessment.")

    # Category-specific validation
    if category == 'sleep':
        sleep_keywords = ['hour', 'sleep', 'night', 'bed', 'wake', 'rest', 'insomnia']
        if not any(keyword in response.lower() for keyword in sleep_keywords):
            warnings.append("Consider mentioning sleep duration or quality.")

    elif category == 'mood':
        emotion_keywords = ['feel', 'mood', 'emotion', 'happy', 'sad', 'angry', 'anxious', 'depressed']
        if not any(keyword in response.lower() for keyword in emotion_keywords):
            warnings.append("Consider describing your emotional state.")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    }


@tool
def identify_missing_categories(session_id: str) -> Dict[str, Any]:
    """
    Identify which assessment categories/scales are missing responses.

    Args:
        session_id: Unique identifier for the assessment session

    Returns:
        Dictionary with lists of completed and missing categories
    """
    from assessments.models import AssessmentSession, ScaleResponse

    try:
        session = AssessmentSession.objects.get(id=session_id)

        if not session.is_legacy_format():
            # Scale-based session
            assigned_scales = list(session.assigned_scales.values_list('code', flat=True))
            completed_scales = list(
                ScaleResponse.objects.filter(session=session)
                .values_list('item__scale__code', flat=True)
                .distinct()
            )

            # Check if scales are fully completed
            fully_completed = []
            for scale_code in completed_scales:
                from assessments.models import PsychometricScale
                scale = PsychometricScale.objects.get(code=scale_code)
                total_items = scale.items.count()
                answered = ScaleResponse.objects.filter(
                    session=session,
                    item__scale=scale
                ).count()
                if answered >= total_items:
                    fully_completed.append(scale_code)

            missing = [s for s in assigned_scales if s not in fully_completed]

            return {
                'status': 'success',
                'format': 'scale_based',
                'completed_scales': fully_completed,
                'missing_scales': missing,
                'is_complete': len(missing) == 0,
                'completion_percentage': int((len(fully_completed) / len(assigned_scales)) * 100) if assigned_scales else 0
            }
        else:
            # Legacy session
            required_categories = ['mood', 'stress', 'sleep', 'anxiety', 'daily_activities', 'concerns']
            existing_categories = list(session.responses.values_list('question_category', flat=True).distinct())
            missing_categories = [cat for cat in required_categories if cat not in existing_categories]

            return {
                'status': 'success',
                'format': 'legacy',
                'completed_categories': existing_categories,
                'missing_categories': missing_categories,
                'is_complete': len(missing_categories) == 0,
                'completion_percentage': int((len(existing_categories) / len(required_categories)) * 100)
            }

    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'missing_categories': []
        }


@tool
def check_distress_signals(response_text: str) -> Dict[str, Any]:
    """
    Check for distress signals or concerning content in responses.
    Uses the DistressDetector for keyword-based detection.

    Args:
        response_text: The user's response text to analyze

    Returns:
        Dictionary indicating if professional review is needed and why
    """
    result = distress_detector.check_free_text(response_text)

    # Map to legacy format for compatibility
    return {
        'requires_immediate_review': result['is_crisis'],
        'requires_review': result['requires_review'],
        'signals_found': result['crisis_keywords'] + result['distress_keywords'],
        'severity': result['severity'],
        'message': result['message']
    }


# Helper function to get all tools
def get_assessment_tools():
    """Return all assessment tools for the agent"""
    return [
        # New scale-aware tools
        get_next_scale_item,
        store_scale_response,
        compute_scale_score,
        get_session_scores,
        verify_summary_grounding,
        check_free_text_distress,
        # Legacy tools
        store_response,
        retrieve_responses,
        validate_response,
        identify_missing_categories,
        check_distress_signals
    ]


def get_scale_tools():
    """Return only the new scale-aware tools"""
    return [
        get_next_scale_item,
        store_scale_response,
        compute_scale_score,
        get_session_scores,
        verify_summary_grounding,
        check_free_text_distress
    ]
