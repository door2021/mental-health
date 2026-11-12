"""
LangGraph State Graph for Mental Health Assessment Agent
"""
from typing import TypedDict, List, Dict, Any, Annotated
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import operator
from django.conf import settings

from .tools import (
    store_response,
    retrieve_responses,
    validate_response,
    identify_missing_categories,
    check_distress_signals
)


class AssessmentState(TypedDict):
    """State schema for the assessment workflow"""
    session_id: str
    collected_responses: Dict[str, Any]
    missing_categories: List[str]
    current_question: str
    conversation_history: Annotated[List[Any], operator.add]
    summary: str
    requires_review: bool
    validation_errors: List[str]
    user_message: str
    agent_response: str
    is_complete: bool
    distress_detected: bool


# Assessment questions for each category
ASSESSMENT_QUESTIONS = {
    'mood': "How would you describe your mood and emotional wellbeing over the past 2 weeks?",
    'stress': "What are your current stress levels? What situations or factors contribute to your stress?",
    'sleep': "How have you been sleeping? How many hours per night, and is your sleep restful?",
    'anxiety': "Have you experienced any anxiety symptoms? If so, please describe when and how they occur.",
    'daily_activities': "How are you managing your daily activities and responsibilities?",
    'concerns': "What are your main concerns or challenges you'd like to discuss?"
}


def start_assessment(state: AssessmentState) -> AssessmentState:
    """Initialize the assessment session"""
    return {
        **state,
        'collected_responses': {},
        'missing_categories': list(ASSESSMENT_QUESTIONS.keys()),
        'conversation_history': [
            SystemMessage(content="""You are a compassionate mental health assessment assistant. 
            Your role is to conduct a structured initial assessment by asking questions about mood, 
            stress, sleep, anxiety, daily activities, and personal concerns. 
            
            Important guidelines:
            - Be empathetic and supportive
            - Never diagnose or provide treatment
            - Ask one question at a time
            - If you detect distress signals, acknowledge them compassionately
            - Your goal is to collect information for a professional to review
            """)
        ],
        'is_complete': False,
        'requires_review': False,
        'distress_detected': False
    }


def ask_question(state: AssessmentState) -> AssessmentState:
    """Present the next question based on missing categories"""
    missing = state.get('missing_categories', [])
    
    if not missing:
        return {
            **state,
            'agent_response': "Thank you for completing all the assessment questions. Let me generate a summary for review."
        }
    
    # Get the first missing category
    next_category = missing[0]
    question = ASSESSMENT_QUESTIONS[next_category]
    
    return {
        **state,
        'current_question': question,
        'agent_response': question
    }


def collect_response(state: AssessmentState) -> AssessmentState:
    """Collect and store the user's response"""
    session_id = state['session_id']
    user_message = state.get('user_message', '')
    
    if not user_message:
        return state
    
    # Determine which category this response is for
    missing = state.get('missing_categories', [])
    if not missing:
        return state
    
    current_category = missing[0]
    question = ASSESSMENT_QUESTIONS[current_category]
    
    # Validate the response
    validation = validate_response.invoke({
        'category': current_category,
        'response': user_message
    })
    
    if not validation.get('valid', False):
        return {
            **state,
            'validation_errors': validation.get('errors', []),
            'agent_response': f"I noticed your response is quite brief. {validation['errors'][0]} Could you please provide more detail?"
        }
    
    # Check for distress signals
    distress_check = check_distress_signals.invoke({'response_text': user_message})
    
    # Store the response
    store_result = store_response.invoke({
        'session_id': session_id,
        'category': current_category,
        'question': question,
        'response': user_message
    })
    
    # Update collected responses
    collected = state.get('collected_responses', {})
    collected[current_category] = user_message
    
    # Remove from missing categories
    updated_missing = [cat for cat in missing if cat != current_category]
    
    # Update conversation history
    new_history = [
        HumanMessage(content=user_message),
    ]
    
    return {
        **state,
        'collected_responses': collected,
        'missing_categories': updated_missing,
        'validation_errors': [],
        'conversation_history': new_history,
        'requires_review': state.get('requires_review', False) or distress_check.get('requires_review', False),
        'distress_detected': distress_check.get('requires_immediate_review', False)
    }


def check_completeness(state: AssessmentState) -> AssessmentState:
    """Check if assessment is complete"""
    missing = state.get('missing_categories', [])
    
    return {
        **state,
        'is_complete': len(missing) == 0
    }


