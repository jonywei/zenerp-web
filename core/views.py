from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Sum, Q, F, Count
from decimal import Decimal
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import traceback
from datetime import timedelta, datetime
from rest_framework.pagination import PageNumberPagination

from core.models import Product, Contact, RentalContract, Transaction, CapitalAccount, CustomUser, Tenant, StockItem
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
def contact_detail_page(request, id):
    if not request.user.is_authenticated: return redirect('/login/')
    return render(request, 'contact_detail.html', {'contact_id': id})

def inventory_page(request): return render(request, 'inventory.html') if request.user.is_authenticated else redirect('/login/')
def rental_hub_page(request): return render(request, 'rental_hub.html') if request.user.is_authenticated else redirect('/login/')
def rental_create_page(request): return render(request, 'rental_create.html') if request.user.is_authenticated else redirect('/login/')

def profit_page(request): return render(request, 'analysis_profit.html') if request.user.is_authenticated else redirect('/login/')
def finance_page(request): return render(request, 'analysis_finance.html') if request.user.is_authenticated else redirect('/login/')
def account_page(request): return render(request, 'analysis_account.html') if request.user.is_authenticated else redirect('/login/')
def profile_page(request): return render(request, 'profile.html') if request.user.is_authenticated else redirect('/login/')

# ==========================================
# 🧱 2. API 基类
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
# 👤 3. 用户与租户
# ==========================================
class StaffViewSet(TenantAwareViewSet):
    queryset = CustomUser.objects.all().order_by('-date_joined')
    serializer_class = StaffSerializer
    def get_queryset(self): return super().get_queryset().exclude(id=self.request.user.id)
    def create(self, request, *args, **kwargs):
        user = request.user
        if user.role != 'ADMIN': return Response({'detail': '无权操作'}, status=403)
        if CustomUser.objects.filter(tenant=user.tenant).count() >= user.tenant.account_limit: return Response({'detail': '员工额度已满'}, status=400)
        data = request.data
        if CustomUser.objects.filter(username=data['username']).exists(): return Response({'detail': '账号已存在'}, status=400)
        try:
            pwd = data.get('password') if data.get('password') else '123456'
            CustomUser.objects.create_user(username=data['username'], password=pwd, first_name=data.get('first_name', '员工'), tenant=user.tenant, role='SALES', initials=data.get('first_name', '员工')[-2:])
            return Response({'status': 'ok'})
        except Exception as e: return Response({'detail': str(e)}, 400)

class MyTenantViewSet(viewsets.ViewSet):
    authentication_classes = (CsrfExemptSessionAuthentication, )
    @action(detail=False, methods=['get'])
    def info(self, request): return Response(TenantSerializer(request.user.tenant).data if request.user.tenant else {})
    @action(detail=False, methods=['post'])
    def update_info(self, request):
        if request.user.role != 'ADMIN': return Response({'detail': '无权操作'}, status=403)
        t = request.user.tenant; t.name = request.data.get('name', t.name); t.owner_name = request.data.get('owner_name', t.owner_name); t.save()
        return Response({'status': 'ok'})

@csrf_exempt
def api_login(request):
    if request.method == 'POST':
        try: data = json.loads(request.body)
        except: data = request.POST
        user = authenticate(username=data.get('username'), password=data.get('password'))
        if user:
            if user.tenant and not user.tenant.is_active: return JsonResponse({'status': 'error', 'msg': '账户待审核'})
            login(request, user)
            return JsonResponse({'status': 'ok', 'role': user.role, 'name': user.first_name or user.username, 'tenant': user.tenant.name if user.tenant else '未入驻'})
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
        try: data = json.loads(request.body)
        except: return JsonResponse({'status': 'error', 'msg': 'Invalid data'})
        if Tenant.objects.filter(phone=data.get('phone')).exists(): return JsonResponse({'status': 'error', 'msg': '手机号已注册'})
        try:
            with transaction.atomic():
                tenant = Tenant.objects.create(name=data.get('company_name'), owner_name=data.get('name'), phone=data.get('phone'), is_active=False)
                CustomUser.objects.create_user(username=data.get('phone'), password=data.get('password'), tenant=tenant, role='ADMIN', first_name=data.get('name'), initials=data.get('name')[-2:] if data.get('name') else 'BOSS')
                CapitalAccount.objects.create(tenant=tenant, name='现金账户', current_balance=0)
                Contact.objects.create(tenant=tenant, name='散客', phone='00000000000')
            return JsonResponse({'status': 'ok', 'msg': '注册成功'})
        except Exception as e: return JsonResponse({'status': 'error', 'msg': str(e)})
    return JsonResponse({'status': 'error'})

