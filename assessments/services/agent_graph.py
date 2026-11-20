"""
LangGraph State Graph for Mental Health Assessment Agent

Updated to use standardized psychometric scales with hallucination safeguards.
"""
from typing import TypedDict, List, Dict, Any, Annotated, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import operator
from django.conf import settings

from .scoring import scoring_engine
from .validation import response_validator, distress_detector
from .verification import summary_verifier


# =============================================================================
# STATE SCHEMA
# =============================================================================

class AssessmentState(TypedDict):
    """State schema for the scale-based assessment workflow"""
    # Session tracking
    session_id: str
    is_legacy: bool  # True if using old open-ended assessment

    # Scale administration
    current_scale_code: Optional[str]
    current_item_number: int
    scales_to_administer: List[str]
    completed_scales: List[str]
    current_item: Optional[Dict]  # Current ScaleItem data

    # Response handling
    awaiting_response_type: str  # 'likert' | 'free_text' | 'none'
    user_message: str
    agent_response: str

    # Scoring (computed deterministically, NO LLM)
    computed_scores: Dict[str, Dict]
    critical_responses_detected: List[Dict]
    requires_professional_review: bool
    review_reasons: List[str]

    # Conversation
    conversation_history: Annotated[List[Any], operator.add]

    # Workflow control
    phase: str  # 'introduction' | 'scales' | 'follow_up' | 'summary' | 'review' | 'completed'
    is_complete: bool
    summary_text: str
    summary_verified: bool
    verification_errors: List[str]
    retry_count: int


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_llm():
    """Get the LLM instance for conversational responses only"""
    return ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.3,
        api_key=settings.GROQ_API_KEY
    )


def format_likert_options(options: List[Dict]) -> str:
    """Format response options for display"""
    lines = []
    for opt in options:
        lines.append(f"  {opt['value']} - {opt['label']}")
    return "\n".join(lines)


def get_scale_item(scale_code: str, item_number: int) -> Optional[Dict]:
    """Retrieve a scale item from the database"""
    from assessments.models import ScaleItem, PsychometricScale

    try:
        scale = PsychometricScale.objects.get(code=scale_code)
        item = ScaleItem.objects.get(scale=scale, item_number=item_number)
        return {
            'id': item.id,
            'scale_code': scale_code,
            'item_number': item_number,
            'question_text': item.question_text,
            'response_options': item.response_options,
            'min_value': item.min_value,
            'max_value': item.max_value,
            'is_critical': item.is_critical,
            'critical_threshold': item.critical_threshold
        }
    except (PsychometricScale.DoesNotExist, ScaleItem.DoesNotExist):
        return None


def get_total_items_for_scale(scale_code: str) -> int:
    """Get total number of items in a scale"""
    from assessments.models import PsychometricScale

    try:
        scale = PsychometricScale.objects.get(code=scale_code)
        return scale.items.count()
    except PsychometricScale.DoesNotExist:
        return 0


# =============================================================================
# GRAPH NODES
# =============================================================================

