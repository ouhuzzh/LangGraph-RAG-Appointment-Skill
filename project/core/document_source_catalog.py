import json
from pathlib import Path

from core.official_source_profiles import OFFICIAL_SOURCE_PROFILES


OFFICIAL_MEDICAL_SOURCES = [
    {
        "id": "medlineplus_health_topics_xml",
        "title": "MedlinePlus Health Topic XML",
        "provider": OFFICIAL_SOURCE_PROFILES["medlineplus"].provider,
        "language": OFFICIAL_SOURCE_PROFILES["medlineplus"].language,
        "content_type": OFFICIAL_SOURCE_PROFILES["medlineplus"].source_type,
        "format": "xml",
        "url": OFFICIAL_SOURCE_PROFILES["medlineplus"].catalog_url,
        "reuse_notes": OFFICIAL_SOURCE_PROFILES["medlineplus"].scope_note,
        "recommended": True,
    },
    {
        "id": "who_health_topics",
        "title": "WHO Health Topics / Fact Sheets",
        "provider": OFFICIAL_SOURCE_PROFILES["who"].provider,
        "language": OFFICIAL_SOURCE_PROFILES["who"].language,
        "content_type": OFFICIAL_SOURCE_PROFILES["who"].source_type,
        "format": "html",
        "url": OFFICIAL_SOURCE_PROFILES["who"].catalog_url,
        "reuse_notes": OFFICIAL_SOURCE_PROFILES["who"].scope_note,
        "recommended": True,
    },
    {
        "id": "nice_guidance",
        "title": "NICE Guidance",
        "provider": "National Institute for Health and Care Excellence",
        "language": "en",
        "content_type": "clinical_guideline",
        "format": "html",
        "url": "https://www.nice.org.uk/guidance",
        "reuse_notes": "适合临床路径和管理建议，不适合直接当患者科普文案。",
        "recommended": True,
    },
    {
        "id": "nhc_guidelines",
        "title": "国家卫生健康委诊疗指南",
        "provider": OFFICIAL_SOURCE_PROFILES["nhc"].provider,
        "language": OFFICIAL_SOURCE_PROFILES["nhc"].language,
        "content_type": OFFICIAL_SOURCE_PROFILES["nhc"].source_type,
        "format": "pdf/html",
        "url": OFFICIAL_SOURCE_PROFILES["nhc"].catalog_url,
        "reuse_notes": OFFICIAL_SOURCE_PROFILES["nhc"].scope_note,
        "recommended": True,
    },
    {
        "id": "pmc_open_access_subset",
        "title": "PMC Open Access Subset",
        "provider": "PubMed Central",
        "language": "en",
        "content_type": "research_article",
        "format": "xml/txt/api",
        "url": "https://pmc.ncbi.nlm.nih.gov/tools/openftlist/",
        "reuse_notes": "只应使用 OA 子集和官方检索方式，适合研究型补充，不建议直接混入患者向主库。",
        "recommended": False,
    },
]


def export_catalog(output_path: str | Path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(OFFICIAL_MEDICAL_SOURCES, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
