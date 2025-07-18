from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Count, Sum
from django.utils import timezone
from datetime import timedelta
from django.db import connection
import psutil
from financial_category.models import FinancialCategory, Income, Expense, Debt, FutureSaving
from financial_category.serializers import FinancialCategorySerializer
from users.models import CustomUser
from users.serializers import UserSerializer

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users to access the view.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)

class AdminViewSet(viewsets.ViewSet):
    """
    Base ViewSet for admin views with proper permission handling
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]

    def get_permissions(self):
        """
        Instantiate and return the list of permissions that this view requires.
        """
        return [permission() for permission in self.permission_classes]

class AdminDashboardViewSet(viewsets.ViewSet):
    """
    ViewSet for admin dashboard functionality
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]

    @action(detail=False, methods=['get'], url_path='dashboard', url_name='dashboard')
    def dashboard_stats(self, request):
        """Get dashboard statistics"""
        try:
            # Calculate dates for new users in last 7 days
            end_date = timezone.now()
            start_date = end_date - timedelta(days=7)
            
            # User statistics
            total_users = CustomUser.objects.count()
            active_users = CustomUser.objects.filter(last_login__gte=start_date).count()
            new_users = CustomUser.objects.filter(date_joined__gte=start_date).count()
            
            # Get all categories with their details
            categories = FinancialCategory.objects.all()
            category_data = []
            
            for category in categories:
                category_data.append({
                    'type': category.get_type_display(),
                    'name': category.name,
                    'description': category.description
                })
            
            return Response({
                'user_stats': {
                    'total_users': total_users,
                    'active_users': active_users,
                    'new_users': new_users
                },
                'categories': category_data
            })
        except Exception as e:
            return Response(
                {'error': f'Error fetching dashboard stats: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class AdminFinancialCategoryViewSet(AdminViewSet, viewsets.ModelViewSet):
    """
    ViewSet for admin users to manage financial categories.
    Provides CRUD operations for financial categories.
    """
    queryset = FinancialCategory.objects.all()
    serializer_class = FinancialCategorySerializer

    def get_queryset(self):
        """
        Optionally filter categories by type.
        """
        queryset = FinancialCategory.objects.all()
        category_type = self.request.query_params.get('type', None)
        if category_type:
            queryset = queryset.filter(type=category_type)
        return queryset.order_by('name')

    def create(self, request, *args, **kwargs):
        """
        Create a new financial category.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        Update an existing financial category.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """
        Delete a financial category.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get comprehensive statistics for admin dashboard
        """
        # Get time range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)  # Last 30 days by default
        
        # User statistics
        total_users = CustomUser.objects.count()
        active_users = CustomUser.objects.filter(last_login__gte=start_date).count()
        
        # Transaction statistics
        total_income = Income.objects.aggregate(total=Sum('amount'))['total'] or 0
        total_expense = Expense.objects.aggregate(total=Sum('amount'))['total'] or 0
        total_debt = Debt.objects.aggregate(total=Sum('amount'))['total'] or 0
        total_savings = FutureSaving.objects.aggregate(
            target=Sum('target_amount'),
            current=Sum('current_amount')
        )
        
        # Category statistics
        categories_by_type = (
            FinancialCategory.objects.values('type')
            .annotate(count=Count('id'))
            .order_by('type')
        )
        
        # Recent activity
        recent_transactions = {
            'incomes': Income.objects.filter(date__gte=start_date).count(),
            'expenses': Expense.objects.filter(date__gte=start_date).count(),
            'debts': Debt.objects.filter(created_at__gte=start_date).count(),
            'savings': FutureSaving.objects.filter(created_at__gte=start_date).count()
        }

        return Response({
            'user_stats': {
                'total_users': total_users,
                'active_users': active_users,
                'activity_rate': (active_users / total_users * 100) if total_users > 0 else 0
            },
            'financial_stats': {
                'total_income': total_income,
                'total_expense': total_expense,
                'total_debt': total_debt,
                'savings': {
                    'target': total_savings['target'] or 0,
                    'current': total_savings['current'] or 0,
                    'progress': ((total_savings['current'] or 0) / (total_savings['target'] or 1)) * 100
                }
            },
            'categories': list(categories_by_type),
            'recent_activity': recent_transactions,
            'system_health': {
                'status': 'healthy',
                'last_check': timezone.now().isoformat()
            }
        })