def introduce_assessment(state: AssessmentState) -> AssessmentState:
    """
    Node: Introduce the assessment to the user.
    Uses LLM for conversational greeting only.
    """
    from assessments.models import AssessmentSession, PsychometricScale

    session_id = state['session_id']

    try:
        session = AssessmentSession.objects.get(id=session_id)

        # Check if this is a legacy session
        if session.is_legacy_format():
            return {
                **state,
                'is_legacy': True,
                'agent_response': "This is a legacy assessment session. Please start a new assessment to use the updated scale-based system."
            }

        # Get assigned scales
        scales = list(session.assigned_scales.all().order_by('order'))

        if not scales:
            # Assign default scales if none assigned
            default_scales = PsychometricScale.objects.filter(
                code__in=['PHQ9', 'GAD7', 'PSS10', 'ISI'],
                is_active=True
            ).order_by('order')

            for scale in default_scales:
                session.assigned_scales.add(scale)

            scales = list(default_scales)

        scale_names = [f"{s.name} ({s.code})" for s in scales]
        scales_to_administer = [s.code for s in scales]

        # Build introduction message
        intro_message = f"""Welcome to your mental health assessment.

I'll be asking you a series of questions from validated clinical questionnaires to help understand your current wellbeing. The assessment includes:

{chr(10).join(f'• {name}' for name in scale_names)}

For each question, you'll select a response from a scale (usually 0-3 or 0-4). Please answer based on how you've been feeling over the past 2 weeks.

Your responses will be scored using standardized clinical methods and reviewed by a mental health professional.

**Important**: This assessment does not diagnose conditions - it collects information to support professional evaluation.

Let's begin with the first questionnaire."""

        # Set first scale
        first_scale = scales_to_administer[0] if scales_to_administer else None

        # Update session phase
        session.phase = 'scales'
        session.current_scale_id = scales[0].id if scales else None
        session.current_item_number = 1
        session.save()

        return {
            **state,
            'is_legacy': False,
            'scales_to_administer': scales_to_administer,
            'completed_scales': [],
            'current_scale_code': first_scale,
            'current_item_number': 1,
            'phase': 'scales',
            'awaiting_response_type': 'none',
            'computed_scores': {},
            'critical_responses_detected': [],
            'requires_professional_review': False,
            'review_reasons': [],
            'conversation_history': [
                SystemMessage(content="""You are a mental health assessment assistant administering
standardized psychometric scales. Present questions clearly and supportively.
Never diagnose or provide treatment recommendations.""")
            ],
            'agent_response': intro_message,
            'is_complete': False,
            'summary_verified': False,
            'verification_errors': [],
            'retry_count': 0
        }

    except Exception as e:
        return {
            **state,
            'agent_response': f"Error initializing assessment: {str(e)}"
        }


def present_scale_item(state: AssessmentState) -> AssessmentState:
    """
    Node: Present the current scale item to the user.
    Uses LLM only for formatting/presentation, not for content.
    """
    current_scale = state.get('current_scale_code')
    current_item_num = state.get('current_item_number', 1)

    if not current_scale:
        return {
            **state,
            'agent_response': "No scale to administer.",
            'phase': 'summary'
        }

    # Get the item from database
    item = get_scale_item(current_scale, current_item_num)

    if not item:
        # Item doesn't exist - maybe we've finished this scale
        total_items = get_total_items_for_scale(current_scale)
        if current_item_num > total_items:
            # Scale complete, handled by advance_to_next_item
            return state
        return {
            **state,
            'agent_response': f"Error: Could not find item {current_item_num} for scale {current_scale}"
        }

    # Format the question
    total_items = get_total_items_for_scale(current_scale)
    options_text = format_likert_options(item['response_options'])

    question_message = f"""**{current_scale} - Question {current_item_num} of {total_items}**

{item['question_text']}

Please respond with a number:
{options_text}"""

    return {
        **state,
        'current_item': item,
        'awaiting_response_type': 'likert',
        'agent_response': question_message
    }


def collect_likert_response(state: AssessmentState) -> AssessmentState:
    """
    Node: Collect and validate a Likert response.
    NO LLM - pure algorithmic validation.
    """
    from assessments.models import AssessmentSession, ScaleItem, ScaleResponse

    user_input = state.get('user_message', '').strip()
    current_item = state.get('current_item')
    session_id = state['session_id']

    if not current_item or not user_input:
        return {
            **state,
            'agent_response': "Please provide a response to continue."
        }

    try:
        session = AssessmentSession.objects.get(id=session_id)
        item = ScaleItem.objects.get(id=current_item['id'])

        # Validate and parse the response
        validation = response_validator.validate_and_parse(item, user_input)

        if not validation.valid:
            # Return error message, stay on same item
            return {
                **state,
                'agent_response': validation.errors[0] if validation.errors else "Invalid response. Please try again."
            }

        # Store the response (scored_value computed automatically on save)
        response, created = ScaleResponse.objects.update_or_create(
            session=session,
            item=item,
            defaults={
                'numeric_value': validation.numeric_value,
                'scored_value': item.get_scored_value(validation.numeric_value)
            }
        )

        # Track critical responses
        critical_detected = list(state.get('critical_responses_detected', []))
        review_reasons = list(state.get('review_reasons', []))
        requires_review = state.get('requires_professional_review', False)

        if validation.is_critical:
            critical_detected.append({
                'scale': current_item['scale_code'],
                'item': current_item['item_number'],
                'value': validation.numeric_value,
                'message': validation.critical_message
            })
            review_reasons.append(validation.critical_message)
            requires_review = True

        # Update conversation history
        new_history = [
            HumanMessage(content=user_input)
        ]

        return {
            **state,
            'conversation_history': new_history,
            'critical_responses_detected': critical_detected,
            'requires_professional_review': requires_review,
            'review_reasons': review_reasons,
            'awaiting_response_type': 'none'
        }

    except Exception as e:
        return {
            **state,
            'agent_response': f"Error recording response: {str(e)}"
        }