# ==========================================
# 📦 4. 业务逻辑 API
# ==========================================

class CapitalAccountViewSet(TenantAwareViewSet):
    queryset = CapitalAccount.objects.all(); serializer_class = CapitalAccountSerializer
    def list(self, request): return Response([{'id': a.id, 'name': a.name, 'balance': a.current_balance} for a in self.get_queryset()])

class StockItemViewSet(TenantAwareViewSet):
    queryset = StockItem.objects.all().order_by('-id'); serializer_class = StockItemSerializer
    filter_backends = [filters.SearchFilter]; search_fields = ['sn', 'product__name']
    def get_queryset(self):
        qs = super().get_queryset(); status = self.request.query_params.get('status')
        if status: qs = qs.filter(status=status)
        return qs
    @action(detail=False, methods=['post'])
    def confirm(self, request):
        try:
            item = StockItem.objects.get(id=request.data.get('id'), tenant=request.user.tenant)
            item.sn = request.data.get('real_sn'); item.status = 'IN_STOCK'; item.save()
            return Response({'status': 'ok'})
        except Exception as e: return Response({'detail': str(e)}, 400)

class ProductViewSet(TenantAwareViewSet):
    queryset = Product.objects.all().order_by('-id'); serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter]; search_fields = ['name', 'zencode', 'note']

    def get_queryset(self):
        qs = super().get_queryset(); status = self.request.query_params.get('status')
        if status and status != 'ALL': qs = qs.filter(status=status)
        return qs

    def create(self, request, *args, **kwargs):
        user = request.user; tenant = user.tenant
        if not tenant: return Response({'detail': '无权限'}, 400)
        data = request.data.copy()
        supplier_id = data.get('supplier_id')
        if not supplier_id or str(supplier_id) in ['0', '', 'null', 'None']: supplier_id = None
        try: quantity = int(data.get('quantity', 1))
        except: quantity = 1
        raw_need_sn = data.get('need_sn', False)
        need_sn = str(raw_need_sn).lower() in ['true', '1', 'yes', 'on']
        def to_dec(v): return Decimal(str(v)) if v and str(v)!='' else Decimal(0)
        cost = to_dec(data.get('cost_price')); paid = to_dec(data.get('paid_amount'))
        name = data.get('name'); cat = data.get('category', 'ZX'); base_sn = data.get('sn')

        try:
            with transaction.atomic():
                product, created = Product.objects.get_or_create(
                    name=name, category=cat, tenant=tenant,
                    defaults={'cpu': data.get('cpu',''), 'gpu': data.get('gpu',''), 'ram': data.get('ram',''), 'disk': data.get('disk',''), 'note': data.get('note',''), 'cost_price': cost, 'retail_price': to_dec(data.get('retail_price')), 'zencode': self._gen_code(user, cat), 'need_sn': need_sn}
                )
                if not created: product.cost_price = cost; product.need_sn = need_sn
                product.status = 'IN_STOCK'; product.save()

                status_code = 'PENDING' if need_sn else 'IN_STOCK'
                sn_prefix = 'WAIT' if need_sn else ('AUTO' if not base_sn else base_sn)

                for i in range(quantity):
                    if need_sn:
                        final_sn = f"{sn_prefix}-{timezone.now().strftime('%H%M%S%f')}-{i+1}"
                        if quantity == 1 and base_sn: final_sn = base_sn; status_code = 'IN_STOCK'
                    else:
                        if base_sn: final_sn = base_sn if quantity == 1 else f"{base_sn}-{i+1}"
                        else: final_sn = f"AUTO-{timezone.now().strftime('%Y%m%d%H%M%S%f')}-{i+1}"
                    if StockItem.objects.filter(tenant=tenant, sn=final_sn).exists(): final_sn += f"_DUP{i}"
                    StockItem.objects.create(tenant=tenant, product=product, sn=final_sn, real_cost=cost, status=status_code, supplier_id=supplier_id, note=data.get('note',''))

                if supplier_id:
                    sup = Contact.objects.get(id=supplier_id)
                    if data.get('account_id') and paid > 0:
                        acc = CapitalAccount.objects.get(id=data.get('account_id'))
                        
                        # 🟢 修正1：采购支出，记录为负数！
                        Transaction.objects.create(
                            tenant=tenant, contact=sup, product=product, account=acc, 
                            amount=paid * -1,  # 强制转负
                            total_amount=paid, type='BUY', 
                            operator=user, remark=f"采购: {name} x {quantity}"
                        )
                        acc.current_balance -= paid; acc.save()
                    
                    total_cost = cost * quantity; debt = total_cost - paid
                    if debt != 0: Contact.objects.filter(id=sup.id).update(balance=F('balance') - debt)

            return Response(self.get_serializer(product).data, status=201)
        except Exception as e: return Response({'detail': f'入库失败: {str(e)}'}, 400)

    def _gen_code(self, user, cat):
        initials = getattr(user, 'initials', 'AD'); dt = timezone.now(); prefix = f"{str(dt.year)[-2:]}{dt.month}{dt.day:02d}{initials}{cat}"
        count = Product.objects.filter(category=cat, tenant=user.tenant).count() + 1; return f"{prefix}{count}"

    @action(detail=True, methods=['post'])
    def sell(self, request, pk=None):
        product = self.get_object(); user = request.user
        try: quantity = int(request.data.get('quantity', 1))
        except: quantity = 1
        
        stocks = StockItem.objects.filter(product=product, status='IN_STOCK', tenant=user.tenant).order_by('id')[:quantity]
        if stocks.count() < quantity: return Response({'detail': f'库存不足! 剩余 {stocks.count()}'}, 400)
        
        unit_price = Decimal(str(request.data.get('price')))
        received = Decimal(str(request.data.get('received_amount', 0) or 0))
        contact_id = request.data.get('contact_id'); acc_id = request.data.get('account_id')
        total_sell = unit_price * quantity
        
        try:
            with transaction.atomic():
                for s in stocks: 
                    s.status = 'SOLD'; s.sold_price = unit_price; s.out_time = timezone.now(); s.save()
                remaining = StockItem.objects.filter(product=product, status='IN_STOCK', tenant=user.tenant).count()
                product.status = 'SOLD' if remaining == 0 else 'IN_STOCK'; product.save()
                
                contact = Contact.objects.get(id=contact_id)
                acc = CapitalAccount.objects.get(id=acc_id) if acc_id else None
                
                # 销售收入，记录为正数 (默认就是正，保持不变)
                Transaction.objects.create(tenant=user.tenant, contact=contact, product=product, account=acc, amount=received, total_amount=total_sell, type='SALE', operator=user, remark=f"销售: {product.name} x {quantity}")
                if acc and received > 0: acc.current_balance += received; acc.save()
                debt = total_sell - received
                if debt != 0: Contact.objects.filter(id=contact.id).update(balance=F('balance') + debt)
                return Response({'msg': 'OK'})
        except Exception as e: return Response({'detail': str(e)}, 500)

