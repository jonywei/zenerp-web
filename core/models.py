from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.utils.html import format_html
from django.core.exceptions import ValidationError

# ==========================================
# 🧱 1. 多租户基石 (SaaS 核心)
# ==========================================

class Tenant(models.Model):
    """租户表：代表一个公司/团队"""
    name = models.CharField(max_length=100, verbose_name="公司名称")
    owner_name = models.CharField(max_length=50, verbose_name="负责人")
    phone = models.CharField(max_length=20, unique=True, verbose_name="登录手机号")
    
    is_active = models.BooleanField(default=True, verbose_name="状态(审核)")
    account_limit = models.IntegerField(default=5, verbose_name="最大子账户数")
    expire_date = models.DateField(null=True, blank=True, verbose_name="到期时间")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.name
    class Meta: verbose_name = "🏢 租户管理"; verbose_name_plural = verbose_name

class TenantAwareModel(models.Model):
    """抽象基类：所有业务表继承它，自动隔离数据"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, verbose_name="所属租户")
    class Meta: abstract = True

# ==========================================
# 👤 2. 用户系统
# ==========================================

class CustomUser(AbstractUser):
    # 关联租户 (为空则是平台超级管理员)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, verbose_name="所属公司")
    
    ROLE_CHOICES = (('ADMIN', '👑 管理员'), ('FINANCE', '💰 财务'), ('SALES', '👤 销售'))
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='SALES', verbose_name="角色")
    initials = models.CharField(max_length=5, default='XX', verbose_name="头像字符")
    
    class Meta: verbose_name = "员工账号"; verbose_name_plural = verbose_name

    def save(self, *args, **kwargs):
        if self.tenant and not self.pk:
            if CustomUser.objects.filter(tenant=self.tenant).count() >= self.tenant.account_limit:
                raise ValidationError(f"子账户额度已满 ({self.tenant.account_limit}个)！")
        super().save(*args, **kwargs)

# ==========================================
# 📦 3. 商品与库存 (SPU-SKU 架构)
# ==========================================

class Product(TenantAwareModel):
    """【商品档案 (SPU)】"""
    TYPE_CHOICES = (('ZJ', '💻 电脑主机'), ('PH', '📱 手机'), ('TB', '📟 平板'), ('XS', '📺 显示器'), ('SJ', '🔩 散件'), ('ZX', '📦 杂项'))
    STATUS_CHOICES = (('IN_STOCK', '在库'), ('RENTED', '在租'), ('TRANSIT', '中转/外借'), ('SOLD', '已售'), ('REPAIR', '维修'))

    zencode = models.CharField(max_length=20, blank=True, verbose_name="编码")
    name = models.CharField(max_length=200, verbose_name="商品名称")
    category = models.CharField(max_length=2, choices=TYPE_CHOICES, verbose_name="分类")
    
    # 硬件参数 (保持原样，适配前端)
    cpu = models.CharField(max_length=50, blank=True, verbose_name="CPU/品牌")
    gpu = models.CharField(max_length=50, blank=True, verbose_name="显卡/颜色")
    ram = models.CharField(max_length=50, blank=True, verbose_name="内存/型号")
    disk = models.CharField(max_length=50, blank=True, verbose_name="硬盘/容量")
    note = models.CharField(max_length=100, blank=True, verbose_name="备注")
    
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="参考成本")
    peer_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="同行底价")
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="零售指导")
    sold_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="实际成交价") # 保留字段
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='IN_STOCK', verbose_name="整体状态")
    image = models.ImageField(upload_to='%Y/%m/', blank=True, null=True, verbose_name="图片")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="入库时间")

    def __str__(self): return self.name
    class Meta: verbose_name = "📂 商品档案(SPU)"; verbose_name_plural = verbose_name

class StockItem(TenantAwareModel):
    """【具体库存 (SKU)】新增表"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_items', verbose_name="所属商品")
    sn = models.CharField(max_length=100, verbose_name="序列号/IMEI")
    real_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="真实入库价")
    
    STATUS_CHOICES = (('IN_STOCK', '✅ 在库'), ('RENTED', '🔄 在租'), ('SOLD', '💰 已售'), ('BAD', '🚫 报废'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_STOCK', verbose_name="当前状态")
    supplier = models.ForeignKey('Contact', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="供应商") # 新增供应商关联
    note = models.CharField(max_length=200, blank=True, verbose_name="单机备注")
    in_time = models.DateTimeField(auto_now_add=True, verbose_name="入库时间")

    class Meta:
        verbose_name = "📦 库存实物(SKU)"; verbose_name_plural = verbose_name
        unique_together = ('tenant', 'sn') # 同一租户下SN唯一

    def __str__(self): return f"{self.product.name} ({self.sn})"

    def status_tag(self):
        # 兼容 admin 调用
        return self.get_status_display()

# ==========================================
# 💰 4. 财务与业务 (升级为多租户)
# ==========================================

class CapitalAccount(TenantAwareModel):
    name = models.CharField(max_length=50, verbose_name="账户名称")
    initial_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="期初余额")
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="当前余额")
    def __str__(self): return self.name
    class Meta: verbose_name = "资金账户"; verbose_name_plural = verbose_name

