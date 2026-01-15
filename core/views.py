from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from django.utils import timezone
from django.shortcuts import render, redirect
from django.db import transaction
from django.db.models import Sum, Q, Count
from decimal import Decimal
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from datetime import timedelta

from core.models import Product, Contact, RentalContract, Transaction, CapitalAccount, CustomUser, Tenant, StockItem
# 🟢 引入 CapitalAccountSerializer
from core.serializers import ProductSerializer, ContactSerializer, RentalContractSerializer, TransactionSerializer, StaffSerializer, TenantSerializer, CapitalAccountSerializer

class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request): return

# --- 页面路由配置 ---
def index_page(request): return render(request, 'index.html') if request.user.is_authenticated else redirect('/login/')
def login_page(request): return redirect('/') if request.user.is_authenticated else render(request, 'login.html')
def register_page(request): return render(request, 'register.html')
def staff_page(request): return render(request, 'staff.html') if request.user.is_authenticated else redirect('/login/')
def company_page(request): return render(request, 'company.html') if request.user.is_authenticated else redirect('/login/')

def entry_page(request): return render(request, 'entry.html') if request.user.is_authenticated else redirect('/login/')
def sales_page(request): return render(request, 'sales.html') if request.user.is_authenticated else redirect('/login/')
def contact_page(request): return render(request, 'contact.html') if request.user.is_authenticated else redirect('/login/')
def inventory_page(request): return render(request, 'inventory.html') if request.user.is_authenticated else redirect('/login/')
def rental_hub_page(request): return render(request, 'rental_hub.html') if request.user.is_authenticated else redirect('/login/')
def rental_create_page(request): return render(request, 'rental_create.html') if request.user.is_authenticated else redirect('/login/')
def profit_page(request): return render(request, 'analysis_profit.html') if request.user.is_authenticated else redirect('/login/')
def finance_page(request): return render(request, 'analysis_finance.html') if request.user.is_authenticated else redirect('/login/')
def account_page(request): return render(request, 'analysis_account.html') if request.user.is_authenticated else redirect('/login/')
def profile_page(request): return render(request, 'profile.html') if request.user.is_authenticated else redirect('/login/')

# --- 核心基类 ---
class TenantAwareViewSet(viewsets.ModelViewSet):
    authentication_classes = (CsrfExemptSessionAuthentication, )
    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated: return self.queryset.none()
        if user.is_superuser: return self.queryset
        if not user.tenant: return self.queryset.none()
        return self.queryset.filter(tenant=user.tenant)
    def perform_create(self, serializer):
        if self.request.user.tenant: serializer.save(tenant=self.request.user.tenant)
        else: serializer.save()

# --- 老板管理接口 ---
class StaffViewSet(TenantAwareViewSet):
    queryset = CustomUser.objects.all().order_by('-date_joined')
    serializer_class = StaffSerializer
    def get_queryset(self): return super().get_queryset().exclude(id=self.request.user.id)
    def create(self, request, *args, **kwargs):
        user = request.user
        if user.role != 'ADMIN': return Response({'detail': '只有老板可操作'}, status=403)
        curr = CustomUser.objects.filter(tenant=user.tenant).count()
        if curr >= user.tenant.account_limit: return Response({'detail': f'员工数已达上限({user.tenant.account_limit})'}, status=400)
        data = request.data
        if CustomUser.objects.filter(username=data['username']).exists(): return Response({'detail': '账号已存在'}, status=400)
        try:
            pwd = data.get('password') if data.get('password') else '123456'
            CustomUser.objects.create_user(username=data['username'], password=pwd, first_name=data.get('first_name', '员工'), tenant=user.tenant, role='SALES', initials=data.get('first_name', '员工')[-2:])
            return Response({'status': 'ok'})
        except Exception as e: return Response({'detail': str(e)}, status=400)

class MyTenantViewSet(viewsets.ViewSet):
    authentication_classes = (CsrfExemptSessionAuthentication, )
    @action(detail=False, methods=['get'])
    def info(self, request): return Response(TenantSerializer(request.user.tenant).data if request.user.tenant else {})
    @action(detail=False, methods=['post'])
    def update_info(self, request):
        if request.user.role != 'ADMIN': return Response({'detail': '无权操作'}, status=403)
        t = request.user.tenant; t.name = request.data.get('name', t.name); t.owner_name = request.data.get('owner_name', t.owner_name); t.save()
        return Response({'status': 'ok'})

# --- 认证 API ---
@csrf_exempt
def api_login(request):
    if request.method == 'POST':
        try: data = json.loads(request.body)
        except: data = request.POST
        user = authenticate(username=data.get('username'), password=data.get('password'))
        if user:
            if user.tenant and not user.tenant.is_active: return JsonResponse({'status': 'error', 'msg': '账户待审核或已停用'})
            login(request, user)
            role_display = '老板' if user.role == 'ADMIN' else '员工'
            company = user.tenant.name if user.tenant else '未入驻'
            return JsonResponse({'status': 'ok', 'role': user.role, 'name': user.first_name or user.username, 'tenant': company, 'role_display': role_display})
        return JsonResponse({'status': 'error', 'msg': '账号或密码错误'})
    return JsonResponse({'status': 'error'})