class ContactViewSet(TenantAwareViewSet):
    queryset = Contact.objects.all().order_by('-id'); serializer_class = ContactSerializer
    filter_backends = [filters.SearchFilter]; search_fields = ['name', 'phone']
    
    def create(self, request, *args, **kwargs):
        if Contact.objects.filter(tenant=request.user.tenant, name=request.data.get('name')).exists():
            return Response(self.get_serializer(Contact.objects.get(tenant=request.user.tenant, name=request.data.get('name'))).data)
        return super().create(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'])
    def repay(self, request, pk=None):
        try:
            with transaction.atomic():
                contact = Contact.objects.select_for_update().get(id=pk, tenant=request.user.tenant)
                amt = Decimal(str(request.data.get('amount', 0)))
                atype = request.data.get('action_type')
                acc_id = request.data.get('account_id')
                if amt <= 0: return Response({'detail': '金额无效'}, 400)
                
                acc = CapitalAccount.objects.get(id=acc_id, tenant=request.user.tenant)
                
                final_amount = amt # 默认正数
                
                # 🟢 修正2：核销逻辑严格分正负
                if atype == 'in': 
                    # 收款：余额减少(债务减少)，账户增加，金额为正
                    contact.balance -= amt; acc.current_balance += amt
                    ttype = 'SALE'; remark_text = "[资金] 收款 (入账)"
                    final_amount = amt
                else: 
                    # 付款：余额增加(我欠钱变少)，账户减少，金额为负
                    contact.balance += amt; acc.current_balance -= amt
                    ttype = 'BUY'; remark_text = "[资金] 付款 (出账)"
                    final_amount = amt * -1 # 强制转负
                
                contact.save(); acc.save()
                
                Transaction.objects.create(
                    tenant=request.user.tenant, contact=contact, account=acc, 
                    amount=final_amount, # 使用带符号的金额
                    total_amount=0, type=ttype, 
                    operator=request.user, remark=remark_text
                )
                
                return Response({'msg': 'OK', 'new_balance': contact.balance})
        except Exception as e: return Response({'detail': str(e)}, 400)
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        txs = Transaction.objects.filter(tenant=request.user.tenant, contact_id=pk).select_related('product').order_by('-created_at')
        res = []
        for t in txs:
            # 🟢 修正3：判断是否为收入 (正数为入，负数为出)
            is_in = t.amount > 0
            desc = t.remark or '-'
            if not t.product:
                if "核销: in" in desc: desc = "[资金] 收款 (入账)"
                elif "核销: out" in desc: desc = "[资金] 付款 (出账)"
            res.append({'date': t.created_at.strftime('%Y-%m-%d %H:%M'), 'type': t.get_type_display(), 'remark': desc, 'amount': abs(t.amount), 'sign': '+' if is_in else '-', 'is_income': is_in})
        return Response(res)

class RentalViewSet(TenantAwareViewSet):
    queryset = RentalContract.objects.all().order_by('-id'); serializer_class = RentalContractSerializer

class AnalysisViewSet(viewsets.ViewSet):
    authentication_classes = (CsrfExemptSessionAuthentication, )
    def _get_qs(self, model): return model.objects.filter(tenant=self.request.user.tenant) if self.request.user.tenant else model.objects.none()
    
    @action(detail=False)
    def dashboard(self, request):
        today = timezone.localtime(timezone.now()).date()
        txs = self._get_qs(Transaction)
        sales_today = txs.filter(type='SALE', created_at__date=today, product__isnull=False).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        stock_val = self._get_qs(StockItem).filter(status='IN_STOCK').aggregate(Sum('real_cost'))['real_cost__sum'] or 0
        recent = []
        for t in txs.select_related('product', 'contact').order_by('-created_at')[:10]:
            time_str = timezone.localtime(t.created_at).strftime('%m-%d %H:%M')
            if not t.product:
                c_name = t.contact.name if t.contact else '未知'
                real_money = abs(t.amount)
                desc = t.remark
                # 文案对齐
                if "核销: in" in desc or (t.type == 'SALE' and "核销" in desc): desc = f"[资金] 收款: {c_name}"
                elif "核销: out" in desc or (t.type == 'BUY' and "核销" in desc): desc = f"[资金] 付款: {c_name}"
                else: 
                    if t.type == 'SALE': desc = f"[资金] 收款: {c_name}"
                    else: desc = f"[资金] 付款: {c_name}"
                
                amt_display = real_money; is_in = t.amount > 0
            else:
                amt_display = t.total_amount if (t.type == 'SALE' and t.total_amount > 0) else t.amount
                desc = f"[{t.get_type_display()}] {t.product.name}"
                is_in = t.amount > 0
            recent.append({'id': t.id, 'desc': desc, 'amount': amt_display, 'is_income': is_in, 'time': time_str})
        contacts = self._get_qs(Contact)
        recv = contacts.filter(balance__gt=0).aggregate(Sum('balance'))['balance__sum'] or 0
        pay = contacts.filter(balance__lt=0).aggregate(Sum('balance'))['balance__sum'] or 0
        cash = self._get_qs(CapitalAccount).aggregate(Sum('current_balance'))['current_balance__sum'] or 0
        
        cat_data = txs.filter(type='SALE', product__isnull=False).values('product__category').annotate(total=Count('id'))
        cat_map = {'ZJ':'整机', 'PH':'手机', 'TB':'平板', 'XS':'显示器', 'SJ':'散件', 'ZX':'杂项'}
        pie_labels = []; pie_data = []
        for c in cat_data: pie_labels.append(cat_map.get(c['product__category'], '其他')); pie_data.append(c['total'])
        if not pie_data: pie_labels = ['暂无数据']; pie_data = [1]
        days = []; sales = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i); days.append(d.strftime('%m-%d'))
            val = txs.filter(type='SALE', created_at__date=d, product__isnull=False).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
            sales.append(float(val))
        return Response({'cards': {'stock_val': stock_val, 'total_sales_amount': sales_today, 'receivable': recv, 'payable': abs(pay), 'cash': cash}, 'recent_list': recent, 'charts': {'trend': {'labels': days, 'data': sales}, 'category': {'labels': pie_labels, 'data': pie_data}}})

    @action(detail=False)
    def accounting(self, request):
        accs = self._get_qs(CapitalAccount); items = self._get_qs(StockItem); cts = self._get_qs(Contact)
        cash = accs.aggregate(Sum('current_balance'))['current_balance__sum'] or 0
        stock = items.filter(status='IN_STOCK').aggregate(Sum('real_cost'))['real_cost__sum'] or 0
        recv = cts.filter(balance__gt=0).aggregate(Sum('balance'))['balance__sum'] or 0
        pay = cts.filter(balance__lt=0).aggregate(Sum('balance'))['balance__sum'] or 0
        return Response({'cash': cash, 'stock': stock, 'receivable': recv, 'payable': abs(pay), 'net_worth': cash + stock + recv + pay, 'accounts': [{'id': a.id, 'name': a.name, 'balance': a.current_balance} for a in accs]})
        
    @action(detail=False)
    def profit_dashboard(self, request):
        user = request.user
        if not user.tenant: return Response({})
        start = request.query_params.get('start_date'); end = request.query_params.get('end_date')
        txs = Transaction.objects.filter(tenant=user.tenant, type='SALE', product__isnull=False).select_related('product', 'contact', 'operator').order_by('-created_at')
        if start: txs = txs.filter(created_at__date__gte=start)
        if end: txs = txs.filter(created_at__date__lte=end)
        total_sales = 0; total_cost = 0; list_data = []
        for t in txs:
            sale_amt = t.total_amount if t.total_amount > 0 else t.amount
            cost_amt = t.product.cost_price if t.product else 0
            profit = sale_amt - cost_amt
            total_sales += sale_amt; total_cost += cost_amt
            list_data.append({'date': t.created_at.strftime('%Y-%m-%d %H:%M'), 'zencode': t.product.zencode if t.product else '-', 'product_name': t.product.name if t.product else '未知', 'customer': t.contact.name if t.contact else '散客', 'sales': sale_amt, 'profit': profit, 'staff': t.operator.first_name if t.operator else '系统'})
        return Response({'summary': {'sales': total_sales, 'cost': total_cost, 'profit': total_sales - total_cost, 'margin': round((total_sales - total_cost) / total_sales * 100, 1) if total_sales > 0 else 0}, 'list': list_data})

    @action(detail=False)
    def account_history(self, request):
        acc_id = request.query_params.get('id')
        if not acc_id: return Response([])
        txs = Transaction.objects.filter(tenant=self.request.user.tenant, account_id=acc_id).select_related('product', 'contact').order_by('-created_at')
        res = []
        for t in txs:
            # 🟢 修正4：直接用正负判断
            is_in = t.amount > 0
            if not t.product:
                target = t.contact.name if t.contact else '未知'
                desc = t.remark
                if "核销: in" in desc: desc = f"[资金] 收款: {target}"
                elif "核销: out" in desc: desc = f"[资金] 付款: {target}"
                elif not desc: 
                    if t.type == 'SALE': desc = f"[资金] 收款: {target}"
                    else: desc = f"[资金] 付款: {target}"
                type_name = '资金收入' if is_in else '资金支出'
            else:
                type_name = t.get_type_display(); desc = t.product.name
            res.append({'date': t.created_at.strftime('%Y-%m-%d %H:%M'), 'type_name': type_name, 'remark': desc, 'amount': abs(t.amount), 'sign': '+' if is_in else '-', 'is_income': is_in})
        return Response(res)

