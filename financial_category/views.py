from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Count, F, Q, ExpressionWrapper, FloatField
from django.db.models.functions import TruncMonth, TruncDay
from django.utils import timezone
from datetime import datetime, timedelta
from .models import FinancialCategory, Income, Expense, Debt, FutureSaving
from .serializers import (
    FinancialCategorySerializer,
    IncomeSerializer,
    ExpenseSerializer,
    DebtSerializer,
    FutureSavingSerializer
)
import csv
from io import StringIO

class FinancialCategoryViewSet(ModelViewSet):
    """
    ViewSet for financial categories
    Regular users can only read categories
    Admin users can perform all CRUD operations
    """
    queryset = FinancialCategory.objects.all()
    serializer_class = FinancialCategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        category_type = self.request.query_params.get('type')
        if category_type:
            queryset = queryset.filter(type=category_type)
        return queryset.order_by('name')

    def get_permissions(self):
        """
        Regular users can only read
        Admin users can perform all operations
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            if not self.request.user.is_admin:
                self.http_method_names = ['get', 'head', 'options']
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        if not request.user.is_admin:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.user.is_admin:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_admin:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

class BaseTransactionViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class IncomeViewSet(BaseTransactionViewSet):
    queryset = Income.objects.all()
    serializer_class = IncomeSerializer

class ExpenseViewSet(BaseTransactionViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        """Filter expenses by user and ensure categories are of type 'expense'"""
        return super().get_queryset().select_related('category').filter(
            user=self.request.user,
            category__type='expense'
        )

class DebtViewSet(BaseTransactionViewSet):
    queryset = Debt.objects.all()
    serializer_class = DebtSerializer

    def get_queryset(self):
        """Filter debts by user and ensure categories are of type 'debt'"""
        return super().get_queryset().filter(
            user=self.request.user
        ).select_related('category').filter(
            Q(category__isnull=True) | Q(category__type='debt')
        )

class FutureSavingViewSet(BaseTransactionViewSet):
    queryset = FutureSaving.objects.all()
    serializer_class = FutureSavingSerializer


class DebtVisualizationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        debts = Debt.objects.filter(
            user=user,
            paid_amount__lt=F('amount')
        ).values(
            'name',
            'amount',
            'paid_amount',
            'due_date'
        ).order_by('due_date')

        return Response(list(debts))

class GoalSavingVisualizationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            savings = FutureSaving.objects.filter(user=request.user)
            data = []
            for saving in savings:
                progress = (saving.current_amount / saving.target_amount * 100) if saving.target_amount else 0
                data.append({
                    'name': saving.name,
                    'current_amount': saving.current_amount,
                    'target_amount': saving.target_amount,
                    'progress': progress,
                    'target_date': saving.target_date
                })
            return Response(data)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class ExpenseVisualizationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        period = request.query_params.get('period', 'month')

        # Set date range
        end_date = timezone.now()
        if period == 'week':
            start_date = end_date - timedelta(days=7)
        elif period == 'month':
            start_date = end_date - timedelta(days=30)
        else:  # year
            start_date = end_date - timedelta(days=365)

        # Get top expenses
        top_expenses = Expense.objects.filter(
            user=user,
            date__range=[start_date, end_date]
        ).values('category__name').annotate(
            total=Sum('amount')
        ).order_by('-total')[:5]

        # Get expense trend
        expense_trend = Expense.objects.filter(
            user=user,
            date__range=[start_date, end_date]
        ).values('date').annotate(
            total=Sum('amount')
        ).order_by('date')

        return Response({
            'top_expenses': list(top_expenses),
            'expense_trend': list(expense_trend),
            'period': period
        })

class CategoryOverviewView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get all categories with their descriptions
            categories = FinancialCategory.objects.all().order_by('type', 'name')
            
            # Serialize the categories
            serializer = FinancialCategorySerializer(categories, many=True)
            
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class ImportDataView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        file = request.FILES.get('file')

        if not file:
            return Response({"error": "No file uploaded."}, status=400)

        if not file.name.endswith('.csv'):
            return Response({"error": "Please upload a CSV file."}, status=400)

        if file.size > 5 * 1024 * 1024:  # 5MB limit
            return Response({"error": "File size should not exceed 5MB."}, status=400)

        try:
            decoded_file = file.read().decode('utf-8')
            io_string = StringIO(decoded_file)
            csv_reader = csv.DictReader(io_string)
            
            required_fields = ['date', 'type', 'category', 'name', 'amount']
            first_row = next(csv_reader)
            io_string.seek(0)
            next(csv_reader)  # Skip header row again
            
            missing_fields = [field for field in required_fields if field not in first_row]
            if missing_fields:
                return Response(
                    {"error": f"Missing required fields: {', '.join(missing_fields)}"},
                    status=400
                )

            from django.db import transaction
            with transaction.atomic():
                imported_count = {
                    'income': 0,
                    'expense': 0,
                    'debt': 0,
                    'saving': 0
                }

                for row in csv_reader:
                    # Skip empty rows
                    if not any(row.values()):
                        continue

                    try:
                        record_type = row['type'].lower()
                        if record_type not in ['income', 'expense', 'debt', 'saving']:
                            continue

                        # Validate and parse date
                        try:
                            date = datetime.strptime(row['date'], '%Y-%m-%d').date()
                        except ValueError:
                            continue

                        # Validate and parse amount
                        try:
                            amount = float(row['amount'])
                            if amount < 0:
                                continue
                        except ValueError:
                            continue

                        # Get or create category
                        category = None
                        if row.get('category'):
                            category = FinancialCategory.objects.filter(
                                name=row['category'],
                                type=record_type
                            ).first()

                        # Common data for all models
                        data = {
                            'user': user,
                            'category': category,
                            'name': row.get('name', ''),
                            'description': row.get('description', ''),
                            'amount': amount,
                            'date': date
                        }

                        if record_type == 'income':
                            Income.objects.create(**data)
                            imported_count['income'] += 1
                        elif record_type == 'expense':
                            Expense.objects.create(**data)
                            imported_count['expense'] += 1
                        elif record_type == 'debt':
                            data['paid_amount'] = float(row.get('paid_amount', 0))
                            data['due_date'] = datetime.strptime(
                                row.get('due_date', row['date']),
                                '%Y-%m-%d'
                            ).date()
                            Debt.objects.create(**data)
                            imported_count['debt'] += 1
                        elif record_type == 'saving':
                            data['target_amount'] = amount
                            data['current_amount'] = float(row.get('current_amount', 0))
                            data['target_date'] = datetime.strptime(
                                row.get('target_date', row['date']),
                                '%Y-%m-%d'
                            ).date()
                            FutureSaving.objects.create(**data)
                            imported_count['saving'] += 1

                    except Exception as row_error:
                        print(f"Error processing row: {row}")
                        print(f"Error: {str(row_error)}")
                        continue

            return Response({
                "message": "Data imported successfully.",
                "imported_count": imported_count
            }, status=201)

        except Exception as e:
            return Response({"error": str(e)}, status=400)
