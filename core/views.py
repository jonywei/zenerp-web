from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from django.utils import timezone
from django.shortcuts import render, redirect
from django.db import transaction
from django.db.models import Sum, Q, F
from decimal import Decimal
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from datetime import timedelta

# 引入模型
from core.models import Product, Contact, RentalContract, Transaction, CapitalAccount, CustomUser, Tenant, StockItem
# 🟢 引入 StockItemSerializer (请确保在 serializers.py 里加了它)
from core.serializers import ProductSerializer, ContactSerializer, RentalContractSerializer, TransactionSerializer, StaffSerializer, TenantSerializer, CapitalAccountSerializer, StockItemSerializer

class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request): return

# ==========================================
# 📄 1. 页面路由
# ==========================================
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

# ==========================================
# 🧱 2. 核心基类
# ==========================================
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

# ==========================================
# 👤 3. 用户与租户管理
# ==========================================
class StaffViewSet(TenantAwareViewSet):
    queryset = CustomUser.objects.all().order_by('-date_joined')
    serializer_class = StaffSerializer
    def get_queryset(self): return super().get_queryset().exclude(id=self.request.user.id)
    def create(self, request, *args, **kwargs):
        user = request.user
        if user.role != 'ADMIN': return Response({'detail': '无权操作'}, status=403)
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

# ==========================================
# 🔐 4. 认证接口
# ==========================================
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

# ==========================================
# 📦 5. 核心业务 ViewSet
# ==========================================

class CapitalAccountViewSet(TenantAwareViewSet):
    queryset = CapitalAccount.objects.all()
    serializer_class = CapitalAccountSerializer 
    def list(self, request): 
        qs = self.get_queryset()
        return Response([{'id': a.id, 'name': a.name, 'balance': a.current_balance} for a in qs])

# 🟢 新增：库存明细管理 (用于待入库转正)
class StockItemViewSet(TenantAwareViewSet):
    queryset = StockItem.objects.all().order_by('-id')
    serializer_class = StockItemSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['sn', 'product__name']

    def get_queryset(self):
        qs = super().get_queryset()
        # 支持按状态筛选 (例如只查 PENDING 待入库的)
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    # 🟢 扫码转正接口 (单个或批量)
    @action(detail=False, methods=['post'])
    def confirm(self, request):
        # 接收 id 和 real_sn
        item_id = request.data.get('id')
        real_sn = request.data.get('real_sn')
        
        try:
            item = StockItem.objects.get(id=item_id, tenant=request.user.tenant)
            
            # 1. 更新为真实SN
            item.sn = real_sn
            # 2. 状态改为在库
            item.status = 'IN_STOCK'
            item.save()
            
            # 3. 这里可以补充财务逻辑
            # 如果是"确认收货"才付款，可以在这里补 Transaction
            # 但为了简单，建议入库时已记录(应付)，这里只是核销库存状态
            
            return Response({'status': 'ok', 'msg': '入库成功'})
        except Exception as e:
            return Response({'detail': str(e)}, 400)


