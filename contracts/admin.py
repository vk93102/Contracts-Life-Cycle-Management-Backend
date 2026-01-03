from django.contrib import admin
from .models import Contract, ContractTemplate, Clause, BusinessRule

@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'contract_type', 'version', 'status')
    list_filter = ('contract_type', 'status')
    search_fields = ('name', 'contract_type')

@admin.register(Clause)
class ClauseAdmin(admin.ModelAdmin):
    list_display = ('clause_id', 'name', 'contract_type', 'version', 'status')
    list_filter = ('contract_type', 'status', 'is_mandatory')
    search_fields = ('clause_id', 'name')

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('title', 'contract_type', 'status')
    list_filter = ('status', 'contract_type')
    search_fields = ('title', 'contract_type')

@admin.register(BusinessRule)
class BusinessRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'rule_type', 'is_active')
    list_filter = ('rule_type', 'is_active')
    search_fields = ('name', 'description')
