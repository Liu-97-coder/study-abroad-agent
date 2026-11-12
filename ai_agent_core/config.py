"""全局配置。

所有可调参数集中在这里，可用项目根目录的 .env 覆盖。
对应文档《07-底层基座-通用能力》的"前置环境统一"。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
SEED_DIR = DATA_DIR / "seed"
LOG_DIR = PROJECT_DIR / "logs"
RUNTIME_DIR = PROJECT_DIR / "runtime"


def _load_env(path: Path) -> None:
    """极简 .env 解析，避免额外依赖。已存在的环境变量优先。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(PROJECT_DIR / ".env")


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # ---------- LLM 统一调度（任务 3.6） ----------
    llm_provider: str = _env("LLM_PROVIDER", "mock")  # mock / deepseek / openai / ollama
    llm_base_url: str = _env("LLM_BASE_URL", "https://api.deepseek.com/v1")
    llm_api_key: str = _env("LLM_API_KEY", "")
    llm_model_big: str = _env("LLM_MODEL_BIG", "deepseek-chat")
    llm_model_small: str = _env("LLM_MODEL_SMALL", "deepseek-chat")
    llm_temperature: float = _env_float("LLM_TEMPERATURE", 0.3)
    llm_timeout: float = _env_float("LLM_TIMEOUT", 60)
    llm_max_retry: int = _env_int("LLM_MAX_RETRY", 2)
    llm_cache_ttl: int = _env_int("LLM_CACHE_TTL", 3600)
    llm_max_concurrency_per_customer: int = _env_int("LLM_MAX_CONCURRENCY", 2)

    # ---------- RAG（任务 1） ----------
    rag_backend: str = _env("RAG_BACKEND", "local")  # local / milvus
    # 注意：不要用 MILVUS_URI 这个名字 —— pymilvus 自己会读它当连接地址，
    # 传本地文件路径会让它 import 时就抛 Illegal uri。
    milvus_server_uri: str = _env("MILVUS_SERVER_URI", "")          # http://127.0.0.1:19530
    milvus_local_path: str = _env("MILVUS_LOCAL_PATH", str(RUNTIME_DIR / "milvus_demo.db"))
    embed_backend: str = _env("EMBED_BACKEND", "hashing")  # hashing / openai
    embed_model: str = _env("EMBED_MODEL", "text-embedding-3-small")
    embed_dim: int = _env_int("EMBED_DIM", 1024)
    rag_top_k: int = _env_int("RAG_TOP_K", 20)
    rag_rerank_top: int = _env_int("RAG_RERANK_TOP", 8)

    # ---------- OCR（任务 2） ----------
    # stub：文本/PDF；图片会尝试 rapidocr；rapidocr：图片 OCR（Windows 免编译，推荐）
    # paddleocr：文档原始方案（体积大）
    ocr_backend: str = _env("OCR_BACKEND", "stub")

    # ---------- 调度（任务 3） ----------
    use_langgraph: bool = _env("USE_LANGGRAPH", "1") == "1"
    graph_max_steps: int = _env_int("GRAPH_MAX_STEPS", 12)

    # ---------- 安全护栏（任务 4） ----------
    safety_strict: bool = _env("SAFETY_STRICT", "1") == "1"
    safety_block_level: str = _env("SAFETY_BLOCK_LEVEL", "high")

    # ---------- 鉴权 ----------
    auth_enabled: bool = _env("AUTH_ENABLED", "1") == "1"
    auth_secret: str = _env("AUTH_SECRET", "dev-secret-change-me-in-production")
    auth_ttl: int = _env_int("AUTH_TTL", 8 * 3600)
    auth_default_admin: str = _env("AUTH_DEFAULT_ADMIN", "admin")
    auth_default_password: str = _env("AUTH_DEFAULT_PASSWORD", "admin123")

    # ---------- 选校打分权重（合计 100，见 school_score.py 的口径说明） ----------
    weight_program: int = 60       # 项目本身录取难度（QS + 硬门槛）
    weight_gpa: int = 15           # 学生 GPA 与门槛的差距
    weight_language: int = 10      # 语言分差
    weight_background: int = 5     # 院校背景差距
    weight_deadline: int = 10      # 截止紧迫度

    # ---------- 目录 ----------
    log_dir: Path = field(default=LOG_DIR)
    runtime_dir: Path = field(default=RUNTIME_DIR)
    seed_dir: Path = field(default=SEED_DIR)

    @property
    def llm_enabled(self) -> bool:
        """mock 模式下所有 LLM 调用走规则/模板兜底，保证离线可跑。"""
        return self.llm_provider != "mock" and bool(self.llm_api_key)


settings = Settings()

for _d in (settings.log_dir, settings.runtime_dir, settings.runtime_dir / "rag"):
    _d.mkdir(parents=True, exist_ok=True)

# 四大知识库物理隔离（任务 1.1）
COLLECTIONS = {
    "school": "院校专业库",
    "visa": "签证政策库",
    "writing": "文书素材库",
    "compliance": "内控风控库",
}

# 客户全流程状态机（任务 3.3）
STAGES = [
    "clue",       # 新线索
    "consult",    # 咨询中
    "signed",     # 已签约
    "material",   # 材料收集
    "document",   # 文书制作
    "application",# 网申递交
    "offer",      # Offer / CAS
    "visa",       # 签证
    "finished",   # 完结
]
STAGE_LABELS = {
    "clue": "新线索", "consult": "咨询中", "signed": "已签约",
    "material": "材料收集", "document": "文书制作", "application": "网申递交",
    "offer": "Offer/CAS", "visa": "签证", "finished": "完结",
}
