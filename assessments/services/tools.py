"""
LangGraph Agent Tools for Mental Health Assessment
"""
from typing import Dict, List, Any
from langchain_core.tools import tool
import re


# In-memory storage for responses during agent execution
# In production, this would interface with Django models
_responses_cache = {}


@tool
def store_response(session_id: str, category: str, question: str, response: str) -> Dict[str, Any]:
    """
    Store a response to an assessment question.

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

    Args:
        session_id: Unique identifier for the assessment session

    Returns:
        Dictionary containing all responses grouped by category
    """
    from assessments.models import AssessmentSession

    try:
        session = AssessmentSession.objects.get(id=session_id)
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
    Validate a response for completeness and consistency.

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
        # Check for sleep-related keywords
        sleep_keywords = ['hour', 'sleep', 'night', 'bed', 'wake', 'rest', 'insomnia']
        if not any(keyword in response.lower() for keyword in sleep_keywords):
            warnings.append("Consider mentioning sleep duration or quality.")

    elif category == 'mood':
        # Check for emotion-related words
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
    Identify which assessment categories are missing responses.

    Args:
        session_id: Unique identifier for the assessment session

    Returns:
        Dictionary with lists of completed and missing categories
    """
    from assessments.models import AssessmentSession

    required_categories = ['mood', 'stress', 'sleep', 'anxiety', 'daily_activities', 'concerns']

    try:
        session = AssessmentSession.objects.get(id=session_id)
        existing_categories = list(session.responses.values_list('question_category', flat=True).distinct())

        missing_categories = [cat for cat in required_categories if cat not in existing_categories]

        return {
            'status': 'success',
            'completed_categories': existing_categories,
            'missing_categories': missing_categories,
            'is_complete': len(missing_categories) == 0,
            'completion_percentage': int((len(existing_categories) / len(required_categories)) * 100)
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'missing_categories': required_categories
        }


@tool
def check_distress_signals(response_text: str) -> Dict[str, Any]:
    """
    Check for distress signals or concerning content in responses.

    Args:
        response_text: The user's response text to analyze

    Returns:
        Dictionary indicating if professional review is needed and why
    """
    distress_keywords = [
        # Self-harm indicators
        'suicide', 'suicidal', 'kill myself', 'end my life', 'self-harm', 'cut myself',
        'hurt myself', 'die', 'death wish',
        # Severe distress
        'hopeless', 'can\'t go on', 'no point', 'worthless', 'hate myself',
        'everyone would be better without me', 'no reason to live',
        # Crisis indicators
        'plan to', 'going to hurt', 'want to die', 'can\'t take it anymore'
    ]

    severe_keywords = [
        'suicide', 'suicidal', 'kill myself', 'end my life', 'self-harm'
    ]

    response_lower = response_text.lower()

    # Check for severe distress signals
    severe_signals = [kw for kw in severe_keywords if kw in response_lower]

    # Check for general distress signals
    distress_signals = [kw for kw in distress_keywords if kw in response_lower]

    requires_immediate_review = len(severe_signals) > 0
    requires_review = len(distress_signals) > 0

    result = {
        'requires_immediate_review': requires_immediate_review,
        'requires_review': requires_review,
        'signals_found': distress_signals if distress_signals else [],
        'severity': 'high' if requires_immediate_review else 'moderate' if requires_review else 'low'
    }

    if requires_immediate_review:
        result['message'] = 'URGENT: Immediate professional review required. Response contains crisis indicators.'
    elif requires_review:
        result['message'] = 'Professional review recommended. Response contains distress indicators.'
    else:
        result['message'] = 'No significant distress signals detected.'

    return result


# Helper function to get all tools
def get_assessment_tools():
    """Return all assessment tools for the agent"""
    return [
        store_response,
        retrieve_responses,
        validate_response,
        identify_missing_categories,
        check_distress_signals
    ]
