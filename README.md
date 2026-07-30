# CampusMatch · 校园志趣恋爱交友平台

CampusMatch 是一个面向高校学生的 Web 端异性交友平台。当前匹配流程采用“每日一对一互配”模式：用户完善资料并主动进入匹配池，系统在北京时间每天中午 12:00 为符合条件的用户生成唯一、互为对方的一组配对。

## 核心流程

```text
注册/登录
  → 完善昵称、头像、学校、年级、性别、兴趣（专业/院系选填）
  →（可选）完成 26 道恋爱价值观问卷，自动获得深度匹配资格
  → 手动开启匹配
  → 每日 12:00 两阶段筛选并一对一互配
  → 双方分别选择是否心动
  → 双向心动后开放聊天
  → 从第一条消息起连续聊天满 7 天
  → 自动解锁联系方式和真实照片
```

规则说明：

- 资料不完整时不能开启匹配，前端会提示“请先完善个人资料”。
- 关闭匹配后不会参与新的匹配，也不会被推荐给其他人。
- 每人每天最多获得一个结果，A 匹配到 B 时，B 的结果也一定是 A。
- 匹配后双方首先只能看到昵称、头像、学校、年级、专业/院系（如有填写）、性别和兴趣等基础信息。
- 双方都点击“心动”后才开放聊天。
- 待心动状态 7 天内未完成双向心动，配对自动解除。
- 聊天开启后，任一方连续 3 天未发送消息，配对自动解除。
- 双向心动且从第一条消息起连续聊天满 7 天后，自动解锁手机号、邮箱、微信号和真实照片。
- 配对解除后双方的匹配开关保持关闭，需要自行决定是否重新开启。
- 问卷为自愿填写；未完成问卷的用户仍按初步分数正常参与匹配。
- 完成全部 26 题后自动进入深度匹配池，无需额外开启开关。

## 深度匹配算法

每日任务会循环选择得分最高的一对，保存后移除双方，继续处理剩余用户；每个用户当天最多只会出现在一组配对中。

1. 先对所有可用异性组合计算初步分数：细分兴趣与兴趣分类相似度占 60%，地域相似度占 30%，年龄相近度占 10%。地域分由当前所在地和家乡各占 50%；两项都按同省同市满分、同省不同市 60%、不同省 0 分计算。
2. 完整填写问卷的双方按初步分数排序，只取每轮 Top-N（默认 10）进入 Qwen 深度评分。
3. Qwen 接收全部题目、选项文字和双方答案，返回 `deep_score`（0～100）及 200 字以内的友善中文评语。
4. 深度候选的综合分为：`final_score = 0.4 × preliminary_score + 0.6 × deep_score`。
5. 每轮选择综合分最高的一对；未完成问卷或 Qwen 降级时，综合分等于初步分数。
6. 当剩余最高分低于阈值（默认 60）或只剩同一性别用户时停止。
7. 已有配对历史的同一用户对会降低本轮选择优先级：解除后 30 天内扣 30 个排序分、31～90 天扣 15 分、91～180 天扣 5 分，180 天后不再扣分。惩罚只用于候选排序，不修改用户看到的适配分，也不会在只剩旧对象时永久禁止再次配对。

Token 控制采用“每日全局调用上限”：默认最多调用 Qwen 10 次。评分按用户对缓存；达到上限后，尚未评估的组合使用初步分数继续匹配，不会让用户滞留在匹配池。Qwen 超时、返回无效 JSON、缺少依赖或没有配置密钥时也会自动降级为初步匹配。

## 已实现功能

- 唯一账号、手机号或邮箱登录；JWT access token + refresh token 自动续期
- bcrypt 密码哈希和密码强度校验
- 个人资料编辑、9 大分类约 90 个细分兴趣、关键词搜索、头像上传
- 最多 6 张真实照片和可选微信号，默认均作为隐私信息
- 具体标签 Jaccard 相似度为主、分类相似度为辅（兴趣合计 60%）+ 地域相似度（30%，当前所在地与家乡各占地域分50%）+ 年龄接近（10%）
- 26 道五维恋爱价值观问卷、分组进度、进度保存和完成状态
- LangChain `ChatPromptTemplate + ChatOpenAI + JsonOutputParser` 调用 DashScope OpenAI 兼容接口
- 决策前的 Top-N 初筛、Qwen 深度精排、40%/60% 加权和友善评语展示
- 每日定时一对一互配和持久化的任务执行记录
- 待心动、聊天中、隐私已解锁、已解除的完整配对状态机
- WebSocket 文字与 Emoji 聊天、在线状态、已读状态
- 配对、双向心动、隐私解锁、新消息和配对解除通知
- SMTP 配置存在时发送配对邮件
- Vue 3 响应式页面：登录注册、每日配对、聊天、资料与通知中心
- SQLite 开发环境、PostgreSQL Docker 环境和 Alembic 数据迁移
- 5 位男生 + 5 位女生演示数据

## 技术栈

