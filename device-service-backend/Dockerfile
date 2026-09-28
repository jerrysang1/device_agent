# 使用官方 Python 轻量级镜像
FROM python:3.11-slim

WORKDIR /app

# 国内加速
RUN pip install uv -i https://mirrors.aliyun.com/pypi/simple/
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 先装依赖，利用层缓存
COPY requirements.txt ./
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 再复制业务代码
COPY . .

EXPOSE 18082

CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "18082"]
