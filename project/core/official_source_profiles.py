from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class OfficialSourceProfile:
    source: str
    label: str
    provider: str
    source_type: str
    language: str
    source_prefix: str
    default_limit: int
    max_limit: int
    catalog_url: str
    expansion_status: str
    scope_note: str
    coverage_note: str
    recommended_use: str
    next_step: str

    def to_dict(self, *, manifest_count=None, local_file_count: int = 0) -> dict:
        data = asdict(self)
        data["manifest_count"] = manifest_count
        data["local_file_count"] = int(local_file_count or 0)
        return data


OFFICIAL_SOURCE_PROFILES = {
    "medlineplus": OfficialSourceProfile(
        source="medlineplus",
        label="MedlinePlus",
        provider="U.S. National Library of Medicine",
        source_type="patient_education",
        language="en",
        source_prefix="medlineplus-",
        default_limit=10,
        max_limit=50,
        catalog_url="https://medlineplus.gov/xml.html",
        expansion_status="broad_source",
        scope_note="批量 XML 健康主题库，是当前最适合做广覆盖患者问答的官方来源。",
        coverage_note="同步时按 limit 拉取健康主题；如果想扩充知识库，优先把 limit 调大或分批同步它。",
        recommended_use="患者教育、常见病解释、生活方式建议、基础医学问答。",
        next_step="如果要更多资料，可提高同步 limit 或分批同步；后续可增加中文翻译/本地化摘要层。",
    ),
    "who": OfficialSourceProfile(
        source="who",
        label="WHO",
        provider="World Health Organization",
        source_type="public_health",
        language="en",
        source_prefix="who-",
        default_limit=10,
        max_limit=50,
        catalog_url="https://www.who.int/news-room/fact-sheets",
        expansion_status="curated_manifest",
        scope_note="当前使用精选 Fact Sheets 清单，不是 WHO 全站爬虫。",
        coverage_note="WHO 适合作为权威公共卫生补充，覆盖常见慢病、传染病、营养与心理健康主题。",
        recommended_use="公共卫生、疾病背景、风险因素、预防建议和权威来源引用。",
        next_step="继续扩容时优先补 Fact Sheets manifest；不建议直接全站爬取，以免混入新闻稿和低相关页面。",
    ),
    "nhc": OfficialSourceProfile(
        source="nhc",
        label="国家卫健委",
        provider="国家卫生健康委员会",
        source_type="clinical_guideline",
        language="zh",
        source_prefix="nhc-",
        default_limit=5,
        max_limit=50,
        catalog_url="https://www.nhc.gov.cn/",
        expansion_status="curated_manifest",
        scope_note="当前使用精选诊疗指南 PDF 清单，不是国家卫健委全站搜索。",
        coverage_note="NHC 适合作为中文权威指南层，不适合作为广覆盖科普主库。",
        recommended_use="中文诊疗方案、指南版本提醒、临床路径类权威依据。",
        next_step="后续可做 NHC 指南候选发现器，再人工确认进入 manifest，避免误收通知/新闻页面。",
    ),
}


def get_official_source_profile(source: str) -> OfficialSourceProfile | None:
    return OFFICIAL_SOURCE_PROFILES.get(str(source or "").strip().lower())


def list_official_source_profiles() -> list[OfficialSourceProfile]:
    return [OFFICIAL_SOURCE_PROFILES[key] for key in ("medlineplus", "who", "nhc")]
