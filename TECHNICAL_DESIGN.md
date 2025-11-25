# OP后台运营管理系统 - 技术设计方案

## 1. 系统概述

### 1.1 项目背景
- 用户规模: ~20,000 APP用户
- 核心功能: 用户管理、Meme代币审核、Post内容管理、客服支持
- 技术栈: FastAPI + PostgreSQL (已有数据库) + OpenIM
- **注意**: 数据库表已存在，后端需适配现有schema

### 1.2 系统架构

```
┌─────────────────┐
│  React Frontend │
│   (Admin UI)    │
└────────┬────────┘
         │ HTTP/WebSocket
         ↓
┌─────────────────┐
│   FastAPI       │
│   Backend       │
│   (OP Admin)    │
└────┬────────┬───┘
     │        │
     ↓        ↓
┌─────────┐ ┌────────┐
│PostgreSQL│ │OpenIM  │
│(Existing)│ │ SDK    │
└──────────┘ └────────┘
```

## 2. 现有数据库表结构

### 2.1 核心表结构（已存在）

#### users (用户认证表)
```sql
CREATE TABLE users (
  id VARCHAR PRIMARY KEY,                    -- UUID格式
  email VARCHAR(320),                        -- 邮箱（唯一）
  hashed_password VARCHAR(1024) NOT NULL,    -- 密码哈希
  phone_number VARCHAR,                      -- 手机号（唯一）
  is_active BOOL NOT NULL,                   -- 是否激活
  is_superuser BOOL NOT NULL,                -- 是否超级用户
  is_verified BOOL NOT NULL,                 -- 是否验证
  is_virtual BOOL,                           -- 是否虚拟用户
  status VARCHAR NOT NULL,                   -- 用户状态
  region VARCHAR,                            -- 地区
  preferred_languages VARCHAR[],             -- 首选语言
  google_id VARCHAR,                         -- Google账号ID（唯一）
  apple_id VARCHAR,                          -- Apple账号ID（唯一）
  avatar_url VARCHAR,                        -- 头像URL
  google_linked_at TIMESTAMP,                -- Google关联时间
  apple_linked_at TIMESTAMP,                 -- Apple关联时间
  email_verified_via VARCHAR,                -- 邮箱验证方式
  last_login_at TIMESTAMP,                   -- 最后登录时间
  last_login_method VARCHAR,                 -- 最后登录方式
  created_at TIMESTAMP,                      -- 创建时间
  updated_at TIMESTAMP                       -- 更新时间
);
```

