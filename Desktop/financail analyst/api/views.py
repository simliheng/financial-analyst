from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from datetime import datetime, timedelta
from users.models import CustomUser
from users.serializers import UserSerializer
from financial_category.models import Income, Expense, Debt, FutureSaving, FinancialCategory
from financial_category.serializers import (
    IncomeSerializer, 
    ExpenseSerializer, 
    DebtSerializer, 
    FutureSavingSerializer,
    FinancialCategorySerializer
)
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
import csv
from io import StringIO

User = get_user_model()

def get_monthly_data(user):
    today = timezone.now()
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Use timezone-aware queries consistently
    monthly_income = Income.objects.filter(
        user=user,
        date__gte=timezone.make_aware(start_of_month)
    ).aggregate(total=Sum('amount'))['total'] or 0

    monthly_expense = Expense.objects.filter(
        user=user,
        date__gte=timezone.make_aware(start_of_month)
    ).aggregate(total=Sum('amount'))['total'] or 0

    total_debt = Debt.objects.filter(
        user=user,
        is_paid=False
    ).aggregate(total=Sum('amount'))['total'] or 0

    savings = FutureSaving.objects.filter(
        user=user
    ).aggregate(
        target=Sum('target_amount'),
        current=Sum('current_amount')
    )
    
    return {
        'income': monthly_income,
        'expense': monthly_expense,
        'balance': monthly_income - monthly_expense,
        'debt': total_debt,
        'savings': {
            'target': savings['target'] or 0,
            'current': savings['current'] or 0,
            'progress': ((savings['current'] or 0) / (savings['target'] or 1)) * 100
        }
    }