def advance_to_next_item(state: AssessmentState) -> AssessmentState:
    """
    Node: Advance to the next item or scale.
    NO LLM - pure state management and scoring.
    """
    from assessments.models import AssessmentSession, PsychometricScale

    session_id = state['session_id']
    current_scale_code = state.get('current_scale_code')
    current_item_num = state.get('current_item_number', 1)
    scales_to_administer = state.get('scales_to_administer', [])
    completed_scales = list(state.get('completed_scales', []))

    try:
        session = AssessmentSession.objects.get(id=session_id)

        # Get total items in current scale
        total_items = get_total_items_for_scale(current_scale_code)
        next_item_num = current_item_num + 1

        if next_item_num <= total_items:
            # More items in this scale
            session.current_item_number = next_item_num
            session.save()

            return {
                **state,
                'current_item_number': next_item_num
            }
        else:
            # Scale complete - compute score
            scale = PsychometricScale.objects.get(code=current_scale_code)
            score_result = scoring_engine.compute_scale_score(session, scale)
            scoring_engine.save_score(session, scale, score_result)

            # Update completed scales
            completed_scales.append(current_scale_code)

            # Update computed scores in state
            computed_scores = dict(state.get('computed_scores', {}))
            computed_scores[current_scale_code] = {
                'total_score': score_result.total_score,
                'max_possible_score': score_result.max_possible_score,
                'severity_level': score_result.severity_level,
                'has_critical_response': score_result.has_critical_response
            }

            # Check if more scales remain
            remaining_scales = [s for s in scales_to_administer if s not in completed_scales]

            if remaining_scales:
                # Move to next scale
                next_scale = remaining_scales[0]
                next_scale_obj = PsychometricScale.objects.get(code=next_scale)

                session.current_scale_id = next_scale_obj.id
                session.current_item_number = 1
                session.save()

                # Build transition message
                transition_msg = f"""You've completed the {current_scale_code}.

**Your {current_scale_code} Score: {score_result.total_score}/{score_result.max_possible_score}**
Severity Level: {score_result.severity_level.replace('_', ' ').title()}

Now let's continue with the next questionnaire: **{next_scale_obj.name}**"""

                return {
                    **state,
                    'completed_scales': completed_scales,
                    'current_scale_code': next_scale,
                    'current_item_number': 1,
                    'computed_scores': computed_scores,
                    'agent_response': transition_msg
                }
            else:
                # All scales complete
                session.phase = 'follow_up'
                session.save()

                return {
                    **state,
                    'completed_scales': completed_scales,
                    'current_scale_code': None,
                    'computed_scores': computed_scores,
                    'phase': 'follow_up'
                }

    except Exception as e:
        return {
            **state,
            'agent_response': f"Error advancing: {str(e)}"
        }


def ask_follow_up(state: AssessmentState) -> AssessmentState:
    """
    Node: Ask optional follow-up questions based on scores.
    Uses LLM to generate contextual follow-up questions.
    """
    computed_scores = state.get('computed_scores', {})

    # Build score summary
    score_lines = []
    for code, data in computed_scores.items():
        score_lines.append(
            f"- {code}: {data['total_score']}/{data['max_possible_score']} ({data['severity_level']})"
        )

    scores_summary = "\n".join(score_lines)

    follow_up_msg = f"""You've completed all the questionnaires.

**Your Results Summary:**
{scores_summary}

Before I generate your assessment report, is there anything else you'd like to share about how you've been feeling? Any additional concerns or context that might be helpful for the professional review?

(Type your response, or type "done" to proceed to your summary)"""

    return {
        **state,
        'awaiting_response_type': 'free_text',
        'agent_response': follow_up_msg
    }


