# JobTracker · 求职投递管理系统

一个用 **Python + MySQL** 写的求职过程管理工具：把「投了哪家公司、简历发的是哪版、面试走到第几轮、最后有没有 Offer」这些散落在 Excel 和聊天记录里的信息，收进一个有登录、有权限隔离、有统计看板的 Web 应用。

> 不是为了做一个「能跑的 demo」，而是按真实项目的标准写的：分层架构、数据库约束、CSRF/越权/文件上传安全、159 个自动化测试、Alembic 版本管理、waitress 生产级启动。

**演示账号**：`demo` / `demo1234`（已预置 12 家企业、60 条投递、55 场面试的真实分布数据）

---

## 一、功能清单

| # | 需求 | 实现方式 | 关键位置 |
|---|------|---------|---------|
| 1 | 添加企业官网链接 | 企业库 CRUD；URL 自动补全 `https://`，拦截 `javascript:` / `data:` / `file:` 协议 | `app/utils/url.py` |
| 2 | 是否投递状态 | 6 种状态（已投递 / 已查看 / 面试中 / 已 Offer / 已拒绝 / 已放弃）+ 状态机校验，非法跳转直接拒绝 | `app/utils/constants.py` |
| 3 | 是否有面试 | 一场投递可挂多轮面试（一面 / 二面 / 三面 / HR 面 / 其他），记录时间、结果、反馈 | `app/services/interview_service.py` |
| 4 | 上传个人简历 | PDF / DOC / DOCX，扩展名白名单 + 文件头魔数 + 大小上限 + UUID 重命名 + 路径穿越防护，五层校验 | `app/services/resume_service.py` |
| 5 | 自定义编辑职位类型 | 用户自建分类（名称 + 颜色 + 排序），支持上移下移、停用；被引用时禁止删除，只允许停用 | `app/services/job_type_service.py` |
| 6 | 统计并可视化 | 6 张 ECharts 图表 + 11 项 KPI 指标 + 明细表 + CSV 导出 | `app/services/stats_service.py` |

**统计看板包含**：状态分布环形图、投递趋势折线图（按天/按周自动切粒度）、职位类型分布条形图、**四层转化漏斗**、渠道效果堆叠柱状图、面试轮次通过率；支持 7/30/90 天与自定义时间区间。

---

## 二、技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| Web 框架 | Flask 3.0 + Jinja2 | 服务端渲染，无需前端构建链，一个进程跑起来即可演示 |
| ORM | Flask-SQLAlchemy 3.1 + PyMySQL | 用 ORM 的同时保留原生 SQL 处理聚合统计 |
| 数据库 | MySQL 9.1（utf8mb4_unicode_ci） | 事务、外键、CHECK 约束、`SUM(CASE WHEN)` 聚合 |
| 认证 | Flask-Login + Werkzeug scrypt | 密码加盐哈希，不存明文 |
| 表单安全 | Flask-WTF | 全站 CSRF Token + 服务端校验 |
| 迁移 | Flask-Migrate (Alembic) | Schema 版本化，当前 `0001_baseline` |
| 前端 | Bootstrap 5 + Bootstrap Icons + 原生 JS | 无框架依赖，静态资源本地化（断网可用） |
| 可视化 | ECharts 5 | 六图联动，数据通过 `data-*` 属性传递 |
| 服务器 | waitress | Windows 友好的 WSGI 生产服务器 |
| 测试 | pytest + SQLite 内存库 | 单测跑在 SQLite 上，秒级反馈 |

---

## 三、六个值得写进简历的设计点

### 1. `max_stage` 单调阶段字段 —— 让漏斗不被终态毁掉

问题：投递状态是终态字段，一旦置为「已拒绝」，就丢失了「它曾经走到过二面」这个事实，漏斗会算错。

做法：加一个**只增不减**的 `max_stage`（1 投递 → 2 查看 → 3 面试 → 4 Offer），任何状态变更、任何面试新增都只往上推，从不回退。于是四层漏斗从 4 次查询变成 1 条 SQL：

```sql
SELECT SUM(CASE WHEN max_stage >= 1 THEN 1 ELSE 0 END) AS applied,
       SUM(CASE WHEN max_stage >= 2 THEN 1 ELSE 0 END) AS viewed,
       SUM(CASE WHEN max_stage >= 3 THEN 1 ELSE 0 END) AS interviewed,
       SUM(CASE WHEN max_stage >= 4 THEN 1 ELSE 0 END) AS offered
FROM applications WHERE user_id = :uid AND applied_at BETWEEN :start AND :end;
```

同时 `max_stage >= 2` 的首次达成时间会写入 `first_viewed_at`，`response_days`（企业几天后查看）在写库时算好，避免 `TIMESTAMPDIFF` 这类跨库方言差异。