def api_logout(request): logout(request); return JsonResponse({'status': 'ok'})
@csrf_exempt
def api_change_password(request):
    try: data = json.loads(request.body); request.user.set_password(data.get('password')); request.user.save(); return JsonResponse({'status': 'ok'})
    except: return JsonResponse({'status': 'error'})
@csrf_exempt
def api_register(request):
    if request.method == 'POST':
        try: 
            data = json.loads(request.body)
            if Tenant.objects.filter(phone=data.get('phone')).exists(): return JsonResponse({'status': 'error', 'msg': '手机号已注册'})
            with transaction.atomic():
                tenant = Tenant.objects.create(name=data.get('company_name'), owner_name=data.get('name'), phone=data.get('phone'), is_active=False)
                CustomUser.objects.create_user(username=data.get('phone'), password=data.get('password'), tenant=tenant, role='ADMIN', first_name=data.get('name'), initials=data.get('name')[-2:] if data.get('name') else 'BOSS')
                CapitalAccount.objects.create(tenant=tenant, name='现金账户', current_balance=0)
                Contact.objects.create(tenant=tenant, name='散客', phone='00000000000')
            return JsonResponse({'status': 'ok', 'msg': '注册成功，请等待审核'})
        except Exception as e: return JsonResponse({'status': 'error', 'msg': str(e)})
    return JsonResponse({'status': 'error'})

# --- 业务 API ---
class CapitalAccountViewSet(TenantAwareViewSet):
    queryset = CapitalAccount.objects.all()
    # 🟢 修复：引用正确的序列化器
    serializer_class = CapitalAccountSerializer 
    def list(self, request): 
        qs = self.get_queryset()
        return Response([{'id': a.id, 'name': a.name, 'balance': a.current_balance} for a in qs])

class ProductViewSet(TenantAwareViewSet):
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'zencode', 'note']

    def create(self, request, *args, **kwargs):
        user = request.user; tenant = user.tenant
        if not tenant and not user.is_superuser: return Response({'detail': '无租户权限'}, 400)
        data = request.data.copy()
        name = data.get('name'); category = data.get('category', 'ZX'); sn = data.get('sn'); cost_price = Decimal(str(data.get('cost_price', 0)))
        with transaction.atomic():
            product, created = Product.objects.get_or_create(
                name=name, category=category, tenant=tenant,
                defaults={'cpu': data.get('cpu', ''), 'gpu': data.get('gpu', ''), 'ram': data.get('ram', ''), 'disk': data.get('disk', ''), 'note': data.get('note', ''), 'cost_price': cost_price, 'retail_price': data.get('retail_price', 0), 'zencode': self._gen_code(user, category)}
            )
            if not created: product.cost_price = cost_price; product.save()
            final_sn = sn if sn else f"AUTO-{timezone.now().strftime('%Y%m%d%H%M%S')}"
            StockItem.objects.create(tenant=tenant, product=product, sn=final_sn, real_cost=cost_price, status='IN_STOCK', supplier_id=data.get('supplier_id') if data.get('supplier_id')!='0' else None, note=data.get('note', ''))
            self._handle_finance(request, product, cost_price)
            return Response(self.get_serializer(product).data, status=status.HTTP_201_CREATED)

    def _gen_code(self, user, cat):
        initials = getattr(user, 'initials', 'AD'); dt = timezone.now(); prefix = f"{str(dt.year)[-2:]}{dt.month}{dt.day:02d}{initials}{cat}"
        count = Product.objects.filter(category=cat, tenant=user.tenant).count() + 1; return f"{prefix}{count}"

    def _handle_finance(self, request, product, amount):
        supplier_id = request.data.get('supplier_id'); paid = Decimal(str(request.data.get('paid_amount', 0) or 0)); acc_id = request.data.get('account_id')
        if supplier_id and str(supplier_id) != '0':
            try:
                sup = Contact.objects.get(id=supplier_id)
                if acc_id:
                    acc = CapitalAccount.objects.get(id=acc_id)
                    Transaction.objects.create(tenant=request.user.tenant, contact=sup, product=product, account=acc, amount=paid, type='BUY', operator=request.user, remark=f"采购: {product.name}")
                    if paid > 0: acc.current_balance -= paid; acc.save()
                debt = amount - paid; 
                if debt != 0: sup.balance -= debt; sup.save()
            except: pass

    @action(detail=True, methods=['post'])
    def sell(self, request, pk=None):
        product = self.get_object(); user = request.user
        stock = StockItem.objects.filter(product=product, status='IN_STOCK', tenant=user.tenant).first()
        if not stock: return Response({'detail': '库存不足'}, 400)
        price = Decimal(str(request.data.get('price'))); received = Decimal(str(request.data.get('received_amount', 0) or 0))
        contact_id = request.data.get('contact_id'); acc_id = request.data.get('account_id')
        try:
            with transaction.atomic():
                stock.status='SOLD'; stock.save(); product.status='SOLD'; product.sold_price=price; product.save()
                contact = Contact.objects.get(id=contact_id); acc = CapitalAccount.objects.get(id=acc_id) if acc_id else None
                Transaction.objects.create(tenant=user.tenant, contact=contact, product=product, account=acc, amount=received, type='SALE', operator=user, remark=f"销售: {product.name} ({stock.sn})")
                if acc and received > 0: acc.current_balance += received; acc.save()
                contact.balance += (price - received); contact.save()
                return Response({'msg': 'OK'})
        except Exception as e: return Response({'detail': str(e)}, 500)

