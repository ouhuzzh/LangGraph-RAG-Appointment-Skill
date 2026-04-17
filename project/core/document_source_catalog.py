import json
from pathlib import Path


OFFICIAL_MEDICAL_SOURCES = [
    {
        "id": "medlineplus_health_topics_xml",
        "title": "MedlinePlus Health Topic XML",
        "provider": "U.S. National Library of Medicine",
        "language": "en",
        "content_type": "patient_education",
        "format": "xml",
        "url": "https://medlineplus.gov/xml.html",
        "reuse_notes": "官方提供批量 XML 下载，适合患者向知识库。",
        "recommended": True,
    },
    {
        "id": "who_health_topics",
        "title": "WHO Health Topics / Fact Sheets",
        "provider": "World Health Organization",
        "language": "en",
        "content_type": "public_health",
        "format": "html",
        "url": "https://www.who.int/health-topics/",
        "reuse_notes": "适合做公共卫生与疾病基础说明，需要保留来源和抓取时间。",
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
        "provider": "国家卫生健康委员会",
        "language": "zh",
        "content_type": "clinical_guideline",
        "format": "pdf/html",
        "url": "https://www.nhc.gov.cn/",
        "reuse_notes": "适合中文临床指南，需要做 PDF 解析和版本管理。",
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
