# 使用官方 Python 3.10 镜像 (比你服务器自带的 3.7 更新、更快、更安全)
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 优化 Python 输出 (实时打印日志，不缓存)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 安装系统级依赖 (PostgreSQL 驱动和图片处理需要这些)
RUN apt-get update && apt-get install -y     libpq-dev     gcc     && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
# 使用阿里云镜像源加速 pip 安装
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 8000