class ProductViewSet(TenantAwareViewSet):
    queryset = Product.objects.all().order_by('-id') 
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'zencode', 'note']

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param and status_param != 'ALL':
            qs = qs.filter(status=status_param)
        return qs

    # 🟢 终极批量入库 (分场景处理)
    def create(self, request, *args, **kwargs):
        user = request.user; tenant = user.tenant
        if not tenant and not user.is_superuser: return Response({'detail': '无租户权限'}, 400)
        data = request.data.copy()
        
        # 1. 获取参数
        name = data.get('name')
        category = data.get('category', 'ZX')
        base_sn = data.get('sn') 
        # 获取数量 (默认为1)
        try: quantity = int(data.get('quantity', 1))
        except: quantity = 1
        
        cost_unit = Decimal(str(data.get('cost_price', 0))) # 单价
        paid_total = Decimal(str(data.get('paid_amount', 0) or 0)) # 总实付
        
        supplier_id = data.get('supplier_id')
        acc_id = data.get('account_id')
        
        # 🟢 核心属性：是否必录SN (由前端传入，或默认False)
        need_sn = data.get('need_sn', False) 
        if str(need_sn).lower() == 'true': need_sn = True
        else: need_sn = False

        with transaction.atomic():
            # A. 建立商品档案
            product, created = Product.objects.get_or_create(
                name=name, category=category, tenant=tenant,
                defaults={
                    'cpu': data.get('cpu', ''), 'gpu': data.get('gpu', ''), 
                    'ram': data.get('ram', ''), 'disk': data.get('disk', ''), 
                    'note': data.get('note', ''), 
                    'cost_price': cost_unit, 'retail_price': data.get('retail_price', 0), 
                    'zencode': self._gen_code(user, category),
                    'need_sn': need_sn # 记录该商品属性
                }
            )
            if not created: 
                product.cost_price = cost_unit
                product.need_sn = need_sn
            product.status = 'IN_STOCK'
            product.save()

            # B. 批量创建库存 (分场景)
            
            # 场景1：iPhone (需要SN) -> 状态 PENDING, SN=WAIT-xxx
            if need_sn:
                status_code = 'PENDING'
                sn_prefix = 'WAIT'
            # 场景2：废品 (不需要SN) -> 状态 IN_STOCK, SN=AUTO-xxx
            else:
                status_code = 'IN_STOCK'
                sn_prefix = 'AUTO' if not base_sn else base_sn

            for i in range(quantity):
                if need_sn:
                    # 待录入，生成占位符
                    final_sn = f"{sn_prefix}-{timezone.now().strftime('%H%M%S%f')}-{i+1}"
                else:
                    # 直接入库，自动生成流水号
                    if base_sn:
                        final_sn = base_sn if quantity == 1 else f"{base_sn}-{i+1}"
                    else:
                        final_sn = f"AUTO-{timezone.now().strftime('%Y%m%d%H%M%S%f')}-{i+1}"
                
                StockItem.objects.create(
                    tenant=tenant, product=product, sn=final_sn, 
                    real_cost=cost_unit, status=status_code, 
                    supplier_id=supplier_id if str(supplier_id)!='0' else None, 
                    note=data.get('note', '')
                )

            # C. 财务流水
            # 只有当选择了供应商时，才记录
            if supplier_id and str(supplier_id) != '0':
                # 🟢 逻辑优化：如果是 PENDING 状态，是否记账？
                # 魏总指示：要输入50个序列号进去。
                # 通常：Pending状态不应触发财务扣款，因为货没点清。
                # 但如果用户在入库时填了“实付金额”，说明已经打款了，必须记账！
                # 所以：只要有 paid_total，就必须记 Transaction。
                
                try:
                    sup = Contact.objects.get(id=supplier_id)
                    
                    # 1. 记录实付流水 (不管货在哪，钱付了就要记)
                    if acc_id and paid_total > 0:
                        acc = CapitalAccount.objects.get(id=acc_id)
                        remark_str = f"采购: {product.name} x {quantity} (含待入库)"
                        Transaction.objects.create(
                            tenant=tenant, contact=sup, product=product, account=acc, 
                            amount=paid_total, type='BUY', operator=user, remark=remark_str
                        )
                        acc.current_balance -= paid_total; acc.save()
                    
                    # 2. 自动抵扣欠款
                    # 只有 IN_STOCK 的商品才算应付？
                    # 不，只要单子开了，就算应付。
                    total_cost = cost_unit * quantity
                    debt = total_cost - paid_total
                    if debt != 0:
                        sup.balance -= debt; sup.save()
                except: pass

            return Response(self.get_serializer(product).data, status=status.HTTP_201_CREATED)

    def _gen_code(self, user, cat):
        initials = getattr(user, 'initials', 'AD'); dt = timezone.now(); prefix = f"{str(dt.year)[-2:]}{dt.month}{dt.day:02d}{initials}{cat}"
        count = Product.objects.filter(category=cat, tenant=user.tenant).count() + 1; return f"{prefix}{count}"

    # 🟢 批量销售逻辑 (自动扣减先进先出)
    @action(detail=True, methods=['post'])
    def sell(self, request, pk=None):
        product = self.get_object(); user = request.user
        
        try: quantity = int(request.data.get('quantity', 1))
        except: quantity = 1
        
        # 自动找出最早入库的 N 个 (且必须是 IN_STOCK)
        stocks = StockItem.objects.filter(product=product, status='IN_STOCK', tenant=user.tenant).order_by('id')[:quantity]
        
        if stocks.count() < quantity:
            return Response({'detail': f'库存不足！当前仅剩 {stocks.count()} 台，无法卖出 {quantity} 台'}, 400)
        
        unit_price = Decimal(str(request.data.get('price')))
        received_total = Decimal(str(request.data.get('received_amount', 0) or 0))
        contact_id = request.data.get('contact_id'); acc_id = request.data.get('account_id')
        
        try:
            with transaction.atomic():
                # A. 批量扣减
                for s in stocks:
                    s.status = 'SOLD'
                    s.save()
                
                # B. 记账
                contact = Contact.objects.get(id=contact_id)
                acc = CapitalAccount.objects.get(id=acc_id) if acc_id else None
                remark_str = f"销售: {product.name} x {quantity}"
                
                Transaction.objects.create(
                    tenant=user.tenant, contact=contact, product=product, account=acc, 
                    amount=received_total, type='SALE', operator=user, remark=remark_str
                )
                
                if acc and received_total > 0: 
                    acc.current_balance += received_total; acc.save()
                
                # C. 抵扣
                total_sell_price = unit_price * quantity
                debt = total_sell_price - received_total
                contact.balance += debt
                contact.save()
                
                return Response({'msg': 'OK'})
        except Exception as e: return Response({'detail': str(e)}, 500)

