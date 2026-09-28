# device-service-backend（业务基座）部署文档

> 本文档记录将 `device-service-backend` 设备维修中台通过 Docker 容器部署到虚拟机的完整流程。部署完成后，本地的 `agent-gateway` / 前端可直接通过 IP + 端口调用中台接口。
>
> 虚拟机：Linux · **192.168.10.15**

---

## 1、部署架构概览

| 子项目 | 部署位置 | 说明 |
|--------|----------|------|
| `agent-gateway`（Agent 后端） | 本地开发 | 主要开发对象 |
| `device-service-frontend`（前端） | 本地开发 | — |
| `shopkeeper_brain`（手册 RAG） | 本地开发 | 可选，后续再容器化 |
| `device-service-backend` + MySQL | **虚拟机 Docker** | 稳定业务基座，打包部署 |

部署后，本地通过 `http://192.168.10.15:18082` 调用设备维修中台。

---

## 2、需要准备的文件（与课程包形式一致）

```text
deploy/                                  ← 本机打包目录
├── docker-compose.yml                   ← 编排文件
├── device-service-backend.zip           ← 中台源码包
└── mysql.zip                            ← 数据库初始化脚本包
```

虚拟机解压后目录结构：

```text
/root/web/
├── docker-compose.yml
├── device-service-backend/              ← 由 zip 解压
│   ├── app/
│   │   ├── api.py
│   │   ├── app.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── main.py
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .dockerignore
└── mysql/                               ← 由 zip 解压
    └── initdb/
        ├── 001_init_device_service.sql
        └── 002_init_customer_service.sql
```

### 2.1 docker-compose.yml（要点）

- `mysql` 挂载 `./mysql/initdb`，**第一次启动**自动执行 SQL。
- `app` 的 `build: ./device-service-backend`，容器内用服务名 `mysql` 访问数据库。
- 账密三处必须一致：`MYSQL_USER` / `MYSQL_PASSWORD` / `DATABASE_URL`。

### 2.2 为什么 compose 里没有 Agent 和前端？

| 角色 | 启动方式 | 原因 |
|------|----------|------|
| MySQL + 中台 (18082) | 虚拟机 `docker compose up` | 稳定基础设施，不常改 |
| Agent (8100) | 本地开发模式 | 每天要改，需要断点 |
| 前端 (5173) | 本地 `npm run dev` | 同上 |
| RAG (8001) | 本地 | 依赖 GPU/模型路径，暂不进 VM |

> **容器化的边界画在「不常改」的服务上。**

---

## 3、本地打包（步骤 1）

> ⚠️ 打包前排除 `.venv`、`__pycache__`、`.env`。

PowerShell 在 `atgui_agent` 下执行：

```powershell
cd /d F:\AAA求职相关\device_agent\atgui_agent

# 准备临时目录
$stage = "$env:TEMP\device-deploy-stage"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path "$stage\device-service-backend", "$stage\mysql\initdb" | Out-Null

# 拷贝中台代码（排除垃圾目录）
robocopy .\device-service-backend "$stage\device-service-backend" /E `
  /XD __pycache__ .venv .pytest_cache .mypy_cache /XF .env *.pyc

# 拷贝 SQL
Copy-Item .\mysql\initdb\*.sql "$stage\mysql\initdb\"

# 打 zip（课程同款：两个包）
Compress-Archive -Path "$stage\device-service-backend" -DestinationPath .\deploy\device-service-backend.zip -Force
Compress-Archive -Path "$stage\mysql" -DestinationPath .\deploy\mysql.zip -Force

# compose 已在 deploy\docker-compose.yml
Get-ChildItem .\deploy
```

---

## 4、上传到虚拟机（步骤 2）

用 SFTP（MobaXterm / Xftp / WinSCP / FileZilla）上传到：

```text
192.168.10.15:/root/web/
```

需要上传 **3 个文件**：

1. `device-service-backend.zip`
2. `mysql.zip`
3. `docker-compose.yml`

也可用 scp：

```powershell
cd F:\AAA求职相关\device_agent\atgui_agent\deploy
scp device-service-backend.zip mysql.zip docker-compose.yml root@192.168.10.15:/root/web/
```

---

## 5、登录虚拟机并解压（步骤 3）

```bash
ssh root@192.168.10.15
cd /root/web/