def collect_free_text(state: AssessmentState) -> AssessmentState:
    """
    Node: Collect optional free-text response.
    Stores verbatim (NO LLM processing in storage).
    """
    from assessments.models import AssessmentSession, FreeTextResponse

    user_input = state.get('user_message', '').strip()
    session_id = state['session_id']

    if not user_input:
        return {
            **state,
            'phase': 'summary'
        }

    # Check if user wants to skip
    if user_input.lower() in ['done', 'skip', 'no', 'nothing', 'n/a']:
        return {
            **state,
            'phase': 'summary',
            'awaiting_response_type': 'none'
        }

    try:
        session = AssessmentSession.objects.get(id=session_id)

        # Store the response verbatim
        FreeTextResponse.objects.create(
            session=session,
            context_type='additional_concerns',
            prompt_text="Is there anything else you'd like to share about how you've been feeling?",
            response_text=user_input
        )

        # Check for distress signals
        distress_check = distress_detector.check_free_text(user_input)

        review_reasons = list(state.get('review_reasons', []))
        requires_review = state.get('requires_professional_review', False)

        if distress_check['requires_review']:
            requires_review = True
            review_reasons.append(distress_check['message'])

        return {
            **state,
            'phase': 'summary',
            'awaiting_response_type': 'none',
            'requires_professional_review': requires_review,
            'review_reasons': review_reasons,
            'conversation_history': [HumanMessage(content=user_input)]
        }

    except Exception as e:
        return {
            **state,
            'agent_response': f"Error recording response: {str(e)}"
        }


def generate_grounded_summary(state: AssessmentState) -> AssessmentState:
    """
    Node: Generate assessment summary.

    IMPORTANT: LLM is used ONLY for narrative generation.
    All scores come from deterministic scoring engine.
    Summary will be verified in next node.
    """
    from assessments.models import AssessmentSession, GroundedSummary, FreeTextResponse

    session_id = state['session_id']

    try:
        session = AssessmentSession.objects.get(id=session_id)

        # Get computed scores (deterministic)
        score_summary = scoring_engine.get_score_summary_dict(session)
        severity_summary = scoring_engine.get_severity_summary_dict(session)

        # Get free text responses
        free_texts = FreeTextResponse.objects.filter(session=session)
        additional_context = "\n".join([f"- {ft.response_text}" for ft in free_texts])

        # Build the summary prompt with explicit constraints
        llm = get_llm()

        # Format scores for the prompt
        score_text = ""
        for code, data in score_summary.items():
            score_text += f"""
{code}:
  - Total Score: {data['total_score']}/{data['max_possible_score']}
  - Severity: {data['severity_level']}
  - Interpretation: {data['clinical_interpretation']}
"""
            if data.get('has_critical_response'):
                score_text += f"  - CRITICAL ITEMS FLAGGED: {data['critical_item_details']}\n"

        summary_prompt = f"""Generate a professional assessment summary based on the following VERIFIED scores.

CRITICAL RULES:
1. You MUST use the EXACT scores provided - do not round, estimate, or modify
2. You MUST use the EXACT severity levels provided
3. If you quote the patient, you MUST use their exact words from the additional context
4. Do NOT diagnose conditions - only report what the scales indicate
5. Do NOT invent symptoms not measured by these scales

VERIFIED ASSESSMENT SCORES:
{score_text}

ADDITIONAL CONTEXT (verbatim patient responses):
{additional_context if additional_context else "No additional context provided."}

Generate a summary with these sections:
1. Assessment Overview (which scales administered)
2. Results Summary (cite EXACT scores and severity levels)
3. Areas of Concern (based on severity levels and critical items)
4. Recommendations for Professional Review

Format the summary in a clear, professional manner suitable for clinical review."""

        response = llm.invoke([HumanMessage(content=summary_prompt)])
        summary_text = response.content

        # Determine completion status
        all_scores = scoring_engine.compute_all_scores(session)

        # Create/update GroundedSummary
        summary_obj, created = GroundedSummary.objects.update_or_create(
            session=session,
            defaults={
                'score_summary': score_summary,
                'severity_summary': severity_summary,
                'narrative_summary': summary_text,
                'completion_status': all_scores.completion_status,
                'missing_scales': all_scores.missing_scales,
                'requires_professional_review': all_scores.overall_requires_review or state.get('requires_professional_review', False),
                'review_reasons': all_scores.review_reasons + state.get('review_reasons', []),
                'is_verified': False  # Will be set by verify_summary
            }
        )

        return {
            **state,
            'summary_text': summary_text,
            'phase': 'summary'
        }

    except Exception as e:
        return {
            **state,
            'agent_response': f"Error generating summary: {str(e)}"
        }


