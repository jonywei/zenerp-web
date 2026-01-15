from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core import views

admin.site.site_header = 'ZenERP 智能管理系统'
admin.site.site_title = 'ZenERP'
admin.site.index_title = '欢迎使用 ZenERP'

router = DefaultRouter()
router.register(r'products', views.ProductViewSet)
router.register(r'contacts', views.ContactViewSet)
router.register(r'rentals', views.RentalViewSet)
router.register(r'analysis', views.AnalysisViewSet, basename='analysis')
# 🟢 新增管理接口
router.register(r'staff', views.StaffViewSet, basename='staff')
router.register(r'my-tenant', views.MyTenantViewSet, basename='my-tenant')
router.register(r'accounts', views.CapitalAccountViewSet, basename='accounts')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index_page, name='index'),
    path('login/', views.login_page, name='login'),
    path('register/', views.register_page, name='register'),
    # 🟢 新增管理页面路由
    path('staff/', views.staff_page, name='staff'),
    path('company/', views.company_page, name='company'),
    
    path('entry/', views.entry_page, name='entry'),
    path('sales/', views.sales_page, name='sales'),
    path('contact/', views.contact_page, name='contact'),
    path('inventory/', views.inventory_page, name='inventory'),
    path('rental/', views.rental_hub_page, name='rental_hub'),
    path('rental/create/', views.rental_create_page, name='rental_create'),
    path('analysis/profit/', views.profit_page, name='profit'),
    path('analysis/finance/', views.finance_page, name='finance'),
    path('analysis/account/', views.account_page, name='account'),
    path('profile/', views.profile_page, name='profile'),
    
    path('api/login/', views.api_login),
    path('api/logout/', views.api_logout),
    path('api/change_password/', views.api_change_password),
    path('api/register/', views.api_register),
    path('api/', include(router.urls)),
]