### 2. `column_property + EXISTS` —— 把「是否有面试」变成可筛选的列

「有没有面试」本来是面试表的聚合结果，直接 `join + group by` 会让投递列表的分页 count 变复杂。用相关子查询把它下沉成模型上的派生列：

```python
has_interview = column_property(
    select(Interview.id)
    .where(Interview.application_id == id)
    .correlate_except(Interview)
    .exists()
)
```

之后 `Application.has_interview == True` 就是一个普通 WHERE 条件，筛选和排序都不用特殊处理。

### 3. 文件上传的五层校验

1. **扩展名白名单** —— `<input accept>` 只是用户体验，服务端必须再校验一次；
2. **文件头魔数** —— PDF `%PDF-`、DOCX `PK\x03\x04` 且包内含 `word/document.xml`、DOC `D0CF11E0`，防止把 `.exe` 改名成 `.pdf`；
3. **双端大小限制** —— `MAX_CONTENT_LENGTH` 拦住超大请求体 + 读取时分块累计再判断；
4. **UUID 重命名** —— 原名只存数据库（用于展示与下载），磁盘上用随机名 + 按用户分目录，杜绝同名覆盖与中文路径问题；
5. **路径穿越防护** —— 下载时 `Path.is_relative_to(upload_root)`，`../../windows/system32` 一律拒绝。

另外用 SHA-256 检测重复上传，落盘采用「先写 `.part` 再 `os.replace`」的原子改名，中途失败不会留下半个文件。

### 4. 越权一律返回 404，而不是 403

```python
statement = select(Application).where(Application.id == app_id, Application.user_id == current_user.id)
```

所有查询都强制带上 `user_id` 条件，别人的记录在你这儿「不存在」——403 会泄露「这个 id 确实有数据」，404 不会。每个业务模块都有专门的越权用例守着。

### 5. 统计查询不做 N+1

- 职位类型分布：一次 `outerjoin + group by`，把「没有投递的类型」也用 `LEFT JOIN` 补 0；
- 投递列表：`joinedload(company)` + `selectinload(interviews)`，固定 3 条 SQL，与列表长度无关；
- 有一条测试专门断言「查询次数不随数据量增长」。

### 6. 失败路径也是设计的一部分

- **时间区间非法**（`start > end`、超过 365 天）→ 回退默认 30 天，而不是 500；
- **时区**：Windows 上 `ZoneInfo` 可能找不到 IANA 库，装了 `tzdata` 并额外兜底固定 UTC+8；
- **CDN 不可达** → Bootstrap / ECharts / 图标字体全部本地 vendor，断网也能演示；
- **上传目录不可写** → `/healthz` 会返回 503 并指出是哪一项挂了。

---

## 四、目录结构

```
jobtracker/
├── app/
│   ├── __init__.py          # 应用工厂、模板过滤器、安全响应头、/healthz
│   ├── extensions.py        # db / login_manager / csrf / migrate 单例
│   ├── models/              # 6 个模型：user company job_type resume application interview
│   ├── services/            # 9 个服务模块：业务规则全在这里，路由层零业务逻辑
│   ├── blueprints/          # 8 个蓝图：auth main companies applications interviews resumes job_types stats
│   ├── forms/               # WTForms + 自定义校验器
│   ├── utils/               # 时区、URL 规范化、分页、异常、安全、常量
│   ├── templates/           # 24 个 Jinja2 模板
│   └── static/              # CSS / JS / ECharts 图表脚本 / 本地 vendor
├── migrations/              # Alembic 迁移（0001_baseline）
├── scripts/
│   ├── create_db.sql        # 建库 + 建专用账号（最小权限）
│   ├── check_env.py         # 环境自检：依赖 / 连接 / 字符集 / 表 / 上传目录 / 时区
│   ├── smoke.py             # 端到端冒烟：真实 HTTP + 真实 MySQL 跑一遍登录与全部页面
│   └── snapshot.py          # 导出登录后页面为静态 HTML，方便截图预览
├── tests/                   # 159 个用例，覆盖率 77%
├── config.py                # Dev / Prod / Test 三套配置
├── run.py / wsgi.py         # 开发入口 / waitress 入口
└── requirements.txt
```

**分层约定**：蓝图只做「取参数 → 调服务 → 渲染/重定向」，`services/` 承担全部业务规则与事务，`models/` 只描述结构和约束。所以换掉 Flask 换 FastAPI，服务层可以整层搬走。

---

## 五、快速开始

### 1. 环境要求

Python 3.10+、MySQL 8.0+

