"""文书 Agent：经历解析 / CV / PS / 推荐信 / 质检 / 版本管理。"""
from .cv_generator import detect_family, generate_cv
from .doc_agent_node import DocumentAgent
from .doc_quality_check import check_by_rules, check_document
from .doc_version_mgr import DocVersionManager
from .experience_parse import build_experience_text, parse_experiences
from .ps_generator import generate_ps
from .ref_generator import generate_refs

__all__ = ["DocumentAgent", "detect_family", "generate_cv", "check_by_rules",
           "check_document", "DocVersionManager", "build_experience_text",
           "parse_experiences", "generate_ps", "generate_refs"]
