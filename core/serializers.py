from rest_framework import serializers
from .models import Product, Contact, RentalContract, Transaction, CapitalAccount, Tenant, StockItem, CustomUser

class CapitalAccountSerializer(serializers.ModelSerializer):
    class Meta: model = CapitalAccount; fields = '__all__'; read_only_fields = ['id', 'tenant']

class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False); date_joined = serializers.DateTimeField(read_only=True, format="%Y-%m-%d")
    class Meta: model = CustomUser; fields = ['id', 'username', 'first_name', 'role', 'is_active', 'password', 'date_joined']; read_only_fields = ['id', 'date_joined', 'role', 'tenant']

class TenantSerializer(serializers.ModelSerializer):
    class Meta: model = Tenant; fields = ['id', 'name', 'owner_name', 'phone', 'expire_date']; read_only_fields = ['id', 'expire_date', 'phone']

class ProductSerializer(serializers.ModelSerializer):
    color_tag = serializers.SerializerMethodField(); flow_history = serializers.SerializerMethodField()
    # 🟢 新增：库存统计
    stock_counts = serializers.SerializerMethodField()
    class Meta: model = Product; fields = '__all__'; read_only_fields = ['id', 'tenant', 'created_at']
    def get_color_tag(self, obj): return 'green' if StockItem.objects.filter(product=obj, status='IN_STOCK').exists() else 'red'
    def get_flow_history(self, obj):
        txs = Transaction.objects.filter(product=obj).order_by('-created_at')
        return [{'date': t.created_at.strftime('%Y-%m-%d'), 'type': t.get_type_display(), 'operator': t.operator.initials if t.operator else '系统', 'desc': t.remark or '-'} for t in txs]
    def get_stock_counts(self, obj):
        items = StockItem.objects.filter(product=obj)
        return {'total': items.count(), 'in_stock': items.filter(status='IN_STOCK').count(), 'sold': items.filter(status='SOLD').count(), 'rented': items.filter(status='RENTED').count()}

class ContactSerializer(serializers.ModelSerializer):
    class Meta: model = Contact; fields = '__all__'; read_only_fields = ['id', 'tenant', 'balance', 'created_at']

class RentalContractSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source='contact.name', read_only=True); product_name = serializers.CharField(source='product.name', read_only=True)
    class Meta: model = RentalContract; fields = '__all__'; read_only_fields = ['id', 'tenant']

class TransactionSerializer(serializers.ModelSerializer):
    # ---- Readable / UI fields ----
    contact_name = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    capital_account_name = serializers.SerializerMethodField()
    type_display = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = '__all__'  # IMPORTANT: do not reference non-existent fields (e.g. updated_at)

    def get_contact_name(self, obj):
        c = getattr(obj, 'contact', None)
        return getattr(c, 'name', None) if c else None

    def get_product_name(self, obj):
        p = getattr(obj, 'product', None)
        return getattr(p, 'name', None) if p else None

    def get_capital_account_name(self, obj):
        a = getattr(obj, 'account', None)
        return getattr(a, 'name', None) if a else None

    def get_type_display(self, obj):
        mapping = {'SALE': '销售', 'BUY': '采购', 'RENT': '租赁', 'OTHER': '其他'}
        return mapping.get(getattr(obj, 'type', None), getattr(obj, 'type', ''))

    def get_status_display(self, obj):
        # is_voided is added by later migrations; keep compatible if DB already has it.
        if getattr(obj, 'is_voided', False):
            return '作废'
        return '有效'


class StockItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    class Meta: model = StockItem; fields = '__all__'
