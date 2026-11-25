# Filecode 📦

极简、安全、自托管的文件密码分享与托管服务。

前端采用现代极简卡片式响应式设计，后端基于 Python Flask + SQLite，配合 Caddy 实现自动化 HTTPS (443) 反向代理与证书管理。

---

## ✨ 核心特性

- **🎨 极简渐进式 UI**：
  - 首页默认展示已上传的文件列表（文件名、大小、上传时间、累计下载量、权限状态）。
  - 平时不展示繁琐的密码输入框，界面极致清爽；仅在选择或拖拽文件上传后，才平滑展开密码设置区。
  - 纯原生内联样式，零外部第三方 CDN 依赖，弱网秒开。

- **🔐 严谨的双重 6 位数字鉴权体系**：
  - **上传权限限制**：内置全局管理员密码（默认 `123456`，可通过环境变量自定义），必须验证管理员密码才能上传文件，防止未授权访客滥用磁盘。
  - **独立下载密码（选填）**：上传时可为每个文件单独设定 6 位纯数字下载密码。
    - **留空不填**：任何人获得链接直接一键下载（公开文件）。
    - **设置密码**：访客必须输入正确的 6 位密码方可下载文件。
  - **独立文件管理后台**：
    - 每个文件生成独立管理路径 `/f/<ID>/manage`。
    - 凭 6 位管理密码解锁权限，可查看详细统计、修改/清除下载密码或永久删除该文件。

- **🚀 生产级极速部署**：
  - 前端采用 **Caddy v2**：自动申请并续期 Let's Encrypt / ZeroSSL 权威 SSL 证书，HTTP 自动 308 跳转 HTTPS。
  - 单文件 SQLite 存储元数据，上传文件磁盘分块持久化。
  - 内置开机自启 systemd 守护配置。

---

## 🛠️ 技术栈

- **Web 框架**：Python 3 / Flask
- **反向代理 & TLS**：Caddy 2
- **数据库**：SQLite 3
- **前端**：HTML5, CSS3, Vanilla JavaScript (零框架依赖)
- **进程管理**：systemd

---

## 📂 目录结构

```text
Filecode/
├── app.py                     # 后端核心业务逻辑与 API 路由
├── Caddyfile                  # Caddy 反向代理与 HTTPS 配置
├── requirements.txt           # Python 依赖清单
├── templates/                 # 前端 HTML 模板
│   ├── layout.html            # 基础布局与自适应样式
│   ├── index.html             # 首页（文件列表 + 渐进式上传区域）
│   ├── download.html          # 文件下载专属页面（支持 6 位密码校验）
│   └── manage.html            # 文件管理页面（密码修改与删除）
├── systemd/                   # systemd 服务单元文件
│   ├── filehub-backend.service # Flask 后端守护服务
│   └── filehub-caddy.service   # Caddy 反向代理守护服务
└── uploads/                   # 上传文件存储目录 (.gitkeep)
```

---

## 🚀 快速上手部署

### 1. 克隆仓库与配置环境

```bash
git clone https://github.com/KxGitHub4/Filecode.git /opt/filehub
cd /opt/filehub

# 创建并激活 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 Caddy 域名

编辑 `Caddyfile`，将你的域名填入：

```caddy
your-domain.com {
    reverse_proxy 127.0.0.1:8123 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }
}

:80 {
    redir https://{host}{uri} permanent
}
```

### 3. 配置开机自启系统服务

将 `systemd/` 下的服务文件复制到系统目录并启动：

```bash
sudo cp systemd/filehub-backend.service /etc/systemd/system/
sudo cp systemd/filehub-caddy.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now filehub-backend
sudo systemctl enable --now filehub-caddy
```

---

## ⚙️ 环境变量配置（可选）

- `FILEHUB_ADMIN_PIN`：自定义全局管理员上传密码（默认值：`123456`，建议在生产环境中通过环境变量修改为自己的私密 6 位数字）。

---

## 📄 开源许可证

本项目采用 [MIT License](LICENSE) 开源协议。