class Contact(TenantAwareModel):
    name = models.CharField(max_length=50, verbose_name="姓名")
    phone = models.CharField(max_length=20, blank=True, verbose_name="电话")
    # 🟢 修复：新增地址字段，解决400报错
    address = models.CharField(max_length=100, blank=True, verbose_name="地址/档口")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="余额")
    def __str__(self): return self.name
    class Meta: verbose_name = "客户/供应商"; verbose_name_plural = verbose_name

class RentalContract(TenantAwareModel):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, verbose_name="客户")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="租赁设备")
    stock_item = models.ForeignKey(StockItem, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="具体序列号") # 新增
    operator = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, verbose_name="经手人")
    
    start_date = models.DateField(default=timezone.now, verbose_name="起租日")
    duration = models.IntegerField(default=1, verbose_name="租期(月)")
    end_date = models.DateField(null=True, blank=True, verbose_name="归还日")
    
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="押金")
    rent_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="租金")
    depreciation_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="月折旧")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="总额")
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="已付")
    expected_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="毛利")
    
    is_active = models.BooleanField(default=True, verbose_name="进行中")
    class Meta: verbose_name = "租赁合同"; verbose_name_plural = verbose_name

class Transaction(TenantAwareModel):
    TYPE_CHOICES = (('SALE', '销售收入'), ('RENT', '租金/押金'), ('BUY', '采购支出'), ('OTHER', '其他'))
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, null=True, verbose_name="关联方")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="商品")
    account = models.ForeignKey(CapitalAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="账户")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="金额")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name="类型")
    operator = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, verbose_name="经手人")
    remark = models.CharField(max_length=200, blank=True, verbose_name="摘要")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="时间")
    class Meta: verbose_name = "财务流水"; verbose_name_plural = verbose_name

# 7. 序列号工厂 (独立)
class SerialNumberFactory(TenantAwareModel):
    sn = models.CharField(max_length=100, verbose_name='序列号/IMEI')
    status = models.CharField(max_length=20, default='normal', verbose_name='状态')
    src_type = models.CharField(max_length=20, default='import', verbose_name='来源')
    check_result = models.TextField(blank=True, null=True, verbose_name='检测结果')
    create_time = models.DateTimeField(auto_now_add=True)
    class Meta: verbose_name = "🏭 序列号工厂"; verbose_name_plural = verbose_name

    def status_color(self):
        if self.status == 'normal': return format_html('<span style="color:green">✅ 正常</span>')
        elif self.status == 'banned': return format_html('<span style="color:red; font-weight:bold;">🚫 封禁</span>')
        return self.status
    status_color.short_description = '状态监控'