def generate_summary(state: AssessmentState) -> AssessmentState:
    """Generate assessment summary using LLM"""
    session_id = state['session_id']
    
    # Retrieve all responses
    responses_data = retrieve_responses.invoke({'session_id': session_id})
    responses = responses_data.get('responses', {})
    
    # Create LLM with Groq
    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.3,
        api_key=settings.GROQ_API_KEY
    )
    
    # Build summary prompt
    summary_prompt = """Based on the following assessment responses, create a structured summary for a mental health professional.

Assessment Responses:
"""
    for category, items in responses.items():
        summary_prompt += f"\n{category.upper()}:\n"
        for item in items:
            summary_prompt += f"Q: {item['question']}\n"
            summary_prompt += f"A: {item['response']}\n\n"
    
    summary_prompt += """
Please provide:
1. A brief summary of reported concerns
2. Key observations about mood, stress, sleep, anxiety, and functioning
3. Any areas that may require immediate professional attention
4. Overall assessment completion status

Format the summary in a clear, professional manner."""
    
    # Generate summary
    summary_response = llm.invoke([HumanMessage(content=summary_prompt)])
    summary_text = summary_response.content
    
    # Save summary to database
    from assessments.models import AssessmentSession, AssessmentSummary
    
    try:
        session = AssessmentSession.objects.get(id=session_id)
        
        # Determine completion status
        completion_status = 'complete' if state['is_complete'] else 'partial'
        
        # Create or update summary
        summary_obj, created = AssessmentSummary.objects.update_or_create(
            session=session,
            defaults={
                'summary_text': summary_text,
                'missing_info': state.get('missing_categories', []),
                'areas_for_review': ['Distress signals detected'] if state.get('distress_detected') else [],
                'completion_status': completion_status,
                'flagged_for_professional': state.get('requires_review', False)
            }
        )
        
        # Update session status
        if state.get('requires_review'):
            session.status = 'requires_review'
        else:
            session.status = 'completed'
        session.save()
        
    except Exception as e:
        print(f"Error saving summary: {e}")
    
    return {
        **state,
        'summary': summary_text
    }


def validate_summary(state: AssessmentState) -> AssessmentState:
    """Validate the generated summary for quality"""
    summary = state.get('summary', '')
    
    # Basic validation checks
    has_minimum_length = len(summary) > 100
    
    return {
        **state,
        'validation_errors': [] if has_minimum_length else ['Summary too short']
    }


def flag_for_review(state: AssessmentState) -> AssessmentState:
    """Flag assessment for professional review if needed"""
    from assessment.models import AssessmentSession
    
    session_id = state['session_id']
    
    try:
        session = AssessmentSession.objects.get(id=session_id)
        session.status = 'requires_review'
        session.save()
    except Exception as e:
        print(f"Error flagging session: {e}")
    
    return {
        **state,
        'agent_response': "Thank you for sharing. I've flagged this assessment for priority review by a mental health professional."
    }


def end_assessment(state: AssessmentState) -> AssessmentState:
    """Finalize the assessment"""
    return {
        **state,
        'agent_response': f"Assessment complete. Summary generated for professional review.\n\n{state.get('summary', '')}"
    }


def route_after_collection(state: AssessmentState) -> str:
    """Route based on whether assessment is complete"""
    if state.get('validation_errors'):
        return "ask_question"  # Re-ask if validation failed
    elif state.get('distress_detected'):
        return "flag_for_review"
    elif state.get('is_complete'):
        return "generate_summary"
    else:
        return "ask_question"


def route_after_summary(state: AssessmentState) -> str:
    """Route after summary generation"""
    if state.get('validation_errors'):
        return "generate_summary"  # Regenerate if validation failed
    else:
        return "end_assessment"


def create_assessment_graph():
    """Create and compile the assessment workflow graph"""
    
    # Create the graph
    workflow = StateGraph(AssessmentState)
    
    # Add nodes
    workflow.add_node("start_assessment", start_assessment)
    workflow.add_node("ask_question", ask_question)
    workflow.add_node("collect_response", collect_response)
    workflow.add_node("check_completeness", check_completeness)
    workflow.add_node("generate_summary", generate_summary)
    workflow.add_node("validate_summary", validate_summary)
    workflow.add_node("flag_for_review", flag_for_review)
    workflow.add_node("end_assessment", end_assessment)
    
    # Set entry point
    workflow.set_entry_point("start_assessment")
    
    # Add edges
    workflow.add_edge("start_assessment", "ask_question")
    workflow.add_edge("ask_question", END)
    workflow.add_edge("check_completeness", END)
    
    # Conditional edge after collecting response
    workflow.add_conditional_edges(
        "collect_response",
        route_after_collection,
        {
            "ask_question": "ask_question",
            "generate_summary": "generate_summary",
            "flag_for_review": "flag_for_review"
        }
    )
    
    # Edge from flag_for_review
    workflow.add_edge("flag_for_review", "generate_summary")
    
    # Validate summary, then end
    workflow.add_edge("generate_summary", "validate_summary")
    workflow.add_conditional_edges(
        "validate_summary",
        route_after_summary,
        {
            "generate_summary": "generate_summary",
            "end_assessment": "end_assessment"
        }
    )
    
    workflow.add_edge("end_assessment", END)
    
    # Create checkpointer for persistence
    checkpointer = MemorySaver()
    
    # Compile the graph
    app = workflow.compile(checkpointer=checkpointer)
    
    return app


# Create the global assessment graph instance
assessment_graph = create_assessment_graph()