unzip device-service-backend.zip
unzip mysql.zip

# 确认结构
ls
# docker-compose.yml  device-service-backend  mysql
```

若解压后多一层目录，挪到与 `docker-compose.yml` 同级：

```bash
# 例如 zip 内是 device-service-backend/... 应已正确
# 若是 web/device-service-backend，则 mv 调整
```

---

## 6、构建并启动（步骤 4）

```bash
cd /root/web
docker compose up -d --build
```

| 部分 | 作用 |
|------|------|
| `docker compose` | 读取当前目录 `docker-compose.yml` |
| `up` | 创建并启动服务、网络、数据卷 |
| `-d` | 后台运行 |
| `--build` | 按 `Dockerfile` 重新构建镜像 |

---

## 7、验证部署（步骤 5）

**① 容器状态**

```bash
docker compose ps
```

应看到 `device-service-app` 与 `device-service-mysql` 均为 `Up`。

**② API 日志**

```bash
docker compose logs -f app
```

看到 `Uvicorn running on http://0.0.0.0:18082` 即成功（`Ctrl+C` 退出日志不影响服务）。

**③ 机内自测**

```bash
curl http://127.0.0.1:18082/health
curl http://127.0.0.1:18082/customers/u1001/devices
```

---

## 8、开放防火墙（步骤 6）

**CentOS/RHEL (firewalld)：**

```bash
sudo firewall-cmd --zone=public --add-port=18082/tcp --permanent
sudo firewall-cmd --zone=public --add-port=3306/tcp --permanent   # 可选，调试用
sudo firewall-cmd --reload
```

**Ubuntu (UFW)：**

```bash
sudo ufw allow 18082/tcp
sudo ufw allow 3306/tcp   # 可选
sudo ufw reload
```

---

## 9、本地访问验证（步骤 7）

浏览器打开：

```text
http://192.168.10.15:18082/docs
http://192.168.10.15:18082/customers/u1001/devices
```

能看到「设备维修中台 Device Service」Swagger 与设备 JSON 即部署成功。

---

## 10、修改本地项目配置

**前端** `device-service-frontend/vite.config.js`：

```js
'/device': {
  target: 'http://192.168.10.15:18082',
  changeOrigin: true,
  rewrite: (path) => path.replace(/^\/device/, ''),
},
```

**Agent**（`agent-gateway/.env`）：

```bash
DEVICE_SERVICE_BASE_URL=http://192.168.10.15:18082
```

改完重启前端 / Agent。

---

## 11、常用运维命令

| 命令 | 用途 |
|------|------|
| `docker compose ps` | 查看服务状态 |
| `docker compose logs -f app` | 中台日志 |
| `docker compose logs -f mysql` | 数据库日志 |
| `docker compose restart app` | 只重启中台 |
| `docker compose down` | 停止（保留数据） |
| `docker compose down -v` | 停止并清空数据库卷（重跑 SQL） |
| `docker compose up -d --build` | 改代码后重建 |
| `docker exec -it device-service-mysql mysql -uroot -pdevice123456` | 进数据库 |

---

## 12、常见问题

### 构建卡在 pip install

Dockerfile 已用阿里云源；仍慢可换清华源。

### API 连不上数据库

核对 compose 中 `MYSQL_*` 与 `DATABASE_URL` 的用户/密码/库名是否一致（均为 `device` / `Device.123` / `device_service`）。

### 改了 SQL 没生效

MySQL 只在数据卷为空时执行 `initdb`：

```bash
docker compose down -v
docker compose up -d --build
```

### 中台手动册是 stub

`RAG_BASE_URL` 指向 Windows 上的 shopkeeper_brain（默认 `http://10.0.2.2:8001`）。连不上不影响保修/工单。

---

## 13、部署后效果

- 本地不再启动 MySQL 与中台，节省资源。
- Agent / 前端通过 `http://192.168.10.15:18082` 访问业务基座。
- 中台由 Compose 统一管理，数据卷持久化。
- 中台代码变更：重新打包 zip 上传 → `docker compose up -d --build`。