def get_recent_transactions(user):
    return {
        'incomes': IncomeSerializer(
            Income.objects.filter(user=user).order_by('-date')[:5],
            many=True
        ).data,
        'expenses': ExpenseSerializer(
            Expense.objects.filter(user=user).order_by('-date')[:5],
            many=True
        ).data,
        'debts': DebtSerializer(
            Debt.objects.filter(user=user).order_by('-created_at')[:5],
            many=True
        ).data,
        'savings': FutureSavingSerializer(
            FutureSaving.objects.filter(user=user).order_by('-created_at')[:5],
            many=True
        ).data
    }

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_view(request):
    try:
        user = request.user
        period = request.GET.get('period', 'month')
        
        # Calculate date range based on period
        today = timezone.now()
        if period == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        elif period == 'year':
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)
        elif period == 'custom':
            try:
                start_date = request.GET.get('start_date')
                end_date = request.GET.get('end_date')
                if not start_date or not end_date:
                    return Response(
                        {'error': 'Both start_date and end_date are required for custom period'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d')
                end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d')
                # Make the dates timezone-aware
                start_date = timezone.make_aware(start_date)
                end_date = timezone.make_aware(end_date)
            except (ValueError, TypeError) as e:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD format for custom dates.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'Invalid period. Use week, month, year, or custom'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get income data with proper date formatting
        if period == 'year' or (period == 'custom' and (end_date - start_date).days > 365):
            # For year view or long custom ranges: Group by month and sum
            income_data = []
            current_date = start_date
            
            while current_date <= end_date:
                month_income = Income.objects.filter(
                    user=user,
                    date__year=current_date.year,
                    date__month=current_date.month
                ).aggregate(total=Sum('amount'))['total'] or 0
                
                income_data.append({
                    'date': current_date.strftime('%B %Y'),  # Format: "January 2025"
                    'amount': float(month_income)
                })
                
                # Move to next month
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)
        else:
            # For week/month/short custom view: Show daily data
            income_data = []
            current_date = start_date.date()
            
            while current_date <= end_date.date():
                daily_income = Income.objects.filter(
                    user=user,
                    date=current_date
                ).aggregate(total=Sum('amount'))['total'] or 0
                
                income_data.append({
                    'date': current_date.strftime('%d %B %Y'),  # Format: "17 January 2025"
                    'amount': float(daily_income)
                })
                current_date += timedelta(days=1)

        # Calculate totals for the period
        total_income = sum(item['amount'] for item in income_data)

        # Get expense data with proper filtering
        expenses = Expense.objects.filter(
            user=user,
            date__range=[start_date, end_date]
        ).select_related('category')  # Add select_related for better performance
        
        total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0.0

        # Get expense categories with proper filtering and sort by total amount
        expense_categories = []
        category_totals = expenses.values('category__name').annotate(
            amount=Sum('amount')
        ).order_by('-amount')
        
        for category in category_totals:
            if category['category__name']:  # Skip null categories
                expense_categories.append({
                    'category': category['category__name'],
                    'amount': float(category['amount'] or 0)
                })

        # Get top 5 expenses
        top_expenses = []
        for expense in expenses.order_by('-amount')[:5]:
            if expense.amount is not None:  # Skip expenses with null amounts
                top_expenses.append({
                    'name': str(expense.name) if expense.name else 'Unnamed Expense',
                    'amount': float(expense.amount),
                    'category': str(expense.category.name) if expense.category else 'Uncategorized',
                    'date': expense.date.strftime('%d %B %Y')  # Format date consistently
                })

        # Get related expenses for each top expense category
        related_expenses = []
        top_categories = set(expense['category'] for expense in top_expenses)
        
        # First, calculate totals for each category
        category_totals = {}
        for category in top_categories:
            category_total = expenses.filter(
                category__name=category
            ).aggregate(total=Sum('amount'))['total'] or 0
            category_totals[category] = float(category_total)

        # Sort categories by their total amount in descending order
        sorted_categories = sorted(top_categories, key=lambda x: category_totals[x], reverse=True)
        
        for category in sorted_categories:
            category_expenses = expenses.filter(
                category__name=category
            ).exclude(  # Exclude the expenses already in top_expenses
                id__in=[exp.id for exp in expenses.order_by('-amount')[:5]]
            ).order_by('-amount')[:3]  # Get next top 3 expenses
            
            expense_items = []
            for exp in category_expenses:
                expense_items.append({
                    'name': str(exp.name) if exp.name else 'Unnamed Expense',
                    'amount': float(exp.amount),
                    'date': exp.date.strftime('%d %B %Y')  # Format date consistently
                })
            
            if expense_items:  # Only add categories that have related expenses
                related_expenses.append({
                    'category': category,
                    'total': category_totals[category],
                    'items': expense_items
                })

        # Get debt progress with historical data
        debts = Debt.objects.filter(user=user)
        debt_progress = []
        for debt in debts:
            if debt.amount > 0:
                # Get historical payments in the selected period using category name matching
                period_payments = Expense.objects.filter(
                    user=user,
                    category__type='debt',
                    date__range=[start_date, end_date],
                    name__icontains=debt.name  # Match expenses by debt name
                ).aggregate(
                    period_paid=Sum('amount')
                )['period_paid'] or 0.0

                # Calculate overall progress
                total_paid = float(debt.paid_amount)
                total_amount = float(debt.amount)
                overall_percentage = (total_paid / total_amount * 100) if total_amount else 0

                # Calculate period progress
                period_percentage = (period_payments / total_amount * 100) if total_amount else 0

                debt_progress.append({
                    'name': debt.name,
                    'total_amount': total_amount,
                    'paid_amount': total_paid,
                    'paid_percentage': float(overall_percentage),
                    'period_stats': {
                        'paid_amount': float(period_payments),
                        'paid_percentage': float(period_percentage),
                        'remaining_amount': float(total_amount - total_paid),
                        'start_date': start_date.strftime('%d %B %Y'),
                        'end_date': end_date.strftime('%d %B %Y')
                    }
                })

        # Sort debts by remaining amount (highest first)
        debt_progress.sort(key=lambda x: x['total_amount'] - x['paid_amount'], reverse=True)

        # Get savings goals with historical data
        savings = FutureSaving.objects.filter(user=user)
        savings_goals = []
        for saving in savings:
            if saving.target_amount > 0:
                # Get savings contributions in the selected period using category name matching
                period_savings = Income.objects.filter(
                    user=user,
                    category__type='saving',
                    date__range=[start_date, end_date],
                    name__icontains=saving.name  # Match incomes by saving goal name
                ).aggregate(
                    period_saved=Sum('amount')
                )['period_saved'] or 0.0

                # Calculate overall progress
                current_amount = float(saving.current_amount)
                target_amount = float(saving.target_amount)
                overall_percentage = (current_amount / target_amount * 100) if target_amount else 0

                # Calculate period progress
                period_percentage = (period_savings / target_amount * 100) if target_amount else 0

                # Calculate estimated completion
                if period_savings > 0 and period in ['month', 'year']:
                    remaining_amount = target_amount - current_amount
                    if period == 'month':
                        months_to_complete = remaining_amount / (period_savings / 30)  # Daily average
                    else:  # year
                        months_to_complete = remaining_amount / (period_savings / 365)  # Daily average
                    
                    estimated_completion = today + timedelta(days=months_to_complete * 30)
                    completion_date = estimated_completion.strftime('%B %Y')
                else:
                    completion_date = None

                savings_goals.append({
                    'name': saving.name,
                    'current_amount': current_amount,
                    'target_amount': target_amount,
                    'progress_percentage': float(overall_percentage),
                    'period_stats': {
                        'saved_amount': float(period_savings),
                        'saved_percentage': float(period_percentage),
                        'remaining_amount': float(target_amount - current_amount),
                        'start_date': start_date.strftime('%d %B %Y'),
                        'end_date': end_date.strftime('%d %B %Y'),
                        'estimated_completion_date': completion_date
                    }
                })

        # Sort savings goals by progress percentage (lowest first to highlight needs)
        savings_goals.sort(key=lambda x: x['progress_percentage'])

        return Response({
            'total_income': float(total_income),
            'total_expenses': float(total_expenses),
            'total_debt': float(sum(d['total_amount'] for d in debt_progress)),
            'total_savings': float(sum(s['current_amount'] for s in savings_goals)),
            'income_data': income_data,
            'expense_categories': expense_categories,
            'top_expenses': top_expenses,
            'debt_progress': debt_progress,
            'savings_goals': savings_goals,
            'related_expenses': related_expenses
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
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

            with transaction.atomic():
                imported_count = {
                    'income': 0,
                    'expense': 0
                }

                date_formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']
                for row in csv_reader:
                    # Skip empty rows
                    if not any(row.values()):
                        continue

                    # Validate record type
                    record_type = row.get('type', '').lower().strip()
                    if record_type not in ['income', 'expense']:
                        print(f"Skipping invalid record type: {record_type}")
                        continue

                    # Get category
                    category_name = row.get('category', '').strip()
                    try:
                        category = FinancialCategory.objects.get(
                            name=category_name,
                            type=record_type
                        )
                    except FinancialCategory.DoesNotExist:
                        print(f"Category not found: {category_name} for type {record_type}")
                        continue

                    # Parse amount
                    try:
                        amount = float(str(row.get('amount', '0')).replace('#', '').strip())
                    except ValueError:
                        print(f"Invalid amount format: {row.get('amount')}")
                        continue

                    # Parse date
                    date_str = row.get('date', '').strip()
                    date = None
                    for date_format in date_formats:
                        try:
                            date = datetime.strptime(date_str, date_format).date()
                            break
                        except ValueError:
                            continue
                    
                    if not date:
                        print(f"Invalid date format: {date_str}")
                        continue

                    # Common data for both income and expense
                    record_data = {
                        'user': user,
                        'category': category,
                        'name': row.get('name', '').strip(),
                        'description': row.get('description', '').strip(),
                        'amount': amount,
                        'date': date
                    }

                    if record_type == 'income':
                        Income.objects.create(**record_data)
                        imported_count['income'] += 1
                    elif record_type == 'expense':
                        Expense.objects.create(**record_data)
                        imported_count['expense'] += 1

            return Response({
                "message": "Data imported successfully.",
                "imported_count": {
                    'income': imported_count['income'],
                    'expense': imported_count['expense']
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=400)