def verify_summary(state: AssessmentState) -> AssessmentState:
    """
    Node: Verify the generated summary for hallucinations.
    NO LLM - pure algorithmic fact-checking.
    """
    from assessments.models import AssessmentSession

    session_id = state['session_id']
    summary_text = state.get('summary_text', '')
    retry_count = state.get('retry_count', 0)

    try:
        session = AssessmentSession.objects.get(id=session_id)

        # Run verification
        result = summary_verifier.verify(session, summary_text)

        # Save verification results
        summary_verifier.save_verification_results(session, result)

        if result.is_valid:
            return {
                **state,
                'summary_verified': True,
                'verification_errors': []
            }
        else:
            # Summary has errors
            if retry_count < 2:
                # Retry generation
                return {
                    **state,
                    'summary_verified': False,
                    'verification_errors': result.errors,
                    'retry_count': retry_count + 1
                }
            else:
                # Accept with warnings after max retries
                return {
                    **state,
                    'summary_verified': False,
                    'verification_errors': result.errors
                }

    except Exception as e:
        return {
            **state,
            'verification_errors': [str(e)]
        }


def end_assessment(state: AssessmentState) -> AssessmentState:
    """
    Node: Finalize the assessment.
    """
    from assessments.models import AssessmentSession

    session_id = state['session_id']

    try:
        session = AssessmentSession.objects.get(id=session_id)

        # Determine final status
        if state.get('requires_professional_review'):
            session.status = 'requires_review'
        else:
            session.status = 'completed'

        session.phase = 'completed'
        session.save()

        # Build final message
        verification_status = "✓ Verified" if state.get('summary_verified') else "⚠ Requires Manual Review"

        final_msg = f"""**Assessment Complete**

Your responses have been recorded and your assessment summary has been generated.

Summary Status: {verification_status}
Review Status: {'Flagged for Priority Review' if state.get('requires_professional_review') else 'Standard Review'}

{state.get('summary_text', '')}

---

This information will be reviewed by a mental health professional. If you're experiencing a crisis, please contact a crisis helpline or go to your nearest emergency room.

Thank you for completing this assessment."""

        return {
            **state,
            'is_complete': True,
            'phase': 'completed',
            'agent_response': final_msg
        }

    except Exception as e:
        return {
            **state,
            'agent_response': f"Error finalizing assessment: {str(e)}"
        }


# =============================================================================
# ROUTING FUNCTIONS
# =============================================================================

def route_after_likert_collection(state: AssessmentState) -> str:
    """Route after collecting a Likert response"""
    if state.get('awaiting_response_type') == 'likert':
        # Still awaiting - validation failed, re-present
        return "present_scale_item"
    else:
        # Response collected, advance
        return "advance_to_next_item"


def route_after_advance(state: AssessmentState) -> str:
    """Route after advancing to next item"""
    if state.get('phase') == 'follow_up':
        return "ask_follow_up"
    elif state.get('current_scale_code'):
        return "present_scale_item"
    else:
        return "ask_follow_up"


def route_after_free_text(state: AssessmentState) -> str:
    """Route after collecting free text"""
    if state.get('phase') == 'summary':
        return "generate_grounded_summary"
    else:
        return "ask_follow_up"


def route_after_verification(state: AssessmentState) -> str:
    """Route after summary verification"""
    if state.get('summary_verified'):
        return "end_assessment"
    elif state.get('retry_count', 0) < 2:
        return "generate_grounded_summary"
    else:
        # Accept with warnings after max retries
        return "end_assessment"


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================

