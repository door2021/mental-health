"""
Django views for Mental Health Assessment System
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json

from .models import AssessmentSession, AssessmentResponse, AssessmentSummary
from .services.agent_graph import assessment_graph


class DashboardView(ListView):
    """Dashboard view listing all assessment sessions"""
    model = AssessmentSession
    template_name = 'assessments/dashboard.html'
    context_object_name = 'sessions'
    paginate_by = 10

    def get_queryset(self):
        return AssessmentSession.objects.all().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Calculate statistics
        all_sessions = AssessmentSession.objects.all()
        context['total_count'] = all_sessions.count()
        context['in_progress_count'] = all_sessions.filter(status='in_progress').count()
        context['completed_count'] = all_sessions.filter(status='completed').count()
        context['requires_review_count'] = all_sessions.filter(status='requires_review').count()

        return context


class StartAssessmentView(View):
    """Initialize a new assessment session"""
    
    def get(self, request):
        # Create a new assessment session
        user_id = request.session.get('user_id', f'user_{request.session.session_key}')
        
        session = AssessmentSession.objects.create(
            user_identifier=user_id,
            status='in_progress'
        )
        
        # Initialize the agent state
        initial_state = {
            'session_id': str(session.id),
            'user_message': '',
            'conversation_history': []
        }
        
        # Invoke the agent to start
        config = {"configurable": {"thread_id": str(session.id)}}
        result = assessment_graph.invoke(initial_state, config)
        
        # Redirect to assessment chat
        return redirect('assessment_chat', session_id=session.id)


class AssessmentChatView(View):
    """Interactive chat interface for assessment"""

    def get(self, request, session_id):
        session = get_object_or_404(AssessmentSession, id=session_id)

        # Get existing responses
        responses = session.responses.all().order_by('timestamp')

        # Determine current question based on progress
        from .services.tools import identify_missing_categories
        from .services.agent_graph import ASSESSMENT_QUESTIONS

        missing_info = identify_missing_categories.invoke({'session_id': str(session_id)})
        missing_categories = missing_info.get('missing_categories', [])

        # Determine current question
        if missing_categories:
            next_category = missing_categories[0]
            current_question = ASSESSMENT_QUESTIONS[next_category]
        else:
            current_question = "Thank you for completing all the assessment questions. Let me generate a summary for review."

        # Build conversation history from existing responses
        conversation_history = []
        for response in responses:
            # Add the question that was asked
            conversation_history.append({
                'type': 'agent',
                'text': response.question_text
            })
            # Add the user's response
            conversation_history.append({
                'type': 'user',
                'text': response.response_text
            })

        # Check if assessment is complete
        is_complete = session.status == 'completed' or len(missing_categories) == 0

        context = {
            'session': session,
            'responses': responses,
            'current_question': current_question,
            'conversation_history': conversation_history,
            'is_complete': is_complete,
        }

        return render(request, 'assessments/assessment_form.html', context)


@method_decorator(csrf_exempt, name='dispatch')
class AssessmentMessageView(View):
    """Handle AJAX messages from the chat interface"""
    
    def post(self, request, session_id):
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '')
            
            session = get_object_or_404(AssessmentSession, id=session_id)
            
            # Get current state
            config = {"configurable": {"thread_id": str(session_id)}}

            # First, identify missing categories
            from .services.tools import identify_missing_categories
            missing_info = identify_missing_categories.invoke({'session_id': str(session_id)})

            # Initialize state with missing categories
            state = {
                'session_id': str(session_id),
                'user_message': user_message,
                'missing_categories': missing_info.get('missing_categories', []),
                'collected_responses': {},
                'is_complete': missing_info.get('is_complete', False),
                'requires_review': False,
                'distress_detected': False,
            }

            # Invoke collect_response node
            from .services.agent_graph import collect_response, check_completeness, ask_question

            # Collect the response
            state = collect_response(state)
            
            # Check completeness
            state = check_completeness(state)
            
            # Determine next action
            if state.get('is_complete'):
                # Generate summary
                from .services.agent_graph import generate_summary, validate_summary, end_assessment
                state = generate_summary(state)
                state = validate_summary(state)
                state = end_assessment(state)
                
                agent_message = state.get('agent_response', 'Assessment complete!')
                is_complete = True
            elif state.get('distress_detected'):
                # Flag and continue
                from .services.agent_graph import flag_for_review
                state = flag_for_review(state)
                agent_message = state.get('agent_response', 'Flagged for review.')
                is_complete = False
                
                # Ask next question
                state = ask_question(state)
                agent_message = state.get('agent_response', '')
            elif state.get('validation_errors'):
                # Return validation error
                agent_message = state.get('agent_response', 'Please provide more detail.')
                is_complete = False
            else:
                # Ask next question
                state = ask_question(state)
                agent_message = state.get('agent_response', '')
                is_complete = False
            
            return JsonResponse({
                'status': 'success',
                'message': agent_message,
                'is_complete': is_complete,
                'session_status': session.status
            })
            
        except Exception as e:
            # Log the full error for debugging
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in AssessmentMessageView: {error_details}")

            return JsonResponse({
                'status': 'error',
                'message': f"Error: {str(e)}",
                'details': error_details if settings.DEBUG else None
            }, status=500)


class SummaryDetailView(DetailView):
    """Display completed assessment summary"""
    model = AssessmentSession
    template_name = 'assessments/summary_detail.html'
    context_object_name = 'session'
    pk_url_kwarg = 'session_id'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get summary if it exists
        try:
            context['summary'] = self.object.summary
        except AssessmentSummary.DoesNotExist:
            context['summary'] = None

        # Get all responses grouped by category with formatted names
        responses_by_category = self.object.get_responses_by_category()
        formatted_responses = {}
        for category, responses in responses_by_category.items():
            # Format category name: "daily_activities" -> "Daily Activities"
            formatted_category = category.replace('_', ' ').title()
            formatted_responses[formatted_category] = responses

        context['responses_by_category'] = formatted_responses

        return context


class ReviewAssessmentView(View):
    """Human-in-the-loop review interface"""
    
    def get(self, request, session_id):
        session = get_object_or_404(AssessmentSession, id=session_id)
        
        try:
            summary = session.summary
        except AssessmentSummary.DoesNotExist:
            summary = None

        # Get all responses grouped by category with formatted names
        responses_by_category = session.get_responses_by_category()
        formatted_responses = {}
        for category, responses in responses_by_category.items():
            # Format category name: "daily_activities" -> "Daily Activities"
            formatted_category = category.replace('_', ' ').title()
            formatted_responses[formatted_category] = responses

        context = {
            'session': session,
            'summary': summary,
            'responses_by_category': formatted_responses
        }

        return render(request, 'assessments/review.html', context)
    
    def post(self, request, session_id):
        """Approve or reject the assessment"""
        session = get_object_or_404(AssessmentSession, id=session_id)
        
        action = request.POST.get('action')
        
        if action == 'approve':
            session.status = 'completed'
            session.save()
        elif action == 'reject':
            session.status = 'requires_review'
            session.save()
        
        return redirect('dashboard')


class DeleteAssessmentView(View):
    """Delete an assessment session"""

    def post(self, request, session_id):
        """Delete the assessment"""
        session = get_object_or_404(AssessmentSession, id=session_id)
        session.delete()
        return redirect('dashboard')
