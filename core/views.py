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

from core.models import Product, Contact, RentalContract, Transaction, CapitalAccount, CustomUser, Tenant, StockItem
from core.serializers import ProductSerializer, ContactSerializer, RentalContractSerializer, TransactionSerializer, StaffSerializer, TenantSerializer, CapitalAccountSerializer, StockItemSerializer

class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request): return

# ==========================================
# 📄 1. 页面路由 (Page Views)
# ==========================================
def index_page(request): return render(request, 'index.html') if request.user.is_authenticated else redirect('/login/')
def login_page(request): return redirect('/') if request.user.is_authenticated else render(request, 'login.html')
def register_page(request): return render(request, 'register.html')
def staff_page(request): return render(request, 'staff.html') if request.user.is_authenticated else redirect('/login/')
def company_page(request): return render(request, 'company.html') if request.user.is_authenticated else redirect('/login/')

# 核心业务
def entry_page(request): return render(request, 'entry.html') if request.user.is_authenticated else redirect('/login/')
def sales_page(request): return render(request, 'sales.html') if request.user.is_authenticated else redirect('/login/')
def contact_page(request): return render(request, 'contact.html') if request.user.is_authenticated else redirect('/login/')

# 🟢 客户详情页 (解决 404)
def contact_detail_page(request, id):
    if not request.user.is_authenticated: return redirect('/login/')
    return render(request, 'contact_detail.html', {'contact_id': id})

def inventory_page(request): return render(request, 'inventory.html') if request.user.is_authenticated else redirect('/login/')
def rental_hub_page(request): return render(request, 'rental_hub.html') if request.user.is_authenticated else redirect('/login/')
def rental_create_page(request): return render(request, 'rental_create.html') if request.user.is_authenticated else redirect('/login/')

# 报表分析
def profit_page(request): return render(request, 'analysis_profit.html') if request.user.is_authenticated else redirect('/login/')
def finance_page(request): return render(request, 'analysis_finance.html') if request.user.is_authenticated else redirect('/login/')
def account_page(request): return render(request, 'analysis_account.html') if request.user.is_authenticated else redirect('/login/')
def profile_page(request): return render(request, 'profile.html') if request.user.is_authenticated else redirect('/login/')

# ==========================================
# 🧱 2. API 基类 (Base ViewSet)
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
# 👤 3. 用户与租户 (User & Tenant)
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


