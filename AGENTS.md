# Repository Guidelines

## 项目结构与模块划分
- 主要代码位于`backend/`，其中`app/`按FastAPI惯例拆分：`api/v1/`存放路由，`models/`管理SQLAlchemy模型，`schemas/`承载Pydantic校验模型，`services/`封装业务逻辑与外部集成，`utils/`放置通用工具。
- 数据迁移由`alembic/`负责；若新增表结构，请同步更新`alembic`迁移脚本并参考`sql/op_admin_new_tables.sql`保持历史一致性。
- `backend/tests/`预留单元与集成测试目录，现有的手工脚本位于`backend/test_notification.py`，可作为异步服务测试示例。
- 根目录下`sq/`、`picture/`、`docker-compose.yml`等提供演示数据、流程图与本地依赖编排；如需联动Kafka、Redis，请优先使用根目录`docker-compose.yml`。

## 构建、测试与开发命令
```bash
cd backend
python3.11 -m venv venv && source venv/bin/activate  # 创建并激活虚拟环境
pip install -r requirements.txt                      # 安装运行时依赖
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000  # 本地热重载服务
pytest                                                # 运行全部Pytest用例
pytest --cov=app --cov-report=term-missing            # 获取核心模块覆盖率
python test_notification.py                           # 手工验证外部通知集成
```
- 需要本地依赖时执行`docker-compose up -d`启动Kafka、Redis等服务；停机使用`docker-compose down`。

## 编码风格与命名约定
- Python使用4空格缩进、类型注解和文档字符串；公共函数应返回模型或`Result`对象以保持API一致性。
- 模块与文件采用`snake_case`，Pydantic与SQLAlchemy模型使用`PascalCase`，环境变量保持`UPPER_SNAKE_CASE`。
- 建议在提交前运行可选的`black`、`flake8`、`mypy`（已在`requirements-dev.txt`中注释列出）以维持风格统一；异步服务默认使用`async/await`并在服务层集中处理事务。

## 测试准则
- 优先使用`pytest`与`pytest-asyncio`编写异步单元测试，测试文件命名为`test_<module>.py`并放入`backend/tests/`。
- 覆盖率目标建议≥80%；新增功能需包含成功路径、失败路径与边界条件，数据库相关测试请使用事务或临时数据库隔离状态。
- 对于外部依赖（Kafka、通知服务、Redis）首选mock实现；确需集成测试时先在`docker-compose`环境启动配套服务，并记录在测试说明中。

## 提交与合并请求规范
- Commit信息采用`<type>(scope): summary`格式，如`feat(user): 支持批量封禁`；常用`type`包括`feat`、`fix`、`refactor`、`docs`、`test`。
- 提交前确认本地测试通过并附上关键脚本输出；涉及数据库或外部服务改动需在说明中标注配置变更。
- PR描述应包含：变更概述、测试/验证结果、关联任务或需求链接，如有界面或API变更请附截图或示例请求/响应。

## 安全与配置提示
- 永远不要将真实凭据提交到仓库；基于`.env.example`复制`.env`，告知队友仅通过安全渠道分发生产密钥。
- Kafka、PostgreSQL等敏感端口应在本地通过`docker-compose`或内网访问；线上部署请结合`DEPLOYMENT_CHECKLIST.md`审查网络与监控策略。
