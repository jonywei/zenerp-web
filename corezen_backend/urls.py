
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core import views
from rest_framework.routers import DefaultRouter

admin.site.site_header = 'ZenERP 智能管理系统'
admin.site.site_title = 'ZenERP'
admin.site.index_title = '欢迎使用 ZenERP'

# ==========================================
# 1. 注册 API 路由 (Router)
# ==========================================
router = DefaultRouter()
router.register(r'products', views.ProductViewSet)
router.register(r'contacts', views.ContactViewSet)
router.register(r'rentals', views.RentalViewSet)
router.register(r'staff', views.StaffViewSet)
router.register(r'accounts', views.CapitalAccountViewSet)
router.register(r'stock', views.StockItemViewSet)
router.register(r'my-tenant', views.MyTenantViewSet, basename='my-tenant')

# ==========================================
# 2. URL 模式定义
# ==========================================
router.register(r'transactions', views.TransactionViewSet, basename='transaction')

urlpatterns = [
    # 🟢 1. Django 原生后台管理 (您找的就在这里)
    path('admin/', admin.site.urls),
    
    # 🟢 2. 页面路由 (Page Routes)
    path('', views.index_page, name='index'),
    path('login/', views.login_page, name='login'),
    path('register/', views.register_page, name='register'),
    
    # 企业/员工管理
    path('staff/', views.staff_page, name='staff'),
    path('company/', views.company_page, name='company'),
    
    # 核心业务
    path('entry/', views.entry_page, name='entry'),
    path('sales/', views.sales_page, name='sales'),
    
    # 客户/供应商
    path('contact/', views.contact_page, name='contact'),
    # 🟢 修复：客户详情页路由 (解决 404)
    path('contact/detail/<int:id>/', views.contact_detail_page, name='contact_detail'),

    # 库存与租赁
    path('inventory/', views.inventory_page, name='inventory'),
    path('rental/', views.rental_hub_page, name='rental_hub'),
    path('rental/create/', views.rental_create_page, name='rental_create'),
    
    # 报表分析
    path('analysis/profit/', views.profit_page, name='profit'),
    path('analysis/finance/', views.finance_page, name='finance'),
    path('analysis/account/', views.account_page, name='account'),
    
    # 个人中心
    path('profile/', views.profile_page, name='profile'),

    # 🟢 3. API 接口路由
    # 认证相关
    path('api/login/', views.api_login, name='api_login'),
    path('api/logout/', views.api_logout, name='api_logout'),
    path('api/change_password/', views.api_change_password, name='api_change_password'),
    path('api/register/', views.api_register, name='api_register'),
    
    # 统计分析专用接口 (手动映射 ViewSet action)
    path('api/analysis/dashboard/', views.AnalysisViewSet.as_view({'get': 'dashboard'})),
    path('api/analysis/accounting/', views.AnalysisViewSet.as_view({'get': 'accounting'})),
    path('api/analysis/profit_dashboard/', views.AnalysisViewSet.as_view({'get': 'profit_dashboard'})),
    path('api/analysis/account_history/', views.AnalysisViewSet.as_view({'get': 'account_history'})),
    
    # 挂载 Router 自动生成的 CRUD 接口
    path('api/', include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)