class ContactViewSet(TenantAwareViewSet):
    queryset = Contact.objects.all(); serializer_class = ContactSerializer; filter_backends = [filters.SearchFilter]; search_fields = ['name', 'phone']
    @action(detail=True, methods=['post'])
    def repay(self, request, pk=None): return Response({'msg':'ok'}) 
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None): return Response([])

class RentalViewSet(TenantAwareViewSet):
    queryset = RentalContract.objects.all().order_by('-id'); serializer_class = RentalContractSerializer

# ... (保留前面所有 Import 和 API 类，只替换最后的 AnalysisViewSet)

# 🟢 全能分析接口：同时修复了Web端NaN和小程序查流水
class AnalysisViewSet(viewsets.ViewSet):
    authentication_classes = (CsrfExemptSessionAuthentication, )
    
    def _get_qs(self, model):
        user = self.request.user
        if user.is_superuser: return model.objects.all()
        if user.tenant: return model.objects.filter(tenant=user.tenant)
        return model.objects.none()
    
    @action(detail=False)
    def dashboard(self, request):
        # ... (Dashboard 逻辑略，保持原样或参照上文)
        return Response({'stock_val':0, 'cards':{}}) # 占位，请用之前的完整代码

    @action(detail=False)
    def accounting(self, request):
        accounts = self._get_qs(CapitalAccount)
        # ... (计算净资产)
        return Response({'accounts': [{'id': a.id, 'name': a.name, 'balance': a.current_balance} for a in accounts]})
    
    # 🟢 核心修复：真实的利润计算逻辑 (解决 NaN)
    @action(detail=False)
    def profit_dashboard(self, request):
        if request.user.role == 'SALES': return Response({'detail': '无权访问'}, status=403)
        
        start = request.query_params.get('start_date')
        end = request.query_params.get('end_date')
        staff_id = request.query_params.get('staff_id')
        
        # 查销售流水
        txs = self._get_qs(Transaction).filter(type='SALE')
        if start: txs = txs.filter(created_at__date__gte=start)
        if end: txs = txs.filter(created_at__date__lte=end)
        if staff_id: txs = txs.filter(operator_id=staff_id)
        
        total_sales = 0
        total_cost = 0
        list_data = []
        
        # 关联查询优化
        for t in txs.select_related('product', 'operator', 'contact').order_by('-created_at'):
            sale_amt = t.amount
            cost_amt = t.product.cost_price if t.product else 0
            profit = sale_amt - cost_amt
            
            total_sales += sale_amt
            total_cost += cost_amt
            
            list_data.append({
                'date': t.created_at.strftime('%Y-%m-%d'),
                'product_name': t.product.name if t.product else '未知商品',
                'zencode': t.product.zencode if t.product else '-',
                'staff': t.operator.first_name if t.operator else '系统',
                'customer': t.contact.name if t.contact else '散客',
                'profit': profit
            })
            
        total_profit = total_sales - total_cost
        
        # 员工筛选列表
        staff_list = CustomUser.objects.filter(tenant=request.user.tenant, role='SALES').values('id', 'first_name', 'username')
        staff_opts = [{'id': u['id'], 'name': u['first_name'] or u['username']} for u in staff_list]

        return Response({
            'summary': {
                'sales': total_sales,
                'cost': total_cost,
                'profit': total_profit
            },
            'list': list_data,
            'options': {'staff': staff_opts}
        })

    # 🟢 查流水接口 (小程序用)
    @action(detail=False)
    def account_history(self, request):
        acc_id = request.query_params.get('id')
        if not acc_id: return Response([])
        txs = self._get_qs(Transaction).filter(account_id=acc_id).select_related('contact', 'product', 'operator').order_by('-created_at')
        data = []
        for t in txs:
            is_income = t.type in ['SALE', 'RENT', 'OTHER']
            if t.type == 'BUY': is_income = False
            target = '-'
            if t.contact: target = t.contact.name
            elif t.product: target = t.product.name
            data.append({
                'id': t.id, 'date': t.created_at.strftime('%Y-%m-%d %H:%M'),
                'type_name': t.get_type_display(), 'amount': t.amount,
                'sign': '+' if is_income else '-', 'is_income': is_income,
                'target': target, 'remark': t.remark or '-',
                'operator': t.operator.first_name if t.operator else '系统'
            })
        return Response(data)