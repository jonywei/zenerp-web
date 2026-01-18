from rest_framework import serializers
from .models import Product, Contact, RentalContract, Transaction, CapitalAccount, Tenant, StockItem, CustomUser
from django.utils import timezone

# 🟢 资金账户序列化
class CapitalAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = CapitalAccount
        fields = '__all__'
        # 🟢 关键修复：防止前端没传 tenant 报错
        read_only_fields = ['id', 'tenant']

# 🟢 员工管理序列化
class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    date_joined = serializers.DateTimeField(read_only=True, format="%Y-%m-%d")
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'first_name', 'role', 'is_active', 'password', 'date_joined']
        read_only_fields = ['id', 'date_joined', 'role', 'tenant']

# 🟢 租户信息序列化
class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['id', 'name', 'owner_name', 'phone', 'expire_date']
        read_only_fields = ['id', 'expire_date', 'phone']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    class Meta: model = Tenant; fields = ['name', 'owner_name', 'phone', 'password']

class ProductSerializer(serializers.ModelSerializer):
    color_tag = serializers.SerializerMethodField()
    flow_history = serializers.SerializerMethodField()
    sn = serializers.CharField(write_only=True, required=False, allow_blank=True)
    class Meta: 
        model = Product
        fields = '__all__'
        # 🟢 关键修复：入库时不需要前端传 tenant
        read_only_fields = ['id', 'tenant', 'created_at']
    
    def get_color_tag(self, obj): return 'green' 

    def get_flow_history(self, obj):
        txs = Transaction.objects.filter(product=obj).order_by('-created_at')
        return [{'date': t.created_at.strftime('%Y-%m-%d'), 'type': t.get_type_display(), 'operator': t.operator.initials if t.operator else '系统', 'desc': t.remark or '-'} for t in txs]

class ContactSerializer(serializers.ModelSerializer):
    class Meta: 
        model = Contact
        fields = '__all__'
        # 🟢 核心修复：这里！把 tenant 设为只读，前端不传就不会报 400 错了
        read_only_fields = ['id', 'tenant', 'balance', 'created_at']

class RentalContractSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source='contact.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_zencode = serializers.CharField(source='product.zencode', read_only=True)
    operator_name = serializers.CharField(source='operator.username', read_only=True)
    class Meta: 
        model = RentalContract
        fields = '__all__'
        read_only_fields = ['id', 'tenant']

class TransactionSerializer(serializers.ModelSerializer):
    class Meta: 
        model = Transaction
        fields = '__all__'
        read_only_fields = ['id', 'tenant']