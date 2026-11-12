# 留学中介的 AI 助手

[![CI](https://github.com/Liu-97-coder/study-abroad-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Liu-97-coder/study-abroad-agent/actions/workflows/ci.yml)

跟着语雀上一套教程做的练习项目，业务是留学中介的申请流程。教程给的是设计文档，代码、测试、部署和后面那些坑是我自己补的。

![工作台](docs/screenshots/01-workbench.png)

---

## 它到底替人干了什么

留学顾问的活其实很碎：看学生背景定校、查截止日期、催材料、写文书、填网申、盯 Offer 条件、准备签证资金材料。每一件都不难，但七件事串起来，一个顾问同时带二十个学生就会乱。

这个项目把这些做成了能跑的东西：左边贴一段聊天记录，右边依次出选校清单、评估报告、文书、材料清单、网申校验、Offer 条件、签证材料，每一份都标了依据。

最后加了一个面试模拟：按目标专业抽六道题（动机、学术、实习、行为、思辨、院校各一道），学生答完按五个维度打分，再出一份复盘。

## 跑起来

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # 建虚拟环境、装依赖、灌知识库、自测
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1     # 启动
```

不想开终端就双击 `启动服务.bat`。8000 端口被占会自动往后顺延，**以窗口打印的地址为准**，不要死记 8000。

打开 `http://127.0.0.1:8000/` 是控制台，`/docs` 是接口文档。

登录：`admin / admin123` 是机构负责人，能看全部客户；`advisor1 / 123456` 和 `advisor2 / 123456` 是顾问，只能看自己名下的，越权会返回 403。

想直接看效果，先灌一批演示客户：

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo.py --reset
```

## 界面

工作台左边输聊天记录，下面有个「填充示例」，点「一键跑全流程」，右边按 Agent 分 Tab 出结果。选校是三档，每条带难度分和截止天数：

![选校](docs/screenshots/02-school.png)

文书这里接真模型之后是这样，质检 88 分，六维分开打分。它会在意见里指出"开头这段校园问卷的经历在经验清单里没有，建议核实"，这个比单纯打个分有用。

![文书](docs/screenshots/08-document-llm.png)

风控看板把客户按阶段铺开，能看出卡在哪一步：

![看板](docs/screenshots/04-dashboard.png)

学生端是一个带 access_key 的免登录链接，学生自己能看还差什么材料，上传后当场告诉他过没过：

![学生端](docs/screenshots/05-student.png)

## 代码怎么分的

```
ai_agent_core/
  base/        基座：RAG 检索、LLM 调用、OCR、风控、LangGraph 调度、日志
  phase1/      选校、文书
  phase2/      材料、网申、Offer、签证
  phase3/      合规巡检、交接
  api/         FastAPI 路由
web/           控制台 + 学生端，原生 HTML/CSS/JS，没有构建步骤
data/seed/     院校库、签证政策、文书素材、合规词库
tests/         86 个用例
scripts/       安装、启动、自检、部署脚本
```

`base/` 和 `phaseN/` 的分法是照教程来的：基座提供能力，每个阶段只写自己的业务。加第八个 Agent 的时候我基本没动主流程，就是在注册表里加一行、新建一个目录。

## 几个当时纠结过的决定

**为什么不写一个大 Agent，而是拆八个。**
一开始试过把提示词堆一起，结果一次调用要输出选校+文书+材料，稍微长一点就截断，而且改一处影响全部。拆开之后每个 Agent 的输入输出都能单独测，出问题也好定位。代价是状态要在它们之间传，所以有了 `state.agent_outputs` 这个东西。

**为什么 RAG 分四个库而不是一个。**
混在一起的时候，查"英国计算机硕士的雅思要求"，前几条经常被文书模板挤掉，因为文案类和政策类的向量太像。按院校、签证、文书、合规分开之后，每库可以单独设条数和阈值，院校库还能先按国家/专业做标量过滤再检索。检索质量是这么上去的。

**为什么分数和截止日期不让模型算。**
模型算 GPA 换算、算截止日期剩下的天数，偶尔会错，而且错了看不出来。这些改成规则表，模型只负责写人话的部分。这样一来没配 API Key 也能把流程跑完——分数照样算，只是文书变成结构稿。

**为什么留着 mock 模式。**
主要是为了测试。pytest 里 Context 被强制成 mock，跑一次测试不花一分钱，也不依赖网络。要验真实模型，单独跑 `check_real_run.py`。

**为什么鉴权自己写。**
其实是不想为了一个练习项目引入 passlib + python-jose 这一堆。HS256 签名用 hmac 和 base64 三十行能写完，PBKDF2 用标准库 hashlib。代价是没有刷新 token、没有密码找回，生产肯定不够用。

## 踩过的坑

这些是我改到一半卡住、后来翻出来记下的，按时间顺序：

- 院校 CSV 里写着 `£38,500`，逗号把列错位了，整整一列数据全歪。后来把千分位去掉才正常。
- 分片函数在最后一段会死循环，一口气切出 104 个碎渣，检索全是噪音。加了 `if end >= len(text): break`。
- 有个正则忘了加捕获组，`extract_conditions` 直接抛 `IndexError: no such group`，排查了半小时。
- 上传文件之后学生信息被覆盖了：`state.student_info = student.model_dump()` 把已上传的文件列表冲掉了，改成合并。
- Milvus 检索报 `Collection 'school' is in state 'released'`，要先 `load_collection` 才能查。
- 环境变量不能叫 `MILVUS_URI`。pymilvus 自己会读这个名字，我一设，它就把相对路径当 URI，报 `Illegal uri`。改成 `MILVUS_SERVER_URI` 和 `MILVUS_LOCAL_PATH` 才对。
- 切到 Milvus 之后，本地的签证和文书库被清空了——`_save` 在 milvus 模式下也照写，写进去是空数组。加了 `if self._milvus: return`。
- 中文 `.ps1` 存成 UTF-8 无 BOM，PowerShell 5.1 按 ANSI 读，直接解析失败。要带 BOM。
- `.bat` 用 LF 换行，双击一闪就没了；改 CRLF 才正常。里面还写过中文，代码页一换就乱码，最后 bat 全部改成纯英文，中文提示交给 PowerShell 输出。
- 8000 端口被看不见的进程占着，`taskkill` 说找不到，但端口在监听。最后写了个按端口杀的 `stop.ps1`。
- 提权安装 WSL 的时候，脚本里的相对路径全废了——提权进程的当前目录是 `C:\Windows\System32`。改成绝对路径。
- WSL2 到现在没装上。Docker Desktop 装好了，引擎起不来，缺 WSL 内核，要管理员权限。所以下面的容器方案**我没跑过**。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest                    # 86 个，隔离临时目录，不动你的数据
.\.venv\Scripts\python.exe scripts\smoke_test.py        # 端到端 12 项断言
.\.venv\Scripts\python.exe scripts\api_smoke.py --base http://127.0.0.1:8000   # 接口契约
```

另外几个专项自检脚本，输出都是 PASS/FAIL，哪个红了看哪行：

`check_auth.py` 查 401/403 和伪造 token，`check_student.py` 查学生端越权和上传校验，`check_milvus.py` 查向量库读写，`check_interview.py` 查面试评分，`check_deploy.py` 在干净环境里只装 requirements 跑一遍，`check_prod.py` 按容器的启动方式验证 0.0.0.0 绑定和局域网访问。

这些测试主要防的不是"跑不通"，是改坏：分片别再退化成碎片、检索必须带 source_id、顾问越权必须 403、接口返回结构别漂移。

## 配置

`.env` 里常改的就这几行：

```bash
LLM_PROVIDER=mock          # mock / deepseek / openai / ollama
LLM_API_KEY=
LLM_MODEL_BIG=deepseek-chat
RAG_BACKEND=local          # local / milvus
AUTH_ENABLED=1
AUTH_SECRET=dev-secret-change-me-in-production   # 生产必须换
```

接真模型别手改，用脚本，它会先备份、再写、然后真发一次请求验证，失败了自动回滚：

```powershell
.\.venv\Scripts\python.exe scripts\set_llm_key.py --key sk-xxxx
.\.venv\Scripts\python.exe scripts\set_llm_key.py --show
```

改完 `.env` 要重启服务，配置是启动时读的。

## 部署

本机当内部系统用，双击 `开机自启.bat`，会在启动文件夹放一个快捷方式，登录后用 wscript 隐藏窗口跑起来，日志在 `logs/server.log`，挂了会自动重启。取消就双击 `取消自启.bat`。

容器这边，`Dockerfile` 和 `docker-compose.yml` 是按标准写的：非 root 用户跑、健康检查用 Python 脚本不依赖 curl、启动前先灌库、runtime 和 logs 挂到宿主机。**但没有真正构建运行过**，卡在 WSL。为了尽量确认不是纸上谈兵，写了两个等价验证：

```powershell
.\.venv\Scripts\python.exe scripts\check_deploy.py   # 干净 venv 只装 requirements，能起来就说明依赖层没问题
.\.venv\Scripts\python.exe scripts\check_prod.py     # 按镜像的启动方式跑，验 0.0.0.0、健康检查、局域网
```

两个都过了，局域网 192.168.155.21 也能访问。但这只能说明依赖和启动方式没问题，不等于镜像一定能构建成功。

Linux 上要上真环境，`docs/部署.md` 里有 systemd 和 nginx 的写法，也没实跑过。

## 还没做的

按我自己的判断，从"能演示"到"能用"还差这些：

- 院校和签证数据是 33 条教学样例，真实数据要每年维护，这是这行产品真正的成本。
- 合规只做了话术拦截。学生护照、成绩单是敏感个人信息，授权书、留存期限、脱敏审计这些一样没有，真上线是法律问题不是技术问题。
- 没有监控和压测，只有 trace 日志。
- 鉴权是最小可用版，企业微信登录没做。
- 一个部署服务一家机构，没有多租户。

## 参考

业务设计来自语雀《项目经验扩展库（黑马鹏鹏讲AI）》那十一篇。我按它的结构落了一遍，实现里加了测试、鉴权、学生端、容器和部署脚本，也踩了一堆上面记的坑。

文档在 `docs/` 下面：`手把手操作手册.md` 是从装 Python 开始写的，`一步步实现.md` 是分步实现，`架构决策.md` 记了为什么这么选，`面试对照.md` 把每篇需求对应到文件，`部署.md` 是三种部署方式。