class ContactViewSet(TenantAwareViewSet):
    queryset = Contact.objects.all().order_by('-id') 
    serializer_class = ContactSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'phone']
    
    # 防重名
    def create(self, request, *args, **kwargs):
        user = request.user
        if not user.tenant: return Response({'detail': '无租户信息'}, 400)
        name = request.data.get('name')
        existing = Contact.objects.filter(tenant=user.tenant, name=name).first()
        if existing: return Response(self.get_serializer(existing).data)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def repay(self, request, pk=None): return Response({'msg':'ok'}) 
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None): return Response([])

class RentalViewSet(TenantAwareViewSet):
    queryset = RentalContract.objects.all().order_by('-id'); serializer_class = RentalContractSerializer

# ==========================================
# 🟢 全能分析接口
# ==========================================
class AnalysisViewSet(viewsets.ViewSet):
    authentication_classes = (CsrfExemptSessionAuthentication, )
    
    def _get_qs(self, model):
        user = self.request.user
        if user.is_superuser: return model.objects.all()
        if user.tenant: return model.objects.filter(tenant=user.tenant)
        return model.objects.none()
    
    @action(detail=False)
    def dashboard(self, request):
        today = timezone.localtime(timezone.now()).date()
        products = self._get_qs(Product)
        txs = self._get_qs(Transaction)
        contacts = self._get_qs(Contact)
        accounts = self._get_qs(CapitalAccount)
        items = self._get_qs(StockItem) 

        # 🟢 修复：库存货值只算 IN_STOCK (不含 PENDING)
        stock_val = items.filter(status='IN_STOCK').aggregate(Sum('real_cost'))['real_cost__sum'] or 0
        
        today_entry = items.filter(in_time__date=today).count()
        today_sale_count = txs.filter(type='SALE', created_at__date=today).count()

        def calc_sales(qs):
            total = 0
            for t in qs:
                total += t.amount
            return total

        today_txs = txs.filter(Q(type='SALE')|Q(type='RENT'), created_at__date=today).select_related('product')
        today_sale_amount = calc_sales(today_txs)
        
        receivable = contacts.filter(balance__gt=0).aggregate(Sum('balance'))['balance__sum'] or 0
        payable = contacts.filter(balance__lt=0).aggregate(Sum('balance'))['balance__sum'] or 0
        total_cash = accounts.aggregate(Sum('current_balance'))['current_balance__sum'] or 0

        days = []; sales_data = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            day_qs = txs.filter(Q(type='SALE')|Q(type='RENT'), created_at__date=day).select_related('product')
            days.append(day.strftime('%m-%d')); sales_data.append(float(calc_sales(day_qs)))

        recent_txs = txs.select_related('product').order_by('-created_at')[:10]
        recent_list = []
        for t in recent_txs:
            recent_list.append({
                'id': t.id, 
                'desc': f"{t.get_type_display()} - {t.product.name if t.product else (t.remark or '-')}", 
                'amount': t.amount, 
                'is_income': t.type in ['SALE', 'RENT', 'OTHER'], 
                'time': t.created_at.strftime('%m-%d %H:%M')
            })
            
        return Response({
            'cards': {'stock_val': stock_val, 'total_sales_amount': today_sale_amount, 'receivable': receivable, 'payable': abs(payable), 'cash': total_cash}, 
            'today_entry': today_entry, 'today_sale': today_sale_count,
            'charts': {'trend': {'labels': days, 'data': sales_data}, 'category': {'labels': ['默认'], 'data': [1]}}, 
            'recent_list': recent_list
        })

    @action(detail=False)
    def accounting(self, request):
        accounts = self._get_qs(CapitalAccount); items = self._get_qs(StockItem); contacts = self._get_qs(Contact)
        total_cash = sum([a.current_balance for a in accounts]) or 0
        stock_value = items.filter(status='IN_STOCK').aggregate(Sum('real_cost'))['real_cost__sum'] or 0
        receivable = contacts.filter(balance__gt=0).aggregate(Sum('balance'))['balance__sum'] or 0
        payable = contacts.filter(balance__lt=0).aggregate(Sum('balance'))['balance__sum'] or 0
        net_worth = total_cash + stock_value + receivable + payable 
        return Response({'cash': total_cash, 'stock': stock_value, 'receivable': receivable, 'payable': abs(payable), 'net_worth': net_worth, 'accounts': [{'id': a.id, 'name': a.name, 'balance': a.current_balance} for a in accounts]})
    
    @action(detail=False)
    def profit_dashboard(self, request):
        if request.user.role == 'SALES': return Response({'detail': '无权访问'}, status=403)
        start = request.query_params.get('start_date'); end = request.query_params.get('end_date'); staff_id = request.query_params.get('staff_id')
        txs = self._get_qs(Transaction).filter(type='SALE')
        if start: txs = txs.filter(created_at__date__gte=start)
        if end: txs = txs.filter(created_at__date__lte=end)
        if staff_id: txs = txs.filter(operator_id=staff_id)
        
        total_sales = 0; total_cost = 0; list_data = []
        for t in txs.select_related('product', 'operator', 'contact').order_by('-created_at'):
            sale_amt = t.amount
            cost_amt = t.product.cost_price if t.product else 0
            profit = sale_amt - cost_amt
            total_sales += sale_amt; total_cost += cost_amt
            list_data.append({
                'date': t.created_at.strftime('%Y-%m-%d'),
                'product_name': t.product.name if t.product else '未知商品',
                'zencode': t.product.zencode if t.product else '-',
                'staff': t.operator.first_name if t.operator else '系统',
                'customer': t.contact.name if t.contact else '散客',
                'profit': profit,
                'sales': sale_amt 
            })
        
        staff_list = CustomUser.objects.filter(tenant=request.user.tenant, role='SALES').values('id', 'first_name', 'username')
        staff_opts = [{'id': u['id'], 'name': u['first_name'] or u['username']} for u in staff_list]
        return Response({'summary': {'sales': total_sales, 'cost': total_cost, 'profit': total_sales - total_cost}, 'list': list_data, 'options': {'staff': staff_opts}})

    @action(detail=False)
    def account_history(self, request):
        acc_id = request.query_params.get('id'); 
        if not acc_id: return Response([])
        txs = self._get_qs(Transaction).filter(account_id=acc_id).select_related('contact', 'product', 'operator').order_by('-created_at')
        data = []
        for t in txs:
            is_income = t.type in ['SALE', 'RENT', 'OTHER']; 
            if t.type == 'BUY': is_income = False
            target = '-'
            if t.contact: target = t.contact.name
            elif t.product: target = t.product.name
            data.append({'id': t.id, 'date': t.created_at.strftime('%Y-%m-%d %H:%M'), 'type_name': t.get_type_display(), 'amount': t.amount, 'sign': '+' if is_income else '-', 'is_income': is_income, 'target': target, 'remark': t.remark or '-', 'operator': t.operator.first_name if t.operator else '系统'})
        return Response(data)