# ==========================================
# 🟢 5. 全量单据中心 API (完整版 - 含筛选修正)
# ==========================================
class TransactionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'

class TransactionViewSet(TenantAwareViewSet):
    queryset = Transaction.objects.all().order_by('-created_at')
    serializer_class = TransactionSerializer
    pagination_class = TransactionPagination

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # 🟢 核心修正：筛选逻辑完全对齐“正负法则”
        ftype = request.query_params.get('filter')
        if ftype == 'in': 
            # 收入 = 纯正数
            # 兼容：如果有旧的 type='SALE' 但是金额为正，也算收入
            queryset = queryset.filter(amount__gt=0)
        elif ftype == 'out': 
            # 支出 = 纯负数
            # 兼容：如果旧数据是正数但 type='BUY'，也算支出！(这是解决您“支出搜不到”的关键)
            queryset = queryset.filter(Q(amount__lt=0) | Q(type='BUY'))
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            data = []
            for t in page:
                desc = t.remark
                # 兼容旧数据文案
                if "核销: in" in (desc or ""): desc = "[资金] 收款 (入账)"
                elif "核销: out" in (desc or ""): desc = "[资金] 付款 (出账)"
                
                if t.product: desc = f"[{t.get_type_display()}] {t.product.name}"
                elif not desc: desc = "资金变动"
                
                is_void = "【冲红" in (t.remark or "")
                
                # 🟢 判断方向：正数 或者 (是正数但是Type=SALE) -> 入
                # 旧数据兼容：如果是 BUY 且金额是正数 -> 实际上是支出
                is_income = t.amount > 0
                if t.amount > 0 and t.type == 'BUY': is_income = False 
                
                time_str = timezone.localtime(t.created_at).strftime('%Y-%m-%d %H:%M')
                type_str = t.get_type_display()
                obj_str = t.contact.name if t.contact else '-'
                acc_str = t.account.name if t.account else '挂账'

                data.append({
                    'id': t.id,
                    'amount': abs(t.amount), # 前端只显示绝对值，符号由 is_income 决定
                    'remark': desc,
                    'is_income': is_income,
                    'is_void': is_void,
                    
                    'date': time_str,
                    'created_at': time_str, 
                    'created_at_fmt': time_str, 
                    
                    'type_name': type_str,
                    'type_display': type_str,
                    'type': type_str, 
                    
                    'account_name': acc_str,
                    'account_id': t.account.id if t.account else None,
                    
                    'related_object': obj_str,
                    'object': obj_str,
                    'contact_name': obj_str,
                    'contact_id': t.contact.id if t.contact else None,
                    
                    'raw_date': t.created_at.strftime('%Y-%m-%d')
                })
            return self.get_paginated_response(data)
        return Response([])

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        origin = self.get_object()
        if "【冲红" in (origin.remark or ""): return Response({'detail': '已作废'}, 400)
        
        try:
            with transaction.atomic():
                if origin.account:
                    acc = CapitalAccount.objects.select_for_update().get(id=origin.account.id)
                    acc.current_balance -= origin.amount
                    acc.save()
                
                if origin.contact:
                    ct = Contact.objects.select_for_update().get(id=origin.contact.id)
                    if origin.type in ['SALE', 'OTHER']: ct.balance += origin.amount
                    elif origin.type in ['BUY', 'RENT']: ct.balance -= origin.amount
                    ct.save()
                
                Transaction.objects.create(
                    tenant=request.user.tenant,
                    contact=origin.contact,
                    product=origin.product,
                    account=origin.account,
                    amount=origin.amount * -1,
                    total_amount=0,
                    type=origin.type,
                    operator=request.user,
                    remark=f"【冲红/作废】原单#{origin.id}"
                )
                return Response({'status': 'ok'})
        except Exception as e:
            return Response({'detail': str(e)}, 400)

    @action(detail=True, methods=['post'])
    def correct(self, request, pk=None):
        origin = self.get_object()
        if "【冲红" in (origin.remark or ""): return Response({'detail': '已作废单据不可更正'}, 400)
        
        new_amt = Decimal(str(request.data.get('amount', origin.amount)))
        new_contact_id = request.data.get('contact_id')
        new_acc_id = request.data.get('account_id')
        new_remark = request.data.get('remark', origin.remark)
        new_date = request.data.get('date') 
        
        try:
            with transaction.atomic():
                # 1. 回滚
                if origin.account:
                    acc = CapitalAccount.objects.select_for_update().get(id=origin.account.id)
                    acc.current_balance -= origin.amount
                    acc.save()
                if origin.contact:
                    ct = Contact.objects.select_for_update().get(id=origin.contact.id)
                    if origin.type in ['SALE', 'OTHER']: ct.balance += origin.amount
                    elif origin.type in ['BUY', 'RENT']: ct.balance -= origin.amount
                    ct.save()
                
                # 2. 更新对象 (如果原单是BUY，新金额也应该是负数)
                # 智能识别方向：如果原单是负数，新输入的金额也转为负数
                final_new_amt = new_amt
                if origin.amount < 0 and new_amt > 0:
                    final_new_amt = new_amt * -1
                
                if new_contact_id: origin.contact = Contact.objects.get(id=new_contact_id)
                if new_acc_id: origin.account = CapitalAccount.objects.get(id=new_acc_id)
                origin.amount = final_new_amt
                origin.remark = new_remark
                if new_date:
                    old_time = timezone.localtime(origin.created_at).time()
                    new_dt = datetime.strptime(new_date, '%Y-%m-%d')
                    origin.created_at = timezone.make_aware(datetime.combine(new_dt, old_time))
                
                # 3. 应用新值
                if origin.account:
                    acc_new = CapitalAccount.objects.select_for_update().get(id=origin.account.id)
                    acc_new.current_balance += final_new_amt
                    acc_new.save()
                if origin.contact:
                    ct_new = Contact.objects.select_for_update().get(id=origin.contact.id)
                    if origin.type in ['SALE', 'OTHER']: ct_new.balance -= final_new_amt
                    elif origin.type in ['BUY', 'RENT']: ct_new.balance += final_new_amt
                    ct_new.save()
                
                origin.save()
                return Response({'status': 'ok', 'msg': '更正成功'})
        except Exception as e:
            return Response({'detail': str(e)}, 400)