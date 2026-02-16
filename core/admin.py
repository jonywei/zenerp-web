from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.contrib import messages
from .models import Tenant, CustomUser, CapitalAccount, Contact, Product, StockItem, RentalContract, Transaction, SerialNumberFactory

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner_name', 'phone', 'is_active')
    actions = ['init_admin_account']

    @admin.action(description='⚡️ 初始化账号 + 默认数据 (必点)')
    def init_admin_account(self, request, queryset):
        count = 0
        for tenant in queryset:
            if not tenant.phone: continue
            
            # 1. 确保账号存在
            user, _ = CustomUser.objects.get_or_create(username=tenant.phone, defaults={'tenant': tenant, 'role': 'ADMIN', 'first_name': tenant.owner_name})
            user.set_password('123456'); user.tenant = tenant; user.is_active = True; user.save()
            
            # 2. 🟢 核心修复：手动开户也要送钱(账户)送人(客户)，防止App报错
            if not CapitalAccount.objects.filter(tenant=tenant).exists():
                CapitalAccount.objects.create(tenant=tenant, name='现金账户', current_balance=0)
            
            if not Contact.objects.filter(tenant=tenant).exists():
                Contact.objects.create(tenant=tenant, name='散客', phone='00000000000')
                
            count += 1
        self.message_user(request, f"成功初始化 {count} 个租户！密码123456，且已自动创建默认资金账户。", level=messages.SUCCESS)

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'tenant', 'role', 'is_active')
    list_filter = ('tenant', 'role')
    fieldsets = UserAdmin.fieldsets + (('SaaS 归属', {'fields': ('tenant', 'role', 'initials')}),)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'category', 'cost_price')
    list_filter = ('tenant',)

@admin.register(CapitalAccount)
class CapitalAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'current_balance')
    list_filter = ('tenant',)

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'phone')
    list_filter = ('tenant',)

@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'sn', 'tenant')
    list_filter = ('tenant',)

# 其他注册保持不变...
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin): pass
@admin.register(RentalContract)
class RentalContractAdmin(admin.ModelAdmin): pass
@admin.register(SerialNumberFactory)
class SerialNumberFactoryAdmin(admin.ModelAdmin): pass