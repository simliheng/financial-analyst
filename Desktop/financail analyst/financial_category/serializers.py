# backend/financial_category/serializers.py

from rest_framework import serializers
from .models import FinancialCategory, Income, Expense, Debt, FutureSaving

class FinancialCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialCategory
        fields = ['id', 'type', 'name', 'description']  

class IncomeSerializer(serializers.ModelSerializer):
    category = FinancialCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=FinancialCategory.objects.all(),
        source='category',
        required=False,
        allow_null=True,
        write_only=True
    )

    class Meta:
        model = Income
        fields = ['id', 'user', 'category', 'category_id', 'name', 'description', 'amount', 'date', 'created_at', 'updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        """Handle the update of an existing Income entry."""
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ExpenseSerializer(serializers.ModelSerializer):
    category = FinancialCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=FinancialCategory.objects.filter(type='expense'),
        source='category',
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Expense
        fields = ['id', 'user', 'category', 'category_id', 'name', 'description', 'amount', 'date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        """Handle the update of an existing Expense entry."""
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
    
class DebtSerializer(serializers.ModelSerializer):
    category = FinancialCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=FinancialCategory.objects.filter(type='debt'),
        source='category',
        write_only=True,
        required=False,
        allow_null=True
    )

    def validate_category_id(self, value):
        if value and value.type != 'debt':
            raise serializers.ValidationError("Category must be of type 'debt'")
        return value

    class Meta:
        model = Debt
        fields = ['id', 'user', 'category', 'category_id', 'name', 'description', 'amount', 'paid_amount', 'due_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def validate(self, data):
        """
        Check that paid_amount is not greater than amount
        """
        if 'paid_amount' in data and data['paid_amount'] > data.get('amount', 0):
            raise serializers.ValidationError("Paid amount cannot be greater than total amount")
        return data

    def update(self, instance, validated_data):
        """Handle the update of an existing Debt entry."""
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
    
class FutureSavingSerializer(serializers.ModelSerializer):
    category = FinancialCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=FinancialCategory.objects.filter(type='saving'),
        source='category',
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = FutureSaving
        fields = ['id', 'user', 'category', 'category_id', 'name', 'description', 'target_amount', 'current_amount', 'target_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        """Handle the update of an existing Future Saving entry."""
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