- 后端：Python 3.11+、FastAPI、Pydantic、SQLAlchemy 2 async
- 数据库：SQLite/aiosqlite、PostgreSQL/asyncpg、Alembic
- 认证与通信：python-jose、passlib bcrypt、WebSocket、aiosmtplib
- 前端：Vue 3 Composition API、Vite、Pinia、Vue Router、Element Plus、Axios
- 调度：Python `asyncio` 后台任务，北京时间每天 12:00 匹配，每 10 分钟维护配对状态
- 大模型：LangChain + DashScope OpenAI 兼容接口（`qwen-max`/可配置模型）
- 部署：uv、Docker、Docker Compose、Nginx

## 从旧版本升级数据库

项目已有 `campusmatch.db` 时，请先停止后端并备份数据库，然后运行迁移：

```powershell
Copy-Item campusmatch.db campusmatch.db.backup
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run alembic upgrade head
```

迁移脚本为：

```text
backend/migrations/versions/20260729_0002_daily_pairing.py
backend/migrations/versions/20260729_0003_interest_taxonomy.py
backend/migrations/versions/20260729_0004_match_interest_names.py
backend/migrations/versions/20260729_0005_deep_matching.py
backend/migrations/versions/20260730_0006_user_location.py
backend/migrations/versions/20260730_0007_user_hometown.py
backend/migrations/versions/20260730_0008_user_blocks.py
backend/migrations/versions/20260730_0009_user_school.py
backend/migrations/versions/20260730_0010_account_rename.py
```

迁移会保留原用户、配对和聊天记录；`0005` 新增问卷与深度匹配字段，`0006` 新增用户当前所在地，`0007` 新增用户家乡省市字段，`0008` 新增持久化用户屏蔽关系，`0009` 新增必填学校并将专业/院系调整为选填，`0010` 将原“学号”字段完整更名为全平台唯一的“账号”。本工作区在深度匹配迁移前的备份为 `campusmatch.db.pre-deep-matching.bak`。

升级到 `0009` 后，非演示账号需要在个人资料中补充学校；专业/院系可以留空。学校、所在地和家乡等必填资料完整后才能重新开启每日匹配。

## 本地启动

### 后端

```powershell
cd D:\study\CampusMatch
Copy-Item .env.example .env -ErrorAction SilentlyContinue
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv sync
uv run alembic upgrade head
uv run uvicorn backend.app.main:app --reload
```

