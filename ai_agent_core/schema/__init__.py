"""全局 Pydantic 结构体（一期 + 二期 + 三期）。

约定：所有 Agent 的输出必须是这里的模型，前端/中台不用做适配。
"""
from .common_schema import ApiResponse, RetrievedChunk, SafetyVerdict, TaskItem
from .state_schema import CustomerState
from .student_schema import StudentBasicInfo
from .school_schema import SchoolItem, SchoolResult
from .document_schema import StudentExperience, DocResult, QualityReport
from .material_schema import MaterialItem, MaterialCheckRisk, MaterialCheckResult, MaterialFullOutput
from .application_schema import FormCheckError, MailInfo, RefereeRemindTask, ApplicationOutput
from .offer_schema import CondCondition, OfferPolicyInfo, OfferFullOutput
from .visa_schema import FundRiskItem, VisaMaterialItem, VisaTimeNode, VisaFullOutput

__all__ = [
    "ApiResponse", "RetrievedChunk", "SafetyVerdict", "TaskItem",
    "CustomerState", "StudentBasicInfo", "SchoolItem", "SchoolResult",
    "StudentExperience", "DocResult", "QualityReport",
    "MaterialItem", "MaterialCheckRisk", "MaterialCheckResult", "MaterialFullOutput",
    "FormCheckError", "MailInfo", "RefereeRemindTask", "ApplicationOutput",
    "CondCondition", "OfferPolicyInfo", "OfferFullOutput",
    "FundRiskItem", "VisaMaterialItem", "VisaTimeNode", "VisaFullOutput",
]
