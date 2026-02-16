from pathlib import Path
import os
# 🟢 新增：允许 CSRF 校验的域名白名单
CSRF_TRUSTED_ORIGINS = ['https://a.corezen.sit']
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'django-insecure-corezen-secret-key-change-me'
DEBUG = True
ALLOWED_HOSTS = ['*', 'a.corezen.site', 'localhost']

# --- 🟢 域名修改核心配置 (已更新为 a.corezen.site) ---

# 允许访问的主机头 (生产环境建议写具体域名，或保持 '*' 允许所有)
ALLOWED_HOSTS = ['*', 'a.corezen.site']

# 🟢 关键：CSRF 白名单 (必须包含新域名的 HTTP 和 HTTPS)
CSRF_TRUSTED_ORIGINS = [
    'https://a.corezen.site',
    'http://a.corezen.site', 
    'https://erp.zengain.cn'  # 保留旧的也没事，以防万一
]

INSTALLED_APPS = [
    'simpleui',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # --- 第三方库 ---
    'rest_framework',
    'corsheaders',
    # --- 我们的核心应用 ---
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware', # 跨域支持
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'corezen_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'corezen_backend.wsgi.application'

# --- 核心：连接 PostgreSQL 数据库 ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        # 🟢 优先读取环境变量，读不到则使用默认值
        'NAME': os.environ.get('DB_NAME', 'zenerp'),
        'USER': os.environ.get('DB_USER', 'zenerp_admin'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'zenerp_secure_password'),
        'HOST': os.environ.get('DB_HOST', '172.19.0.2'), # 注意这里对应 docker-compose 里的服务名
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'zh-hans' # 中文界面
TIME_ZONE = 'Asia/Shanghai' # 中国时间
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# 🟢 新增这一行（这就是报错说缺少的 STATIC_ROOT）
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# --- 自定义用户模型 ---
AUTH_USER_MODEL = 'core.CustomUser'

# --- 图片存储路径 (映射到腾讯云硬盘) ---
MEDIA_URL = '/uploads/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'uploads')
# --- SimpleUI 个性化配置 (品牌统一为 ZenERP) ---
SIMPLEUI_HOME_INFO = False  
SIMPLEUI_ANALYSIS = False
SIMPLEUI_DEFAULT_ICON = False

# 🟢 1. 修改左侧菜单顶部的 Logo/文字
SIMPLEUI_LOGO = 'ZenERP'   # 保持与品牌名称一致
SIMPLEUI_HOME_TITLE = 'ZenERP 工作台'
SIMPLEUI_DEFAULT_THEME = 'admin.lte.css'

# 🟢 2. 左侧菜单增加“返回工作台”
SIMPLEUI_CONFIG = {
    'system_keep': True,
    'dynamic_menus': [{
        'name': '🔙 返回工作台',
        'url': '/',
        'icon': 'fa fa-home'
    }]
}