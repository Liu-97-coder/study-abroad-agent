"""基座层单测：RAG 检索 / 安全护栏 / OCR 抽取。"""
from __future__ import annotations

from ai_agent_core.base.rag_client import EMPTY_HINT, RAGClient, _match_meta, split_text


class TestSplitText:
    def test_short_text_single_chunk(self):
        assert split_text("很短的一句话。", 500, 100) == ["很短的一句话。"]

    def test_long_text_terminates_and_covers(self):
        text = "第一句。第二句。第三句。" * 200
        chunks = split_text(text, 300, 80)
        assert 1 < len(chunks) < 60, f"分片数量异常：{len(chunks)}"
        assert all(len(c) <= 320 for c in chunks)
        # 覆盖度：首尾内容都要出现
        assert text[:10] in chunks[0]
        assert text[-10:] in chunks[-1]

    def test_no_tiny_tail_chunks(self):
        """曾经出过 bug：文末退化成 1 字符步进，产出上百个碎片。"""
        text = "测试文本。" * 300
        chunks = split_text(text, 200, 60)
        tiny = [c for c in chunks if len(c) < 40]
        assert not tiny, f"出现 {len(tiny)} 个碎片分片"


class TestMetaFilter:
    def test_equality(self):
        assert _match_meta({"country": "英国"}, {"country": "英国"})
        assert not _match_meta({"country": "香港"}, {"country": "英国"})

    def test_in(self):
        meta = {"country": "英国"}
        assert _match_meta(meta, {"country": {"$in": ["英国", "香港"]}})
        assert not _match_meta(meta, {"country": {"$in": ["澳洲"]}})

    def test_numeric_range(self):
        meta = {"gpa_min": 3.2}
        assert _match_meta(meta, {"gpa_min": {"$lte": 3.5}})
        assert not _match_meta(meta, {"gpa_min": {"$lte": 3.0}})
        assert _match_meta(meta, {"gpa_min": {"$gte": 3.0}})

    def test_missing_field_not_matched(self):
        assert not _match_meta({}, {"gpa_min": {"$lte": 3.0}})


class TestSearch:
    def test_search_returns_source_id(self, ctx, has_knowledge):
        chunks = ctx.rag.search("school", "英国 计算机硕士 GPA 3.2", top_k=10, rerank_top=5)
        assert chunks, "院校库应该有命中"
        assert all(c.source_info.get("source_id") for c in chunks)
        assert all(0 <= c.score <= 1.2 for c in chunks)

    def test_country_filter_applied(self, ctx, has_knowledge):
        chunks = ctx.rag.search("school", "计算机硕士", where={"country": {"$in": ["香港"]}},
                                top_k=10, rerank_top=10)
        assert chunks
        assert all(c.metadata.get("country") == "香港" for c in chunks)

    def test_empty_when_filter_excludes_all(self, ctx, has_knowledge):
        chunks = ctx.rag.search("school", "计算机", where={"country": {"$in": ["南极洲"]}})
        assert chunks == []

    def test_format_context_has_sources(self, ctx, has_knowledge):
        chunks = ctx.rag.search("school", "爱丁堡 计算机", top_k=5, rerank_top=3)
        text = RAGClient.format_context(chunks)
        assert "来源" in text
        assert "school-" in text

    def test_empty_context_is_explicit(self):
        assert RAGClient.format_context([]) == EMPTY_HINT


class TestSafety:
    def test_commitment_is_high(self, ctx):
        verdict = ctx.safety.check("放心，我们可以保录前 50")
        assert verdict.level == "high"
        assert verdict.blocked is True

    def test_denial_is_low(self, ctx):
        verdict = ctx.safety.check("我们不做保录，也没有内推渠道")
        assert verdict.level == "low"
        assert verdict.blocked is False

    def test_question_is_medium(self, ctx):
        verdict = ctx.safety.check("能不能保录前 50？")
        assert verdict.level == "medium"
        assert verdict.blocked is False

    def test_clean_text_low(self, ctx):
        verdict = ctx.safety.check("这所学校的雅思要求是 6.5")
        assert verdict.level == "low"
        assert verdict.hits == []

    def test_sanitize_replaces_words(self, ctx):
        assert "保录" not in ctx.safety.sanitize("我们可以保录")

    def test_verify_citations(self, ctx):
        items = [{"school_name": "A", "source_id": "school-0001"}, {"school_name": "B"}]
        assert ctx.safety.verify_citations(items) == [1]


class TestOCR:
    def test_extract_fund_entities(self, ctx):
        doc = ctx.ocr.parse(text="中国银行 存款证明 存款金额 300000 元 存入日期 2026-10-20 存期 30 天")
        assert doc.file_type == "存款证明"
        assert doc.entities["fund_amount"] == 300000
        assert doc.entities["deposit_days"] == 30
        assert doc.entities["deposit_date"] == "2026-10-20"

    def test_extract_transcript_entities(self, ctx):
        doc = ctx.ocr.parse(text="南京理工大学 成绩单 TRANSCRIPT 教务处盖章 GPA 3.2 均分 82")
        assert doc.file_type in {"成绩单", "在读证明"}
        assert doc.entities["gpa"] == 3.2
        assert doc.entities["average_score"] == 82

    def test_mask_passport(self, ctx):
        masked = ctx.ocr.mask("护照号 E12345678")
        assert "E12345678" not in masked
        assert masked.count("*") >= 4
        assert len(masked.replace("*", "")) < len("护照号 E12345678")

    def test_empty_file_reports_error(self, ctx):
        doc = ctx.ocr.parse(text="")
        assert doc.errors