def create_assessment_graph():
    """Create and compile the scale-based assessment workflow graph"""

    workflow = StateGraph(AssessmentState)

    # Add nodes
    workflow.add_node("introduce_assessment", introduce_assessment)
    workflow.add_node("present_scale_item", present_scale_item)
    workflow.add_node("collect_likert_response", collect_likert_response)
    workflow.add_node("advance_to_next_item", advance_to_next_item)
    workflow.add_node("ask_follow_up", ask_follow_up)
    workflow.add_node("collect_free_text", collect_free_text)
    workflow.add_node("generate_grounded_summary", generate_grounded_summary)
    workflow.add_node("verify_summary", verify_summary)
    workflow.add_node("end_assessment", end_assessment)

    # Set entry point
    workflow.set_entry_point("introduce_assessment")

    # Add edges
    workflow.add_edge("introduce_assessment", "present_scale_item")

    # Present item -> END (wait for user input)
    workflow.add_edge("present_scale_item", END)

    # After collecting response, route based on validation
    workflow.add_conditional_edges(
        "collect_likert_response",
        route_after_likert_collection,
        {
            "present_scale_item": "present_scale_item",
            "advance_to_next_item": "advance_to_next_item"
        }
    )

    # After advancing, route to next item or follow-up
    workflow.add_conditional_edges(
        "advance_to_next_item",
        route_after_advance,
        {
            "present_scale_item": "present_scale_item",
            "ask_follow_up": "ask_follow_up"
        }
    )

    # Follow-up question -> END (wait for user input)
    workflow.add_edge("ask_follow_up", END)

    # After free text, go to summary
    workflow.add_conditional_edges(
        "collect_free_text",
        route_after_free_text,
        {
            "generate_grounded_summary": "generate_grounded_summary",
            "ask_follow_up": "ask_follow_up"
        }
    )

    # Summary -> verify
    workflow.add_edge("generate_grounded_summary", "verify_summary")

    # Verify -> end or retry
    workflow.add_conditional_edges(
        "verify_summary",
        route_after_verification,
        {
            "end_assessment": "end_assessment",
            "generate_grounded_summary": "generate_grounded_summary"
        }
    )

    # End -> END
    workflow.add_edge("end_assessment", END)

    # Create checkpointer for persistence
    checkpointer = MemorySaver()

    # Compile
    app = workflow.compile(checkpointer=checkpointer)

    return app


# Create the global assessment graph instance
assessment_graph = create_assessment_graph()


# =============================================================================
# LEGACY SUPPORT
# =============================================================================

# Keep old questions for legacy sessions
ASSESSMENT_QUESTIONS = {
    'mood': "How would you describe your mood and emotional wellbeing over the past 2 weeks?",
    'stress': "What are your current stress levels? What situations or factors contribute to your stress?",
    'sleep': "How have you been sleeping? How many hours per night, and is your sleep restful?",
    'anxiety': "Have you experienced any anxiety symptoms? If so, please describe when and how they occur.",
    'daily_activities': "How are you managing your daily activities and responsibilities?",
    'concerns': "What are your main concerns or challenges you'd like to discuss?"
}


# Legacy functions (kept for backwards compatibility with views)
def start_assessment(state: AssessmentState) -> AssessmentState:
    """Legacy: Initialize the assessment session"""
    return introduce_assessment(state)


def ask_question(state: AssessmentState) -> AssessmentState:
    """Legacy: Present the next question"""
    return present_scale_item(state)


def collect_response(state: AssessmentState) -> AssessmentState:
    """Legacy: Collect user response"""
    return collect_likert_response(state)


def check_completeness(state: AssessmentState) -> AssessmentState:
    """Legacy: Check if assessment is complete"""
    return state


def generate_summary(state: AssessmentState) -> AssessmentState:
    """Legacy: Generate summary"""
    return generate_grounded_summary(state)


def validate_summary(state: AssessmentState) -> AssessmentState:
    """Legacy: Validate summary"""
    return verify_summary(state)


def flag_for_review(state: AssessmentState) -> AssessmentState:
    """Legacy: Flag for review"""
    return {
        **state,
        'requires_professional_review': True,
        'agent_response': "This assessment has been flagged for priority professional review."
    }
