"""
Django views for Mental Health Assessment System
Updated for scale-based assessments with hallucination safeguards
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
import json

from .models import (
    AssessmentSession, AssessmentResponse, AssessmentSummary,
    PsychometricScale, ScaleResponse, ScaleScore, GroundedSummary, FreeTextResponse
)
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
    """Initialize a new assessment session with scale-based workflow"""

    def get(self, request):
        # Create a new assessment session
        user_id = request.session.get('user_id', f'user_{request.session.session_key}')

        session = AssessmentSession.objects.create(
            user_identifier=user_id,
            status='in_progress',
            phase='introduction'
        )

        # Assign default scales (PHQ-9, GAD-7, PSS-10, ISI)
        default_scales = PsychometricScale.objects.filter(
            code__in=['PHQ9', 'GAD7', 'PSS10', 'ISI'],
            is_active=True
        ).order_by('order')

        for scale in default_scales:
            session.assigned_scales.add(scale)

        # Set first scale as current
        if default_scales.exists():
            session.current_scale = default_scales.first()
            session.current_item_number = 1
            session.save()

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
    """Interactive chat interface for scale-based assessment"""

    def get(self, request, session_id):
        session = get_object_or_404(AssessmentSession, id=session_id)

        # Check if this is a scale-based or legacy session
        if session.is_legacy_format():
            return self._legacy_chat_view(request, session)

        # Get scale-based context
        current_question = self._get_current_question(session)
        conversation_history = self._build_conversation_history(session)
        is_complete = session.phase == 'completed'

        context = {
            'session': session,
            'current_question': current_question,
            'conversation_history': conversation_history,
            'is_complete': is_complete,
        }

        return render(request, 'assessments/assessment_form.html', context)

    def _get_current_question(self, session):
        """Get the current question to display"""
        if session.phase == 'completed':
            return "Assessment complete. Thank you!"

        if session.phase == 'follow_up':
            return """You've completed all the questionnaires.

Before I generate your assessment report, is there anything else you'd like to share about how you've been feeling? Any additional concerns or context that might be helpful for the professional review?

(Type your response, or type "done" to proceed to your summary)"""

        if session.phase == 'summary':
            return "Generating your assessment summary..."

        # Get current scale item
        if session.current_scale:
            from .services.agent_graph import get_scale_item, format_likert_options, get_total_items_for_scale

            item = get_scale_item(session.current_scale.code, session.current_item_number)
            if item:
                total_items = get_total_items_for_scale(session.current_scale.code)
                options_text = format_likert_options(item['response_options'])

                return f"""**{session.current_scale.code} - Question {session.current_item_number} of {total_items}**

{item['question_text']}