#### authors (作者/创作者表)
```sql
CREATE TABLE authors (
  id VARCHAR PRIMARY KEY,                    -- UUID格式
  user_id VARCHAR NOT NULL,                  -- 关联users.id
  username VARCHAR(255) NOT NULL UNIQUE,     -- 用户名（唯一）
  username_raw CITEXT NOT NULL UNIQUE,       -- 原始用户名（不区分大小写）
  name VARCHAR(255) NOT NULL,                -- 显示名称
  avatar VARCHAR(255),                       -- 头像URL
  original_avatar VARCHAR(255),              -- 原始头像
  dedication VARCHAR(255),                   -- 个人签名
  description VARCHAR(300),                  -- 个人简介
  location VARCHAR(255),                     -- 位置
  country VARCHAR(255),                      -- 国家
  language VARCHAR(255),                     -- 语言
  education VARCHAR(255),                    -- 教育
  email VARCHAR(255),                        -- 邮箱
  phone_number VARCHAR(255),                 -- 电话
  birthday DATE,                             -- 生日
  gender VARCHAR,                            -- 性别
  region VARCHAR NOT NULL,                   -- 地区
  likes_count INT NOT NULL,                  -- 点赞数
  citations_count INT NOT NULL DEFAULT 0,    -- 引用数
  posts_count INT NOT NULL DEFAULT 0,        -- 帖子数
  pins VARCHAR[] NOT NULL DEFAULT '{}',      -- 置顶帖子ID列表
  invitation_id VARCHAR,                     -- 邀请ID
  invitation_id_owned VARCHAR(50),           -- 拥有的邀请ID
  group_size INT NOT NULL DEFAULT 0,         -- 群组大小
  group_grade INT NOT NULL DEFAULT 0,        -- 群组等级
  direct_invited_count INT NOT NULL DEFAULT 0, -- 直接邀请数
  vip_code VARCHAR(20),                      -- VIP码
  created_at TIMESTAMP,                      -- 创建时间
  updated_at TIMESTAMP,                      -- 更新时间
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### user_ban_records (用户封禁记录表)
```sql
CREATE TABLE user_ban_records (
    id BIGSERIAL PRIMARY KEY,
    uid BIGINT NOT NULL REFERENCES users(uid),
    operator_id BIGINT NOT NULL REFERENCES users(uid),
    ban_reason TEXT NOT NULL,
    ban_method VARCHAR(20) NOT NULL, -- account, device
    ban_duration_type VARCHAR(20) NOT NULL, -- permanent, custom
    ban_duration_value INTEGER, -- 小时数，permanent时为NULL
    ban_start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ban_end_time TIMESTAMP,
    is_notify BOOLEAN DEFAULT false,
    notify_message TEXT,
    status VARCHAR(20) DEFAULT 'active', -- active, expired, unbanned
    unban_time TIMESTAMP,
    unban_operator_id BIGINT REFERENCES users(uid),
    unban_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ban_records_uid ON user_ban_records(uid);
CREATE INDEX idx_ban_records_status ON user_ban_records(status);
CREATE INDEX idx_ban_records_operator ON user_ban_records(operator_id);
```

#### device_ban_records (设备封禁记录表)
```sql
CREATE TABLE device_ban_records (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL,
    operator_id BIGINT NOT NULL REFERENCES users(uid),
    ban_reason TEXT NOT NULL,
    ban_duration_type VARCHAR(20) NOT NULL,
    ban_duration_value INTEGER,
    ban_start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ban_end_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_device_ban_device_id ON device_ban_records(device_id);
CREATE INDEX idx_device_ban_status ON device_ban_records(status);
```

#### memes (Meme表)
```sql
CREATE TABLE memes (
    id BIGSERIAL PRIMARY KEY,
    meme_code VARCHAR(50) UNIQUE NOT NULL,
    meme_name VARCHAR(255) NOT NULL,
    meme_description TEXT,
    cover_image_url VARCHAR(500),
    creator_uid BIGINT NOT NULL REFERENCES users(uid),
    creator_username VARCHAR(50),
    chat_amount DECIMAL(20, 2) DEFAULT 0, -- LHDB代币数量
    cion_amount DECIMAL(20, 2) DEFAULT 0, -- USD价值
    url VARCHAR(500),
    status VARCHAR(20) DEFAULT 'pending', -- pending, approved, rejected
    review_operator_id BIGINT REFERENCES users(uid),
    review_time TIMESTAMP,
    review_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_memes_creator ON memes(creator_uid);
CREATE INDEX idx_memes_status ON memes(status);
CREATE INDEX idx_memes_code ON memes(meme_code);
```

#### meme_review_records (Meme审核记录表)
```sql
CREATE TABLE meme_review_records (
    id BIGSERIAL PRIMARY KEY,
    meme_id BIGINT NOT NULL REFERENCES memes(id),
    operator_id BIGINT NOT NULL REFERENCES users(uid),
    action VARCHAR(20) NOT NULL, -- approve, reject
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_review_records_meme ON meme_review_records(meme_id);
CREATE INDEX idx_review_records_operator ON meme_review_records(operator_id);
```

#### posts (帖子表)
```sql
CREATE TABLE posts (
    id BIGSERIAL PRIMARY KEY,
    post_url VARCHAR(500) UNIQUE NOT NULL,
    meme_id BIGINT REFERENCES memes(id),
    creator_uid BIGINT REFERENCES users(uid),
    content TEXT,
    weight INTEGER DEFAULT 0, -- 权重值，用于排序
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_posts_meme ON posts(meme_id);
CREATE INDEX idx_posts_weight ON posts(weight);
CREATE INDEX idx_posts_status ON posts(status);
```

#### post_weight_records (帖子权重调整记录表)
```sql
CREATE TABLE post_weight_records (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES posts(id),
    operator_id BIGINT NOT NULL REFERENCES users(uid),
    old_weight INTEGER,
    new_weight INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_weight_records_post ON post_weight_records(post_id);
```

#### support_conversations (客服会话表)
```sql
CREATE TABLE support_conversations (
    id BIGSERIAL PRIMARY KEY,
    conversation_id VARCHAR(100) UNIQUE NOT NULL, -- OpenIM会话ID
    user_uid BIGINT NOT NULL REFERENCES users(uid),
    user_username VARCHAR(50),
    user_displayname VARCHAR(100),
    user_wallet_address VARCHAR(255),
    app_version VARCHAR(20),
    status VARCHAR(20) DEFAULT 'pending', -- pending, processing, processed, closed
    assigned_operator_id BIGINT REFERENCES users(uid),
    assigned_at TIMESTAMP,
    last_message_content TEXT,
    last_message_time TIMESTAMP,
    unread_count INTEGER DEFAULT 0,
    has_new_message BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_conversations_user ON support_conversations(user_uid);
CREATE INDEX idx_conversations_status ON support_conversations(status);
CREATE INDEX idx_conversations_operator ON support_conversations(assigned_operator_id);
CREATE INDEX idx_conversations_updated ON support_conversations(updated_at DESC);
```

#### support_messages (客服消息表)
```sql
CREATE TABLE support_messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id VARCHAR(100) NOT NULL,
    message_id VARCHAR(100) UNIQUE NOT NULL, -- OpenIM消息ID
    sender_uid BIGINT NOT NULL,
    sender_type VARCHAR(20) NOT NULL, -- user, operator
    content_type VARCHAR(20) DEFAULT 'text', -- text, image, file
    content TEXT NOT NULL,
    is_read BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_conversation ON support_messages(conversation_id);
CREATE INDEX idx_messages_created ON support_messages(created_at DESC);
```

#### quick_replies (快捷回复模板表)
```sql
CREATE TABLE quick_replies (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES users(uid),
    title VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    usage_count INTEGER DEFAULT 0,
    is_shared BOOLEAN DEFAULT false, -- 是否共享给其他运营
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quick_replies_operator ON quick_replies(operator_id);
CREATE INDEX idx_quick_replies_shared ON quick_replies(is_shared);
```

#### operator_audit_logs (运营操作审计日志表)
```sql
CREATE TABLE operator_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES users(uid),
    action_type VARCHAR(50) NOT NULL, -- ban_user, unban_user, approve_meme, reject_meme, etc.
    target_type VARCHAR(50), -- user, meme, post, conversation
    target_id BIGINT,
    action_details JSONB, -- 详细操作信息
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_operator ON operator_audit_logs(operator_id);
CREATE INDEX idx_audit_logs_action ON operator_audit_logs(action_type);
CREATE INDEX idx_audit_logs_created ON operator_audit_logs(created_at DESC);
```

## 3. API设计

### 3.1 User模块

#### 用户列表
```
GET /api/v1/users
Query Params:
  - uid: string (可选)
  - username: string (可选)
  - displayname: string (可选)
  - email: string (可选)
  - wallet_address: string (可选)
  - tel: string (可选)
  - status: string (可选: all, active, banned)
  - page: int (默认1)
  - page_size: int (默认10, 最大100)
  - sort_by: string (默认created_at)
  - sort_order: string (desc/asc)

Response:
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [...],
    "total": 6532,
    "page": 1,
    "page_size": 10
  }
}
```

#### 用户详情
```
GET /api/v1/users/{uid}

Response:
{
  "code": 0,
  "data": {
    "uid": 123456,
    "username": "lulu",
    "displayname": "lele123",
    "email": "135463@126.com",
    "tel": "+4.4562315",
    "wallet_address": "0xH4H6G4G53JHG64GH35G",
    "device_id": "ios_device_123",
    "device_type": "iOS",
    "app_version": "1.2.6",
    "registration_time": "2025/09/01 12:03:00",
    "bio": "User bio...",
    "role": "Super Admin",
    "status": "active",
    "ban_records": [...]
  }
}
```

#### 封禁用户
```
POST /api/v1/users/{uid}/ban

Request Body:
{
  "ban_reason": "违规行为",
  "ban_method": "account", // account or device
  "ban_duration_type": "custom", // permanent or custom
  "ban_duration_value": 24, // 小时数
  "is_notify": true,
  "notify_message": "您因违规已被封禁24小时"
}

Response:
{
  "code": 0,
  "message": "User banned successfully"
}
```

#### 解封用户
```
POST /api/v1/users/{uid}/unban

Request Body:
{
  "unban_reason": "申诉通过"
}

Response:
{
  "code": 0,
  "message": "User unbanned successfully"
}
```

#### 更新用户信息
```
PUT /api/v1/users/{uid}

Request Body:
{
  "displayname": "new name",
  "bio": "new bio",
  ...
}
```

### 3.2 Operation模块

#### Meme审核列表
```
GET /api/v1/operations/memes/review
Query Params:
  - username: string
  - meme_code: string
  - meme_name: string
  - status: string (pending, approved, rejected)
  - page: int
  - page_size: int

Response:
{
  "code": 0,
  "data": {
    "items": [...],
    "total": 6532
  }
}
```

#### 审核Meme
```
POST /api/v1/operations/memes/{meme_id}/review

Request Body:
{
  "action": "approve", // approve or reject
  "comment": "审核通过"
}

Response:
{
  "code": 0,
  "message": "Meme reviewed successfully"
}
```

#### Post列表
```
GET /api/v1/operations/posts
Query Params:
  - meme_id: int
  - sort_by: weight/created_at
  - page: int
  - page_size: int
```

#### 创建Post
```
POST /api/v1/operations/posts

Request Body:
{
  "post_url": "https://example.com/post/123",
  "meme_id": 456,
  "weight": 10
}

Response:
{
  "code": 0,
  "message": "Post created successfully",
  "data": {
    "id": 789,
    ...
  }
}
```

#### 更新Post权重
```
PUT /api/v1/operations/posts/{post_id}/weight

Request Body:
{
  "weight": 20,
  "reason": "提升热度"
}
```

### 3.3 Support模块

#### 会话列表
```
GET /api/v1/support/conversations
Query Params:
  - status: pending/processing/processed
  - uid: string
  - username: string
  - displayname: string
  - wallet_address: string
  - page: int
  - page_size: int

Response:
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": 1,
        "conversation_id": "c123",
        "user_uid": 415654,
        "user_username": "nnananyu",
        "user_displayname": "雪雪",
        "last_message_content": "texttexttexttextex",
        "last_message_time": "2025/09/26 12:20:03",
        "status": "pending",
        "unread_count": 3,
        "has_new_message": true
      }
    ],
    "total": 6532
  }
}
```

#### 获取会话详情
```
GET /api/v1/support/conversations/{conversation_id}

Response:
{
  "code": 0,
  "data": {
    "conversation": {...},
    "messages": [...]
  }
}
```

#### 分配会话（打开会话）
```
POST /api/v1/support/conversations/{conversation_id}/assign

Response:
{
  "code": 0,
  "message": "Conversation assigned successfully"
}
```

#### 释放会话（稍后处理）
```
POST /api/v1/support/conversations/{conversation_id}/release

Response:
{
  "code": 0,
  "message": "Conversation released"
}
```

#### 关闭会话
```
POST /api/v1/support/conversations/{conversation_id}/close

Response:
{
  "code": 0,
  "message": "Conversation closed"
}
```

#### 发送消息
```
POST /api/v1/support/conversations/{conversation_id}/messages

Request Body:
{
  "content": "消息内容",
  "content_type": "text"
}

Response:
{
  "code": 0,
  "data": {
    "message_id": "msg123",
    ...
  }
}
```

#### WebSocket连接（实时消息）
```
WS /api/v1/support/ws

Client -> Server:
{
  "type": "subscribe",
  "conversation_id": "c123"
}

Server -> Client:
{
  "type": "new_message",
  "data": {
    "conversation_id": "c123",
    "message": {...}
  }
}
```

#### 快捷回复管理
```
GET /api/v1/support/quick-replies
POST /api/v1/support/quick-replies
PUT /api/v1/support/quick-replies/{id}
DELETE /api/v1/support/quick-replies/{id}
```

## 4. 技术实现要点

### 4.1 后端架构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI应用入口
│   ├── config.py               # 配置管理
│   ├── database.py             # 数据库连接
│   ├── dependencies.py         # 依赖注入
│   ├── models/                 # SQLAlchemy模型
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── meme.py
│   │   ├── post.py
│   │   ├── support.py
│   │   └── audit.py
│   ├── schemas/                # Pydantic模型
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── meme.py
│   │   ├── post.py
│   │   └── support.py
│   ├── api/                    # API路由
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── users.py
│   │   │   ├── operations.py
│   │   │   ├── support.py
│   │   │   └── auth.py
│   ├── services/               # 业务逻辑
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── meme_service.py
│   │   ├── post_service.py
│   │   ├── support_service.py
│   │   ├── openim_service.py
│   │   └── audit_service.py
│   ├── utils/                  # 工具函数
│   │   ├── __init__.py
│   │   ├── pagination.py
│   │   ├── validators.py
│   │   └── security.py
│   └── middleware/             # 中间件
│       ├── __init__.py
│       ├── auth.py
│       └── audit.py
├── alembic/                    # 数据库迁移
│   ├── versions/
│   └── env.py
├── tests/                      # 测试
├── requirements.txt
├── alembic.ini
└── .env.example
```

### 4.2 核心技术实现

#### 4.2.1 用户封禁逻辑
```python
# 账号级别封禁
- 更新users表status为'banned'
- 创建user_ban_records记录
- 如果选择通知，通过OpenIM发送消息
- 记录审计日志

# 设备级别封禁
- 创建device_ban_records记录
- 查询该设备关联的所有账号，全部封禁
- 后续登录时检查设备ID是否被封禁
```

#### 4.2.2 Meme审核流程
```python
# 审核通过
1. 更新meme状态为'approved'
2. 记录审核信息（operator_id, review_time）
3. 创建meme_review_records
4. 通过OpenIM通知用户审核通过
5. 记录审计日志

# 审核拒绝
1. 更新meme状态为'rejected'
2. 记录拒绝原因
3. 通知用户（可选）
```

#### 4.2.3 客服会话管理
```python
# 会话锁定机制
- 使用Redis实现分布式锁
- operator打开会话时，设置lock: conversation:{id} = operator_id
- 其他operator尝试打开时检查锁状态
- 会话关闭或释放时删除锁

# 实时消息推送
- WebSocket连接管理
- 新消息触发事件，推送给订阅的operator
- 更新会话的has_new_message标志
```

#### 4.2.4 OpenIM集成
```python
# 功能
1. 用户封禁/解封通知
2. Meme审核结果通知
3. 客服会话消息收发
4. 在线状态管理

# 实现方式
- 使用OpenIM Python SDK
- 封装OpenIMService服务类
- 异步发送消息（避免阻塞主流程）
```

### 4.3 前端架构（建议）

```
frontend/
├── src/
│   ├── components/
│   │   ├── Layout/
│   │   ├── UserManagement/
│   │   ├── Operations/
│   │   └── Support/
│   ├── pages/
│   │   ├── Users/
│   │   ├── MemeReview/
│   │   ├── PostManagement/
│   │   └── Support/
│   ├── services/
│   │   ├── api.ts
│   │   ├── userService.ts
│   │   ├── operationService.ts
│   │   └── supportService.ts
│   ├── hooks/
│   │   ├── useWebSocket.ts
│   │   └── useAuth.ts
│   ├── store/
│   │   └── redux slices
│   └── App.tsx
├── package.json
└── tsconfig.json

推荐技术栈:
- React 18
- TypeScript
- Ant Design (UI组件库)
- React Router
- Redux Toolkit
- React Query
- WebSocket Client
```

## 5. 性能优化

### 5.1 数据库优化
- 合理索引设计（已在表结构中体现）
- 分页查询优化
- 使用数据库连接池
- 定期清理过期数据

### 5.2 缓存策略
```
Redis缓存:
- 用户信息缓存（TTL: 5分钟）
- 会话锁（分布式锁）
- 会话状态缓存
- 快捷回复缓存
```

### 5.3 API优化
- 使用async/await异步处理
- 批量操作API
- 响应数据压缩
- 接口限流

## 6. 安全性

### 6.1 认证授权
```python
- JWT Token认证
- 基于角色的权限控制（RBAC）
- 运营人员角色: Super Admin, Admin, Support
- 所有操作需要审计日志
```

### 6.2 数据安全
- SQL注入防护（使用ORM）
- XSS防护
- CSRF防护
- 敏感数据加密
- 操作审计日志

## 7. 部署方案

### 7.1 开发环境
```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

### 7.2 生产环境（Docker）
```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:15
    ...
  redis:
    image: redis:7
    ...
  backend:
    build: ./backend
    ...
  frontend:
    build: ./frontend
    ...
  nginx:
    image: nginx:alpine
    ...
```

## 8. 监控告警

### 8.1 系统监控
- API响应时间监控
- 数据库性能监控
- WebSocket连接数监控
- 错误日志告警

### 8.2 业务监控
- 待审核Meme数量
- 待处理客服会话数
- 封禁用户数量
- 运营人员操作统计

## 9. 开发计划

### Phase 1 (Week 1-2): 基础架构
- 数据库设计与迁移
- FastAPI项目搭建
- 基础认证授权
- OpenIM集成

### Phase 2 (Week 3-4): User模块
- 用户列表与搜索
- 用户详情
- 封禁/解封功能
- 审计日志

### Phase 3 (Week 5-6): Operation模块
- Meme审核功能
- Post管理功能
- 权重调整

### Phase 4 (Week 7-8): Support模块
- 会话列表
- 实时聊天（WebSocket）
- 快捷回复
- 会话分配机制

### Phase 5 (Week 9-10): 前端开发与联调
- React前端开发
- 前后端联调
- 测试与优化

## 10. 技术栈版本

```
Backend:
- Python 3.11+
- FastAPI 0.104+
- SQLAlchemy 2.0+
- Alembic 1.12+
- asyncpg 0.29+
- redis 5.0+
- pydantic 2.0+
- python-jose[cryptography]
- passlib[bcrypt]
- openim-sdk-python (latest)

Frontend:
- React 18
- TypeScript 5
- Ant Design 5
- React Router 6
- Redux Toolkit 2
- React Query 5

Infrastructure:
- PostgreSQL 15
- Redis 7
- Nginx 1.25
- Docker & Docker Compose
```

## 11. 注意事项

1. OpenIM集成需要提前配置好OpenIM服务器地址和密钥
2. 用户封禁需要同步到APP端，确保APP检查封禁状态
3. 客服会话锁定机制需要处理异常情况（operator断线等）
4. 所有敏感操作必须记录审计日志
5. 定期备份数据库
6. 设置合理的API限流策略
7. Post URL需要实现验证规则
8. WebSocket连接需要心跳检测机制
9. 大量数据导出需要异步处理
10. 考虑国际化支持（i18n）