- API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)
- 健康检查：[http://localhost:8000/health](http://localhost:8000/health)

首次使用空数据库时会自动创建表，并根据 `SEED_DEMO_DATA` 写入演示数据。

### 配置 Qwen 深度匹配

在项目根目录的 `.env` 中填写 DashScope 密钥：

```env
DASHSCOPE_API_KEY=你的_DashScope_API_Key
DASHSCOPE_MODEL=qwen-max
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DEEP_MATCH_CANDIDATE_POOL_SIZE=10
DEEP_MATCH_MAX_DAILY_CALLS=10
DEEP_MATCH_MIN_FINAL_SCORE=60
DEEP_MATCH_PRELIMINARY_WEIGHT=0.4
DEEP_MATCH_MODEL_WEIGHT=0.6
DEEP_MATCH_TIMEOUT_SECONDS=45
REPEAT_MATCH_RECENT_WINDOW_DAYS=30
REPEAT_MATCH_RECENT_PENALTY=30
REPEAT_MATCH_MEDIUM_WINDOW_DAYS=90
REPEAT_MATCH_MEDIUM_PENALTY=15
REPEAT_MATCH_LONG_WINDOW_DAYS=180
REPEAT_MATCH_LONG_PENALTY=5
```

修改 Python 依赖后请执行 `uv sync`。若 `DASHSCOPE_API_KEY` 留空，后端仍可正常启动，问卷也可填写，但每日匹配会安全降级为初步分数。

### 前端

另开一个 PowerShell：

```powershell
cd D:\study\CampusMatch\frontend
npm install
npm run dev
```

打开：[http://localhost:5173](http://localhost:5173)

## 演示账号

所有演示账号密码均为 `Campus123`。

| 性别 | 账号 | 昵称 | 学校 | 专业/院系 |
|---|---|---|---|---|
| 女 | 20260001 | 林夏 | CampusMatch示范大学 | 计算机学院 |
| 女 | 20260002 | 小糖 | CampusMatch示范大学 | 外国语学院 |
| 女 | 20260003 | 沫沫 | CampusMatch示范大学 | 艺术学院 |
| 女 | 20260004 | 予舟 | CampusMatch示范大学 | 新闻学院 |
| 女 | 20260005 | 薄荷 | CampusMatch示范大学 | 生命科学学院 |
| 男 | 20260006 | 江屿 | CampusMatch示范大学 | 计算机学院 |
| 男 | 20260007 | 南风 | CampusMatch示范大学 | 建筑学院 |
| 男 | 20260008 | 星河 | CampusMatch示范大学 | 经济学院 |
| 男 | 20260009 | 阿哲 | CampusMatch示范大学 | 体育学院 |
| 男 | 20260010 | 栖木 | CampusMatch示范大学 | 音乐学院 |

`20260006` 带有 `is_superuser` 标志。开发测试时可以让两个无有效配对的异性账号分别开启匹配，然后使用该管理员账号在 Swagger 调用：

```text
POST /api/matching/run-now
```

该接口只用于开发和管理测试；正式匹配仍由每天中午 12:00 的任务触发。

## 主要 API

```text
GET   /api/matching/status                  当前匹配资格、开关和有效配对
PATCH /api/matching/settings                开启或关闭匹配
PATCH /api/matching/pairs/{id}/heart        保存心动选择
POST  /api/matching/run-now                 管理员手动触发匹配
GET   /api/questionnaire                    获取 26 道题、已有答案和进度
GET   /api/questionnaire/status             获取问卷完成状态
PUT   /api/questionnaire/answers            新增或更新用户问卷答案
GET   /api/matches                          已开放聊天的配对列表
GET   /api/matches/{id}/messages            聊天记录
POST  /api/matches/{id}/block               屏蔽配对对象并立即结束配对
GET   /api/blocks                            获取我的屏蔽列表
DELETE /api/blocks/{user_id}                 解除对指定用户的屏蔽
WS    /api/ws/chat/{id}?token=...           实时聊天
POST  /api/profile/real-photos              上传真实照片
DELETE /api/profile/real-photos?url=...      删除真实照片
```

旧版 `/api/recommendations` 和 `/api/swipes` 会返回 `410 Gone`，防止绕过新的每日互配流程。

## 聊天安全与屏蔽词维护

- 用户屏蔽配对对象后，本次配对立即结束，双方无法继续发送消息，也不会再次进入彼此的匹配候选组合。
- 解除屏蔽入口位于个人中心；解除后不会恢复已经结束的配对，但未来可以重新匹配。
- HTTP 和 WebSocket 消息均由后端执行敏感词检查，前端无法绕过。
- 当前拦截血腥暴力、色情不良、银行卡转账及常见诈骗风险内容。

屏蔽词目录：

```text
backend/app/data/blocked_words/
├── violence.txt   # 血腥暴力
├── sexual.txt     # 色情及不良内容
├── fraud.txt      # 银行卡、转账和诈骗风险
└── README.md      # 更新格式与注意事项
```

每行填写一个词或短语，保存后下一条消息即自动生效，不需要重启服务器。系统会忽略大小写、空格和常见标点，例如“转 账”和“转-账”都会命中“转账”。为避免误伤正常聊天，不建议添加“钱”“卡”“血”等单字。

## Docker Compose

```bash
docker compose up --build -d
```

- Web 前端：[http://localhost:8080](http://localhost:8080)
- 后端 API：[http://localhost:8000/docs](http://localhost:8000/docs)
- Compose 使用 PostgreSQL 17，并持久化数据库与上传照片

公网部署前必须：

- 设置强随机 `SECRET_KEY`
- 修改 PostgreSQL 密码
- 设置 `SEED_DEMO_DATA=false`
- 设置 `DASHSCOPE_API_KEY`（如需启用深度评分）
- 使用域名和 HTTPS
- 不将 PostgreSQL 5432 暴露到公网
- 建议隐藏后端 8000 端口，只允许前端 Nginx 通过 Docker 网络访问

## 测试与构建

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest

cd frontend
npm run build
```

## 主要目录

```text
CampusMatch/
├── backend/
│   ├── app/
│   │   ├── api/          # 认证、资料、每日配对、聊天、通知、WebSocket
│   │   ├── core/         # 数据库、JWT、依赖注入
│   │   ├── models/       # User、Match、MatchingRun 等模型
│   │   ├── schemas/      # Pydantic 请求与响应模型
│   │   ├── services/     # 配对算法、深度评分、问卷、聊天安全、状态维护、调度、邮件、种子
│   │   └── data/blocked_words/ # 可直接维护的聊天屏蔽词目录
│   ├── migrations/
│   ├── tests/
│   └── uploads/
├── frontend/src/
│   ├── components/
│   ├── views/
│   ├── stores/
│   └── api/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── uv.lock
```

## 运行边界

- 后台调度运行在当前 FastAPI 进程内，部署时应保持单个后端进程，避免多实例重复调度。多实例生产环境建议迁移到独立调度服务或带分布式锁的任务系统。
- WebSocket 在线状态也保存在当前后端进程内，多实例部署需使用 Redis Pub/Sub。
- 调度时区固定为中国标准时间 UTC+8，不依赖操作系统时区数据库。
- `matching_runs.run_date` 会记录每日任务，服务错过 12:00 后重新启动时会补执行当天任务。
- 旧版 `Like` 表暂时保留用于历史数据兼容，新流程不再写入该表。
- 未配置 SMTP 时邮件会跳过，但站内通知不受影响。
- 未配置 DashScope 密钥或 Qwen 调用失败时，系统使用初步分数完成当日匹配。
- 默认每天最多发起 10 次 Qwen 调用；可通过 `.env` 调整候选池、调用上限、权重、阈值与超时。