class TransactionViewSet(viewsets.ViewSet):
    """资金单据中心 API
    - 列表：GET /api/transactions/?page=1&page_size=20&include_voided=0
    - 作废：POST /api/transactions/{id}/void/
    - 更正：POST /api/transactions/{id}/correct/  (会先作废旧流水，再生成新流水)
    说明：遵循“宪法”——只改当前问题，不改 UI、不动既有业务流程；这里只补齐缺失的 API 和最小必要的账务联动。
    """

    permission_classes = [permissions.IsAuthenticated]

    def _qs(self, model):
        # 多租户：按当前用户 tenant 过滤（兼容历史数据 tenant 为空）
        tenant = getattr(getattr(self.request, 'user', None), 'tenant', None)
        qs = model.objects.all()
        if tenant is not None and hasattr(model, 'tenant'):
            qs = qs.filter(tenant=tenant)
        return qs

    def list(self, request):
        from core.models import Transaction
        from core.serializers import TransactionSerializer

        include_voided = request.GET.get('include_voided', '0') in ['1', 'true', 'True']
        qs = self._qs(Transaction).order_by('-created_at')
        # 兼容旧库（没有字段时不报错）
        if not include_voided and hasattr(Transaction, 'is_voided'):
            qs = qs.filter(is_voided=False)

        # 简易分页（与前端 page/page_size 对齐）
        try:
            page = int(request.GET.get('page', '1'))
            page_size = int(request.GET.get('page_size', '20'))
        except Exception:
            page, page_size = 1, 20
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)

        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        data = TransactionSerializer(qs[start:end], many=True).data
        return Response({'count': total, 'results': data})

    def create(self, request):
        # 当前版本前端未用到 create；保留最小实现，避免误用导致账务混乱
        return Response({'detail': 'Not implemented'}, status=405)

    def _reverse_balance_effect_safe(self, tx):
        """尽量安全地反向回滚一条流水对账户/往来的影响。
        只对“核销收款/核销付款”这类明确方向的流水做全局联动，避免误判。
        """
        from django.utils import timezone
        from core.models import CapitalAccount, Contact

        remark = (tx.remark or '').strip()
        acct = tx.account if hasattr(tx, 'account') else None
        contact = tx.contact if hasattr(tx, 'contact') else None
        amt = float(tx.amount or 0)

        # 1) 明确的核销流水：严格回滚（最关键）
        if remark.startswith('收款核销'):
            if contact: contact.balance = (contact.balance or 0) + amt; contact.save(update_fields=['balance'])
            if acct: acct.current_balance = (acct.current_balance or 0) - amt; acct.save(update_fields=['current_balance'])
            return True

        if remark.startswith('付款核销'):
            if contact: contact.balance = (contact.balance or 0) - amt; contact.save(update_fields=['balance'])
            if acct: acct.current_balance = (acct.current_balance or 0) + amt; acct.save(update_fields=['current_balance'])
            return True

        # 2) 其他流水：仅回滚资金账户（按既有规则：SALE/RENT/OTHER 为入，BUY 为出）
        #    不回滚 contact.balance（缺少明确方向字段，误判风险高）
        if acct:
            is_income = tx.type in ['SALE', 'RENT', 'OTHER']
            delta = -amt if is_income else +amt
            acct.current_balance = (acct.current_balance or 0) + delta
            acct.save(update_fields=['current_balance'])
            return True

        return False

    def _apply_balance_effect_safe(self, tx):
        """尽量安全地应用一条流水对账户/往来的影响（用于更正生成的新流水）"""
        from core.models import CapitalAccount, Contact

        remark = (tx.remark or '').strip()
        acct = tx.account if hasattr(tx, 'account') else None
        contact = tx.contact if hasattr(tx, 'contact') else None
        amt = float(tx.amount or 0)

        if remark.startswith('收款核销'):
            if contact: contact.balance = (contact.balance or 0) - amt; contact.save(update_fields=['balance'])
            if acct: acct.current_balance = (acct.current_balance or 0) + amt; acct.save(update_fields=['current_balance'])
            return True

        if remark.startswith('付款核销'):
            if contact: contact.balance = (contact.balance or 0) + amt; contact.save(update_fields=['balance'])
            if acct: acct.current_balance = (acct.current_balance or 0) - amt; acct.save(update_fields=['current_balance'])
            return True

        if acct:
            is_income = tx.type in ['SALE', 'RENT', 'OTHER']
            delta = +amt if is_income else -amt
            acct.current_balance = (acct.current_balance or 0) + delta
            acct.save(update_fields=['current_balance'])
            return True

        return False

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        from django.utils import timezone
        from core.models import Transaction

        tx = self._qs(Transaction).filter(id=pk).first()
        if not tx:
            return Response({'detail': 'Not found'}, status=404)

        if getattr(tx, 'is_voided', False):
            return Response({'detail': 'Already voided'}, status=400)

        # 先回滚余额影响（安全回滚）
        self._reverse_balance_effect_safe(tx)

        # 标记作废
        if hasattr(tx, 'is_voided'):
            tx.is_voided = True
        if hasattr(tx, 'void_reason'):
            tx.void_reason = str(request.data.get('reason', '') or '')[:200]
        if hasattr(tx, 'voided_at'):
            tx.voided_at = timezone.now()
        tx.save()

        return Response({'ok': True})

    @action(detail=True, methods=['post'])
    def correct(self, request, pk=None):
        """更正：作废旧流水 + 生成新流水（并联动余额）"""
        from django.utils import timezone
        from core.models import Transaction

        old = self._qs(Transaction).filter(id=pk).first()
        if not old:
            return Response({'detail': 'Not found'}, status=404)
        if getattr(old, 'is_voided', False):
            return Response({'detail': 'Cannot correct a voided transaction'}, status=400)

        try:
            new_amount = float(request.data.get('amount', old.amount))
        except Exception:
            return Response({'detail': 'Invalid amount'}, status=400)

        # 1) 先作废旧流水（含回滚余额）
        self._reverse_balance_effect_safe(old)
        if hasattr(old, 'is_voided'):
            old.is_voided = True
        if hasattr(old, 'void_reason'):
            old.void_reason = str(request.data.get('reason', '更正作废') or '')[:200]
        if hasattr(old, 'voided_at'):
            old.voided_at = timezone.now()
        old.save()

        # 2) 生成新流水（尽量沿用旧字段）
        new_tx = Transaction.objects.create(
            tenant=getattr(old, 'tenant', None),
            type=old.type,
            contact=old.contact,
            product=old.product,
            stock_item=old.stock_item if hasattr(old, 'stock_item') else None,
            account=old.account,
            amount=new_amount,
            total_amount=new_amount if getattr(old, 'total_amount', None) is not None else None,
            remark=str(request.data.get('remark', old.remark or '') or '')[:200],
            corrected_from=old if hasattr(old, 'corrected_from') else None,
        )

        # 3) 应用新流水对余额的影响
        self._apply_balance_effect_safe(new_tx)

        return Response({'ok': True, 'new_id': new_tx.id})


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
                        Transaction.objects.create(tenant=tenant, contact=sup, product=product, account=acc, amount=paid, total_amount=paid, type='BUY', operator=user, remark=f"采购: {name} x {quantity}")
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
        # 🟢 核销核心修复：使用悲观锁 select_for_update 防止并发，确保余额准确
        try:
            with transaction.atomic():
                contact = Contact.objects.select_for_update().get(id=pk, tenant=request.user.tenant)
                amt = Decimal(str(request.data.get('amount', 0)))
                atype = request.data.get('action_type')
                acc_id = request.data.get('account_id')
                if amt <= 0: return Response({'detail': '金额无效'}, 400)
                
                acc = CapitalAccount.objects.get(id=acc_id, tenant=request.user.tenant)
                
                if atype == 'in': 
                    contact.balance -= amt; acc.current_balance += amt
                    ttype = 'SALE'; remark_text = "[资金] 收款核销"
                else: 
                    contact.balance += amt; acc.current_balance -= amt
                    ttype = 'BUY'; remark_text = "[资金] 付款核销"
                
                contact.save(); acc.save()
                Transaction.objects.create(tenant=request.user.tenant, contact=contact, account=acc, amount=amt, total_amount=0, type=ttype, operator=request.user, remark=remark_text)
                
                return Response({'msg': 'OK', 'new_balance': contact.balance})
        except Exception as e: return Response({'detail': str(e)}, 400)
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        # 🟢 修复流水文案：资金往来显示 [资金]，商品显示名称
        txs = Transaction.objects.filter(tenant=request.user.tenant, contact_id=pk).select_related('product').order_by('-created_at')
        res = []
        for t in txs:
            is_in = t.type in ['SALE', 'RENT', 'OTHER'] and t.type != 'BUY'
            desc = t.product.name if t.product else (t.remark or '-')
            if not t.product:
                if t.type == 'SALE': desc = "[资金] 收款 (入账)"
                elif t.type == 'BUY': desc = "[资金] 付款 (出账)"
            res.append({'date': t.created_at.strftime('%Y-%m-%d %H:%M'), 'type': t.get_type_display(), 'remark': desc, 'amount': t.amount, 'sign': '+' if is_in else '-', 'is_income': is_in})
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
                if t.type == 'SALE': desc = f"[资金] {c_name} 付款给我: 收入 {real_money}"; amt_display = real_money; is_in = True
                else: desc = f"[资金] 付款给 {c_name}: 支出 {real_money}"; amt_display = real_money; is_in = False
            else:
                amt_display = t.total_amount if (t.type == 'SALE' and t.total_amount > 0) else t.amount
                type_str = {'SALE': '销售', 'BUY': '采购', 'RENT': '租赁', 'OTHER': '其他'}.get(t.type, t.type)
                desc = f"[{type_str}] {t.product.name}"
                is_in = t.type in ['SALE', 'RENT', 'OTHER']
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
        # 🟢 修复：补全 ZenCode
        user = request.user
        tenant = getattr(user, 'tenant', None)
        if not tenant:
            return Response({'cards': {'stock_val': 0, 'total_sales_amount': 0, 'receivable': 0, 'payable': 0, 'cash': 0}, 'recent_list': [], 'charts': {'trend': {'labels': [], 'data': []}, 'category': {'labels': ['暂无数据'], 'data': [1]}}}, status=200)
        start = request.query_params.get('start_date'); end = request.query_params.get('end_date')
        txs = Transaction.objects.filter(tenant=tenant, type='SALE', product__isnull=False).select_related('product', 'contact', 'operator').order_by('-created_at')
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
        # 🟢 修复：资金流水文案对齐主页
        acc_id = request.query_params.get('id')
        if not acc_id: return Response([])
        txs = Transaction.objects.filter(tenant=self.request.user.tenant, account_id=acc_id).select_related('product', 'contact').order_by('-created_at')
        res = []
        for t in txs:
            is_in = t.type in ['SALE', 'RENT', 'OTHER'] and t.type != 'BUY'
            if not t.product:
                target = t.contact.name if t.contact else '未知'
                if t.type == 'SALE': type_name = '资金收入'; desc = f"[资金] {target} 付款给我"
                else: type_name = '资金支出'; desc = f"[资金] 付款给 {target}"
            else:
                type_name = t.get_type_display(); desc = t.product.name
            res.append({'date': t.created_at.strftime('%Y-%m-%d %H:%M'), 'type_name': type_name, 'remark': desc, 'amount': t.amount, 'sign': '+' if is_in else '-', 'is_income': is_in})
        return Response(res)