### 2. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
```

### 3. 建库与账号

用 root 执行 `scripts/create_db.sql`：创建 `jobtracker` 库（utf8mb4）、创建专用账号 `jt`，只授予 `jobtracker.*` 权限——应用账号拿不到别的库，也不用 root 跑业务。

```bash
mysql -u root -p < scripts/create_db.sql
```

### 4. 配置 `.env`

```bash
copy .env.example .env
```

至少改这三项：`SECRET_KEY`（随机串）、`DB_PASSWORD`、`UPLOAD_ROOT`（**纯 ASCII 绝对路径**，Windows 中文路径会导致 `send_file` 异常）。

### 5. 建表 + 造演示数据

```bash
flask --app wsgi init-db          # 建表（或 flask db upgrade）
flask --app wsgi seed-demo        # 12 家企业 / 60 条投递 / 55 场面试
```

### 6. 启动

```bash
python run.py                                     # 开发模式（debug + 自动重载）
python serve.py                                   # 生产模式（waitress，可 Ctrl+C 停止）
waitress-serve --port=5001 wsgi:app               # 生产模式（等价写法，命令行专用）
```

打开 http://127.0.0.1:5001 ，用 `demo` / `demo1234` 登录。

### 7. 在 PyCharm 里启停

项目已内置 3 个共享运行配置（`.idea/runConfigurations/`），打开项目后右上角下拉框可直接选：

| 运行配置 | 作用 |
|---|---|
| **JobTracker 开发服务器 (run.py)** | 开发模式，改代码自动重载 |
| **JobTracker 生产服务器 (waitress, serve.py)** | waitress 单进程，演示用 |
| **环境自检 (scripts/check_env.py)** | 依赖/数据库/上传目录逐项体检 |

点绿三角启动，点红方块停止，Run 面板里能看到实时日志和访问记录。
首次打开需指定一次解释器：`File → Settings → Project → Python Interpreter`，选 `.venv\Scripts\python.exe`。

---

## 六、常用命令

| 命令 | 作用 |
|------|------|
| `python run.py` | 开发服务器（debug + 自动重载） |
| `python serve.py` | 生产服务器（waitress） |
| `python scripts/check_env.py` | 环境自检，逐项告诉你哪里没配好 |
| `python scripts/smoke.py` | 端到端冒烟（需先启动服务）：登录、CSRF、15 个页面、越权 404 |
| `pytest -q` | 跑全部测试 |
| `pytest --cov=app --cov-report=term-missing` | 覆盖率报告 |
| `flask --app wsgi init-db` | 建表 |
| `flask --app wsgi seed-demo --reset` | 清空并重建演示数据 |
| `flask --app wsgi db migrate -m "说明"` | 生成增量迁移脚本 |
| `flask --app wsgi db upgrade` | 应用迁移 |
| `python scripts/snapshot.py` | 导出页面静态快照到 `.preview/` |

---

## 七、测试与质量

```
159 passed，覆盖率 77%
```

覆盖范围不只是「页面返回 200」：

- **业务规则**：状态机非法跳转被拒、`max_stage` 只增不减、面试结果回写投递状态但不把 Offer 降级；
- **数据正确性**：用 3 条已知投递对账全部图表——`total=3 / viewed=2 / interviewed=2 / offered=1`、漏斗 `3→2→2→1`、`stepRate` 精确到小数点；
- **安全**：CSRF 缺失被拒、越权访问 404、路径穿越被拒、伪造扩展名被文件头校验拦下；
- **性能**：断言列表接口的 SQL 条数不随数据量增长（防 N+1 回归）；
- **边界**：空数据集返回 0 而不是报错、非法时间区间回退默认值、分页越界。

其中有 2 个用例是「为了让统计不出错」而写的：`test_funnel_is_monotonic`（漏斗必须单调递减）和 `test_channel_stacking_sums_to_total`（各渠道之和必须等于总数）——图表正确性是这类项目最容易糊弄、也最容易被面试官追问的地方。

---

## 八、已知限制

- 单用户单进程演示，未做多租户团队协作；
- 简历只做存储与下载，未做 PDF 内容解析（下一步可以接 `pdfplumber` 抽关键词，做「简历-JD 匹配度」）；
- 统计走实时聚合，未加缓存层；数据量到十万级时应引入按天预聚合表；
- 未接入邮件/日历提醒，面试提醒目前是看板上的「近 7 天待面试」列表。

## 九、安全清单

- [x] 密码 scrypt 加盐哈希，登录失败提示统一（防账号枚举）
- [x] 全站 CSRF Token（`WTF_CSRF_TIME_LIMIT=None`，随会话有效）
- [x] 所有查询强制带 `user_id`，越权返回 404
- [x] 登录后跳转只允许站内路径（防开放重定向）
- [x] 上传：白名单 + 魔数 + 大小 + UUID 重命名 + 路径穿越防护
- [x] 响应头 `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy`
- [x] 会话 Cookie `HttpOnly` + `SameSite=Lax`
- [x] 数据库账号最小权限，业务不使用 root
- [x] `.env` 与上传目录均在 `.gitignore` 中
