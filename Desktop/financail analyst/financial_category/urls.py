from django.urls import path
from .views import (
    GoalSavingVisualizationView,
    DebtVisualizationView,
    ExpenseVisualizationView,
    CategoryOverviewView,
)

urlpatterns = [
    path('categories/', CategoryOverviewView.as_view(), name='category-overview'),
    path('savings/visualization/', GoalSavingVisualizationView.as_view(), name='savings-visualization'),
    path('debts/visualization/', DebtVisualizationView.as_view(), name='debt-visualization'),
    path('expenses/visualization/', ExpenseVisualizationView.as_view(), name='expense-visualization'),
]
