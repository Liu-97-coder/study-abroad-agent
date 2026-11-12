# 留学申请全流程 AI Agent 系统

[![CI](https://github.com/Liu-97-coder/study-abroad-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Liu-97-coder/study-abroad-agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![License](https://img.shields.io/badge/License-MIT-green)

基于 FastAPI + LangGraph 的留学中介业务系统。把顾问手工完成的选校、文书、材料、网申、Offer、签证、面试模拟七个环节，拆成可独立调度、可回退的 Agent，配合四库隔离的 RAG 检索与话术风控，覆盖从线索到签证的完整流程。

不配置大模型 API Key 时使用规则与模板兜底，全流程可离线跑通；配置 Key 后同一套代码自动切换为真实模型输出。

![工作台](docs/screenshots/01-workbench.png)

## 简介

留学顾问的工作由大量重复但不可省略的判断组成：看背景定校、查截止日期、催材料、写文书、填网申、核对 Offer 条件、准备签证资金材料。单个环节不难，但同时带二十个学生时，遗漏与返工集中出现在环节之间的交接处。

本项目将这些环节实现为一条状态机驱动的流水线。每个环节由一个独立 Agent 负责，输出写入统一的状态对象，顾问确认后才推进到下一阶段。所有硬性数据（GPA 换算、截止天数、资金门槛）由规则表计算，模型只负责生成需要自然语言表达的部分；每条结论携带 `source_id`，可回溯到原始文档。

## 功能特性

- **选校**：冲刺 / 匹配 / 保底三档，结合 QS 排名、GPA 门槛、语言要求、专业匹配计算难度分，输出风险标签与评估报告。
- **文书**：CV、PS、推荐信三件套，六维质检打分（真实匹配度、专业匹配度、模板化程度、空话冗余度、逻辑连贯性、语法地道性），版本固化可回溯。
- **材料**：按国家 / 学位 / 在读状态生成个性化清单，上传文件经 OCR 抽取字段后做规则校验，不合格项给出整改建议。
- **网申**：表单格式预校验、院校邮件意图识别、截止日期三级倒计时、推荐人提交状态跟踪。
- **Offer**：Con 条件解析、达标风险计算、押金规则、CAS 时间线倒推。
- **签证**：资金四维风险（金额 / 存期 / 来源 / 时间）、材料包生成、递签时间线。
- **面试模拟**：按目标专业抽取六道题（动机 / 学术 / 实习 / 行为 / 思辨 / 院校），五维评分与复盘报告。
- **合规风控**：关键词 → 语境 → 语义三级判定，拦截「保录」「包过」等违规承诺并转人工；每步并行执行，只读不影响主流程。
- **多顾问隔离**：自签 HS256 JWT + 客户级数据隔离，顾问只能访问名下客户，越权返回 403。
- **学生端**：带 access_key 的免登录链接，学生可查看材料缺口并上传，OCR 后即时校验。

## 界面预览

选校结果，每条包含难度分、硬门槛、截止天数与风险提示：

![选校](docs/screenshots/02-school.png)

文书页，质检分与六维明细，意见会指出经历清单中不存在的情节：

![文书](docs/screenshots/08-document-llm.png)

风控看板，按客户所处环节统计漏斗与风险标签：

![看板](docs/screenshots/04-dashboard.png)

学生端，上传材料后即时返回校验结果：

![学生端](docs/screenshots/05-student.png)

## 技术栈

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 语言 | Python 3.10+ | 全项目类型标注 |
| Web 框架 | FastAPI + Pydantic v2 | 自动生成 `/docs` |
| 编排 | LangGraph | 未安装时降级为内置路由循环 |
| 向量库 | 本地 JSON / Milvus | 默认本地，零依赖 |
| Embedding | hashing 1024 维 / OpenAI 兼容 | 默认离线，可替换 |
| 大模型 | OpenAI 兼容协议 | DeepSeek 已验证 |
| OCR | RapidOCR（ONNX） | Windows 免编译 |
| 存储 | SQLite | 客户、待办、风险、文书版本、面试记录 |
| 前端 | 原生 HTML / CSS / JS | 无构建步骤，由 FastAPI 直接托管 |
| 测试 | pytest | 86 个用例，CI 自动执行 |

## 快速开始

### 环境要求

- Windows 10/11 或 Linux
- Python 3.10 及以上
- 无需数据库、无需 Docker

### 安装

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

该脚本会创建虚拟环境、安装依赖、灌入知识库并执行一次自测。只想装环境可加 `-SkipSmoke`。

### 配置

默认使用 mock 模式，无需任何 API Key。如需接入真实模型，编辑 `.env`：

```bash
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxxx
LLM_MODEL_BIG=deepseek-chat
```

或使用脚本写入（自动备份、验证失败回滚）：

```powershell
.\.venv\Scripts\python.exe scripts\set_llm_key.py --key sk-xxxx
```

### 启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

或双击 `启动服务.bat`。默认端口 8000，被占用时自动顺延，以窗口输出为准。

访问地址：

| 地址 | 内容 |
| --- | --- |
| `http://127.0.0.1:8000/` | Web 控制台 |
| `http://127.0.0.1:8000/docs` | 接口文档 |
| `http://127.0.0.1:8000/student.html?k=xxx` | 学生端 |

默认账号：

| 账号 | 密码 | 权限 |
| --- | --- | --- |
| `admin` | `admin123` | 机构负责人，可见全部客户 |
| `advisor1` | `123456` | 顾问，仅名下客户 |
| `advisor2` | `123456` | 顾问，仅名下客户 |

### 演示数据

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo.py --reset
```

生成四个处于不同阶段的客户，看板与台账即刻有数据。

## 项目结构

```
study-abroad-agent/
├── ai_agent_core/
│   ├── base/          基座：RAG、LLM 调度、OCR、风控、LangGraph 引擎、日志
│   ├── phase1/        选校、文书
│   ├── phase2/        材料、网申、Offer、签证
│   ├── phase3/        合规巡检、高危预判、交接
│   ├── api/           FastAPI 路由
│   ├── schema/        Pydantic 结构体
│   └── config.py      全局配置
├── web/               控制台与学生端
├── data/seed/         院校库、签证政策、文书素材、合规词库、面试题库
├── tests/             pytest 用例
├── scripts/           安装、启动、自检、部署脚本
├── docs/              操作手册、实现步骤、架构决策、部署说明
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 接口说明

统一返回结构 `{"code": 0, "message": "ok", "data": {...}}`，限流 20 次/分钟。

| 模块 | 接口 |
| --- | --- |
| 选校 | `POST /api/school/extract` `/match` `/report` `/talk` `/summary` |
| 文书 | `POST /api/doc/parse-experience` `/generate-cv` `/generate-ps` `/generate-ref` `/quality-check` `/version-save` |
| 材料 | `POST /api/material/build-list` `/check-file` `/get-risk-todo` |
| 网申 | `POST /api/application/form-check` `/parse-mail`；`GET /api/application/deadline-warn` |
| Offer | `POST /api/offer/parse-offer`；`GET /api/offer/calc-cond-risk` `/cas-material-plan` |
| 签证 | `POST /api/visa/build-visa-list` `/analyze-fund`；`GET /api/visa/get-visa-timeline` |
| 调度 | `POST /api/graph/run-all` 及各阶段接口；`GET /api/graph/trace/{id}` |
| 中台 | `GET /api/customer/list` `/customer/{id}` `/tasks` `/risks` `/handover` |
| 看板 | `GET /api/dashboard/overview` `/health` |

完整示例见 `docs/api-examples.http`（20 个可直接发送的请求）。

## 配置项

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_PROVIDER` | `mock` | `mock` / `deepseek` / `openai` / `ollama` |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | 兼容 OpenAI 协议的地址 |
| `LLM_API_KEY` | 空 | 模型 Key |
| `LLM_MODEL_BIG` | `deepseek-chat` | 用于文书与评估 |
| `LLM_MODEL_SMALL` | `deepseek-chat` | 用于抽取与纪要 |
| `RAG_BACKEND` | `local` | `local` / `milvus` |
| `MILVUS_SERVER_URI` | 空 | 独立 Milvus 服务地址 |
| `MILVUS_LOCAL_PATH` | `./runtime/milvus_demo.db` | Milvus Lite 数据库路径 |
| `EMBED_BACKEND` | `hashing` | `hashing` / `openai` |
| `OCR_BACKEND` | `stub` | `stub` / `paddleocr` |
| `AUTH_ENABLED` | `1` | 关闭后所有请求视为管理员 |
| `AUTH_SECRET` | `dev-secret-...` | 生产环境必须替换为随机值 |
| `AUTH_TTL` | `28800` | Token 有效期（秒） |

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest                                        # 86 个用例
.\.venv\Scripts\python.exe scripts\smoke_test.py                            # 端到端 12 项断言
.\.venv\Scripts\python.exe scripts\api_smoke.py --base http://127.0.0.1:8000  # 接口契约
```

单元测试中的 Context 被固定为 mock 模式，执行测试不产生模型调用费用，也不依赖网络。

专项自检脚本：

| 脚本 | 校验内容 |
| --- | --- |
| `check_auth.py` | 未登录 401、管理员全量可见、顾问越权 403、伪造 Token |
| `check_student.py` | 学生端链接、进度、上传校验、越权 404 |
| `check_milvus.py` | 建库、写入、检索、标量过滤、覆盖更新 |
| `check_interview.py` | 出题梯度、五维评分、复盘报告 |
| `check_deploy.py` | 全新环境仅装 requirements 后启动应用 |
| `check_prod.py` | 按容器启动方式验证 0.0.0.0 绑定、健康检查、局域网访问 |

## 部署

### 本机常驻

```powershell
双击 开机自启.bat
```

在启动文件夹创建快捷方式，登录后以隐藏窗口运行 `scripts/run_server.py`，日志写入 `logs/server.log`，异常退出自动重启。取消自启双击 `取消自启.bat`。

### Docker

```powershell
右键 安装WSL.bat -> 以管理员身份运行
重启电脑
双击 启动Docker.bat
```

镜像基于 `python:3.12-slim`，非 root 用户运行，健康检查使用 `scripts/healthcheck.py`（不依赖 curl），启动前幂等灌库，`runtime/` 与 `logs/` 挂载到宿主机。

**当前状态：Docker 与 Docker Desktop 已安装，WSL2 内核尚未安装，镜像未实际构建运行。** 为验证构建前提，提供了两个替代检查：

```powershell
.\.venv\Scripts\python.exe scripts\check_deploy.py   # 干净环境仅装 requirements 后启动
.\.venv\Scripts\python.exe scripts\check_prod.py     # 按容器启动方式验证绑定与健康检查
```

### Linux

参见 `docs/部署.md`，含 systemd 服务单元与 nginx 反向代理配置。

## 已知限制

- 院校与签证数据为 33 条教学样例，生产环境需接入当年数据并持续维护。
- 合规仅覆盖话术拦截，未实现个人信息授权、留存期限与脱敏审计。
- 未实现监控指标与压力测试，仅有 trace 日志。
- 鉴权为最小实现，未接入企业微信或 OAuth，无刷新 Token 与密码找回。
- 单实例部署，未实现多租户。
- Docker 镜像未实际构建运行，容器方案尚未验证。
- hashing 向量基于字面重合，语义检索能力有限，生产建议替换为 bge-m3 等模型。

## 贡献

个人项目，欢迎提交 Issue 讨论实现思路。提交代码前请确保 `pytest` 与 `smoke_test.py` 通过。

## 许可证

[MIT](LICENSE)

## 致谢

业务设计参考语雀《项目经验扩展库（黑马鹏鹏讲AI）》共十一篇文档，实现、测试与部署由本人完成。
