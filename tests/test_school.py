"""选校链路单测：抽取 → 筛选 → 分层。"""
from __future__ import annotations

from ai_agent_core.phase1.school_agent.school_filter import _major_ok, filter_schools
from ai_agent_core.phase1.school_agent.school_score import program_difficulty, score_one, split_into_three
from ai_agent_core.phase1.school_agent.student_extract import extract_by_rules, extract_student, normalize
from ai_agent_core.schema.student_schema import StudentBasicInfo

CHAT = ("学生李同学，南京理工大学计算机科学与技术专业大三，GPA 3.2/4.0，均分 82，"
        "雅思 6.5，有两段实习，一段科研，想申请英国和香港的计算机硕士，预算 35 万，"
        "2027 年 9 月入学。")


class TestExtract:
    def test_rules_pick_core_fields(self):
        data = extract_by_rules(CHAT)
        assert data["gpa"] == 3.2
        assert data["average_score"] == 82
        assert data["ielts"] == 6.5
        assert data["internship_count"] == 2
        assert data["research_count"] == 1
        assert set(data["target_country"]) == {"英国", "香港"}
        assert data["target_degree"] == "硕士"
        assert data["target_major"] == "计算机"
        assert data["intake_year"] == 2027
        assert data["school_name"] == "南京理工大学"
        assert data["school_level"] == "985"

    def test_major_strips_school_name(self):
        """曾经把"苏州大学金融学"整段当成专业。"""
        data = extract_by_rules("学生王芳，苏州大学金融学专业大四，GPA 3.6，雅思 7.0。")
        assert data["major"] == "金融学"
        assert data["target_major"] == "金融"

    def test_gpa_scale_conversion(self):
        info = normalize({"gpa": 4.5, "gpa_scale": 5.0})
        assert info.gpa == 3.6
        assert info.gpa_scale == 4.0

    def test_missing_info_detected(self):
        info = normalize({"gpa": 3.0})
        assert "语言成绩（雅思/托福）" in info.missing_info
        assert "意向国家" in info.missing_info

    def test_risk_tags(self):
        info = normalize({"gpa": 2.8, "target_country": ["英国"]})
        assert "GPA偏低" in info.risk_tags
        assert "无语言成绩" in info.risk_tags

    def test_llm_optional(self, ctx):
        """mock 模式下也必须能抽出结果（规则兜底）。"""
        student = extract_student(CHAT, ctx=ctx)
        assert student.gpa == 3.2
        assert student.ielts == 6.5


class TestScore:
    def test_harder_program_scores_higher(self):
        student = StudentBasicInfo(gpa=3.2, ielts=6.5, school_level="普通本科")
        reach = {"school_name": "A", "major_name": "计算机科学", "country": "英国",
                 "qs_rank": 15, "gpa_min": 3.6, "ielts_min": 7.0, "bg_require": "985",
                 "deadline": "2027-01-01", "days_left": 40, "source_id": "school-0001"}
        safe = {"school_name": "B", "major_name": "计算机科学", "country": "英国",
                "qs_rank": 300, "gpa_min": 2.8, "ielts_min": 6.0, "bg_require": "普通本科",
                "deadline": "2027-07-01", "days_left": 200, "source_id": "school-0002"}
        a, b = score_one(reach, student), score_one(safe, student)
        assert a.match_score > b.match_score
        assert a.level_type == "冲刺"
        assert b.level_type == "保底"

    def test_score_detail_sums_to_total(self):
        student = StudentBasicInfo(gpa=3.2, ielts=6.5)
        item = score_one({"school_name": "X", "major_name": "计算机科学", "qs_rank": 40,
                          "gpa_min": 3.4, "ielts_min": 6.5, "days_left": 60,
                          "source_id": "school-0001"}, student)
        assert abs(sum(item.score_detail.values()) - item.match_score) < 0.11
        assert item.source_id == "school-0001"

    def test_difficulty_curve_is_monotonic(self):
        prev = 101
        for qs in (5, 30, 60, 100, 150, 250, 400):
            value = program_difficulty({"qs_rank": qs})
            assert value <= prev, f"QS {qs} 难度反而更高"
            prev = value


class TestFilter:
    def test_major_family(self):
        assert _major_ok("计算机", "数据科学")
        assert _major_ok("计算机", "金融科技")
        assert not _major_ok("计算机", "传媒与传播")
        assert not _major_ok("金融", "计算机科学")
        assert _major_ok(None, "任意专业")      # 学生没说专业就不误杀

    def test_filter_pipeline(self, ctx, has_knowledge):
        student = StudentBasicInfo(gpa=3.2, ielts=6.5, school_level="985",
                                   target_country=["英国", "香港"], target_degree="硕士",
                                   target_major="计算机")
        result = filter_schools(ctx.rag, student)
        assert result.candidates, "应有候选院校"
        assert all(c["source_id"] for c in result.candidates)
        assert all("计算机" in c["major_name"] or "数据" in c["major_name"]
                   or "金融科技" in c["major_name"] or "信息" in c["major_name"]
                   for c in result.candidates), "不应混入无关专业"
        assert all("已截止" not in d["reason"] for d in result.dropped)

    def test_three_buckets(self, ctx, has_knowledge):
        student = StudentBasicInfo(gpa=3.2, ielts=6.5, school_level="985",
                                   target_country=["英国", "香港"], target_degree="硕士",
                                   target_major="计算机")
        filtered = filter_schools(ctx.rag, student)
        buckets = split_into_three(filtered.candidates, student)
        assert len(buckets["冲刺"]) + len(buckets["匹配"]) + len(buckets["保底"]) > 0
        assert sum(1 for v in buckets.values() if v) >= 2, "三档至少两档有内容"
