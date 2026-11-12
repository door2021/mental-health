"""
URL configuration for assessment app
"""
from django.urls import path
from .views import (
    DashboardView,
    StartAssessmentView,
    AssessmentChatView,
    AssessmentMessageView,
    SummaryDetailView,
    ReviewAssessmentView,
    DeleteAssessmentView
)

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('start/', StartAssessmentView.as_view(), name='start_assessment'),
    path('assessment/<int:session_id>/', AssessmentChatView.as_view(), name='assessment_chat'),
    path('assessment/<int:session_id>/message/', AssessmentMessageView.as_view(), name='assessment_message'),
    path('summary/<int:session_id>/', SummaryDetailView.as_view(), name='summary_detail'),
    path('review/<int:session_id>/', ReviewAssessmentView.as_view(), name='review_assessment'),
    path('delete/<int:session_id>/', DeleteAssessmentView.as_view(), name='delete_assessment'),
]