Please respond with a number:
{options_text}"""

        return "Welcome to your mental health assessment. Let's begin."

    def _build_conversation_history(self, session):
        """Build conversation history from stored responses"""
        history = []

        # Get scale responses
        responses = ScaleResponse.objects.filter(session=session).select_related('item__scale').order_by('timestamp')

        for response in responses:
            # Add agent question
            history.append({
                'type': 'agent',
                'text': f"**{response.item.scale.code} Q{response.item.item_number}**: {response.item.question_text}"
            })
            # Add user response
            label = self._get_response_label(response.item, response.numeric_value)
            history.append({
                'type': 'user',
                'text': f"{response.numeric_value} - {label}"
            })

        # Get free text responses
        for ft in FreeTextResponse.objects.filter(session=session).order_by('timestamp'):
            history.append({
                'type': 'agent',
                'text': ft.prompt_text
            })
            history.append({
                'type': 'user',
                'text': ft.response_text
            })

        return history

    def _get_response_label(self, item, value):
        """Get the label for a numeric response value"""
        for opt in item.response_options:
            if opt.get('value') == value:
                return opt.get('label', '')
        return str(value)

    def _legacy_chat_view(self, request, session):
        """Handle legacy (non-scale) assessments"""
        from .services.tools import identify_missing_categories
        from .services.agent_graph import ASSESSMENT_QUESTIONS

        responses = session.responses.all().order_by('timestamp')
        missing_info = identify_missing_categories.invoke({'session_id': str(session.id)})
        missing_categories = missing_info.get('missing_categories', [])

        if missing_categories:
            next_category = missing_categories[0]
            current_question = ASSESSMENT_QUESTIONS[next_category]
        else:
            current_question = "Thank you for completing all the assessment questions."

        conversation_history = []
        for response in responses:
            conversation_history.append({'type': 'agent', 'text': response.question_text})
            conversation_history.append({'type': 'user', 'text': response.response_text})

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

            # Check if legacy or scale-based
            if session.is_legacy_format():
                return self._handle_legacy_message(session, user_message)

            return self._handle_scale_message(session, user_message)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in AssessmentMessageView: {error_details}")

            return JsonResponse({
                'status': 'error',
                'message': f"Error: {str(e)}",
                'details': error_details if settings.DEBUG else None
            }, status=500)

    def _handle_scale_message(self, session, user_message):
        """Handle scale-based assessment messages"""
        from .services.agent_graph import (
            collect_likert_response, advance_to_next_item,
            present_scale_item, ask_follow_up, collect_free_text,
            generate_grounded_summary, verify_summary, end_assessment,
            get_scale_item
        )

        # Get scales that have been completed (have ScaleScore records)
        completed_scales = list(
            ScaleScore.objects.filter(session=session).values_list('scale__code', flat=True)
        )

        # Get computed scores from database
        computed_scores = {}
        for score in ScaleScore.objects.filter(session=session).select_related('scale'):
            computed_scores[score.scale.code] = {
                'total_score': score.total_score,
                'max_possible_score': score.max_possible_score,
                'severity_level': score.severity_level,
                'has_critical_response': score.has_critical_response
            }

        # Build current state
        state = {
            'session_id': str(session.id),
            'user_message': user_message,
            'current_scale_code': session.current_scale.code if session.current_scale else None,
            'current_item_number': session.current_item_number,
            'scales_to_administer': list(session.assigned_scales.order_by('order').values_list('code', flat=True)),
            'completed_scales': completed_scales,
            'current_item': None,
            'awaiting_response_type': 'likert' if session.phase == 'scales' else 'free_text',
            'computed_scores': computed_scores,
            'critical_responses_detected': [],
            'requires_professional_review': session.status == 'requires_review',
            'review_reasons': [],
            'conversation_history': [],
            'phase': session.phase,
            'is_complete': False,
            'summary_text': '',
            'summary_verified': False,
            'verification_errors': [],
            'retry_count': 0
        }

        # Get current item if in scales phase
        if session.phase == 'scales' and session.current_scale:
            item = get_scale_item(session.current_scale.code, session.current_item_number)
            if item:
                state['current_item'] = item

        # Process based on phase
        if session.phase == 'scales':
            # Collect response
            state = collect_likert_response(state)

            if state.get('awaiting_response_type') == 'likert':
                # Validation failed
                return JsonResponse({
                    'status': 'success',
                    'message': state.get('agent_response', 'Invalid response. Please try again.'),
                    'is_complete': False
                })

            # Advance to next
            state = advance_to_next_item(state)

            if state.get('phase') == 'follow_up':
                # All scales done
                state = ask_follow_up(state)
                session.phase = 'follow_up'
                session.save()

                return JsonResponse({
                    'status': 'success',
                    'message': state.get('agent_response', ''),
                    'is_complete': False
                })

            # More questions
            state = present_scale_item(state)

            return JsonResponse({
                'status': 'success',
                'message': state.get('agent_response', ''),
                'is_complete': False
            })

        elif session.phase == 'follow_up':
            # Collect free text
            state = collect_free_text(state)

            if state.get('phase') == 'summary':
                session.phase = 'summary'
                session.save()

                # Generate and verify summary
                state = generate_grounded_summary(state)
                state = verify_summary(state)
                state = end_assessment(state)

                return JsonResponse({
                    'status': 'success',
                    'message': state.get('agent_response', 'Assessment complete!'),
                    'is_complete': True
                })

            # Still collecting
            return JsonResponse({
                'status': 'success',
                'message': state.get('agent_response', ''),
                'is_complete': False
            })

        return JsonResponse({
            'status': 'success',
            'message': 'Assessment complete.',
            'is_complete': True
        })

    def _handle_legacy_message(self, session, user_message):
        """Handle legacy assessment messages"""
        from .services.tools import identify_missing_categories
        from .services.agent_graph import (
            collect_response, check_completeness, ask_question,
            generate_summary, validate_summary, end_assessment, flag_for_review,
            ASSESSMENT_QUESTIONS
        )

        # Get current state
        missing_info = identify_missing_categories.invoke({'session_id': str(session.id)})

        state = {
            'session_id': str(session.id),
            'user_message': user_message,
            'missing_categories': missing_info.get('missing_categories', []),
            'collected_responses': {},
            'is_complete': missing_info.get('is_complete', False),
            'requires_review': False,
            'distress_detected': False,
        }

        # Collect the response
        state = collect_response(state)

        # Check completeness
        state = check_completeness(state)

        # Determine next action
        if state.get('is_complete'):
            state = generate_summary(state)
            state = validate_summary(state)
            state = end_assessment(state)

            agent_message = state.get('agent_response', 'Assessment complete!')
            is_complete = True
        elif state.get('distress_detected'):
            state = flag_for_review(state)
            state = ask_question(state)
            agent_message = state.get('agent_response', '')
            is_complete = False
        elif state.get('validation_errors'):
            agent_message = state.get('agent_response', 'Please provide more detail.')
            is_complete = False
        else:
            state = ask_question(state)
            agent_message = state.get('agent_response', '')
            is_complete = False

        return JsonResponse({
            'status': 'success',
            'message': agent_message,
            'is_complete': is_complete,
            'session_status': session.status
        })


class SummaryDetailView(DetailView):
    """Display completed assessment summary"""
    model = AssessmentSession
    template_name = 'assessments/summary_detail.html'
    context_object_name = 'session'
    pk_url_kwarg = 'session_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # Check if scale-based or legacy
        if not session.is_legacy_format():
            # Scale-based assessment
            context['scale_scores'] = ScaleScore.objects.filter(
                session=session
            ).select_related('scale').order_by('scale__order')

            # Get grounded summary
            try:
                context['grounded_summary'] = session.grounded_summary
            except GroundedSummary.DoesNotExist:
                context['grounded_summary'] = None

            # Get scale responses grouped by scale
            responses = ScaleResponse.objects.filter(
                session=session
            ).select_related('item__scale').order_by('item__scale__order', 'item__item_number')

            scale_responses_by_scale = {}
            for response in responses:
                scale_code = response.item.scale.code
                if scale_code not in scale_responses_by_scale:
                    scale_responses_by_scale[scale_code] = []
                scale_responses_by_scale[scale_code].append(response)

            context['scale_responses_by_scale'] = scale_responses_by_scale

        else:
            # Legacy assessment
            try:
                context['summary'] = session.summary
            except AssessmentSummary.DoesNotExist:
                context['summary'] = None

            responses_by_category = session.get_responses_by_category()
            formatted_responses = {}
            for category, responses in responses_by_category.items():
                formatted_category = category.replace('_', ' ').title()
                formatted_responses[formatted_category] = responses

            context['responses_by_category'] = formatted_responses

        return context


class ReviewAssessmentView(View):
    """Human-in-the-loop review interface"""

    def get(self, request, session_id):
        session = get_object_or_404(AssessmentSession, id=session_id)

        context = {
            'session': session,
        }

        # Check if scale-based or legacy
        if not session.is_legacy_format():
            context['scale_scores'] = ScaleScore.objects.filter(
                session=session
            ).select_related('scale').order_by('scale__order')

            try:
                context['grounded_summary'] = session.grounded_summary
            except GroundedSummary.DoesNotExist:
                context['grounded_summary'] = None

            # Get responses by scale
            responses = ScaleResponse.objects.filter(
                session=session
            ).select_related('item__scale').order_by('item__scale__order', 'item__item_number')

            scale_responses_by_scale = {}
            for response in responses:
                scale_code = response.item.scale.code
                if scale_code not in scale_responses_by_scale:
                    scale_responses_by_scale[scale_code] = []
                scale_responses_by_scale[scale_code].append(response)

            context['scale_responses_by_scale'] = scale_responses_by_scale
        else:
            try:
                context['summary'] = session.summary
            except AssessmentSummary.DoesNotExist:
                context['summary'] = None

            responses_by_category = session.get_responses_by_category()
            formatted_responses = {}
            for category, responses in responses_by_category.items():
                formatted_category = category.replace('_', ' ').title()
                formatted_responses[formatted_category] = responses

            context['responses_by_category'] = formatted_responses

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
