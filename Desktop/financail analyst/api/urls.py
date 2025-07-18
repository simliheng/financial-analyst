# backend/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from financial_category.views import (
    IncomeViewSet,
    ExpenseViewSet,
    DebtViewSet,
    FutureSavingViewSet,
    FinancialCategoryViewSet,
    CategoryOverviewView,
    ImportDataView
)
from users.views import (
    CustomTokenObtainPairView,
    RegisterView,
    LogoutView,
    UserProfileView,
    GoogleLoginView
)
from . import views, admin_views

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'categories', FinancialCategoryViewSet)
router.register(r'incomes', IncomeViewSet)
router.register(r'expenses', ExpenseViewSet)
router.register(r'debts', DebtViewSet)
router.register(r'savings', FutureSavingViewSet)

urlpatterns = [
    # Authentication endpoints
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/user/', UserProfileView.as_view(), name='user'),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/google/', GoogleLoginView.as_view(), name='google-login'),

    # Dashboard and Data
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('import-data/', ImportDataView.as_view(), name='import-data'),
    path('category-overview/', CategoryOverviewView.as_view(), name='category_overview'),

    # Admin endpoints
    path('admin/dashboard_stats/', admin_views.AdminDashboardViewSet.as_view({'get': 'dashboard_stats'}), name='admin-dashboard-stats'),
    path('admin/categories/', admin_views.AdminFinancialCategoryViewSet.as_view({'get': 'list', 'post': 'create'}), name='admin-categories'),
    path('admin/categories/<int:pk>/', admin_views.AdminFinancialCategoryViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='admin-category-detail'),

    # Include router URLs
    path('', include(router.urls)),
]