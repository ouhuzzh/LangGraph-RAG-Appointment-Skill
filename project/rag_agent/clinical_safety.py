"""Clinical safety guardrail — graded red-flag triage + prescription-boundary checks.

Pure, dependency-light helpers that (a) grade the clinical urgency of a user
query into ``critical / high / moderate / normal``, (b) detect when an answer
over-steps into specific prescription/dosing advice, and (c) render an
emergency-escalation notice.

Kept free of graph/LLM/DB imports so it is trivially unit-testable and safe to
call from any node.  It is wired into risk inference only when
``config.ENABLE_CLINICAL_SAFETY_GUARDRAIL`` is set (default off), so it is
strictly additive to existing behavior.
"""

from __future__ import annotations

import re


# Single symptoms that always warrant immediate (emergency) evaluation.
CRITICAL_SYMPTOMS = (
    "胸痛", "胸闷", "呼吸困难", "呼吸急促", "意识模糊", "昏迷", "抽搐",
    "大出血", "咯血", "呕血", "晕厥", "偏瘫", "半身不遂",
    "severe chest pain", "shortness of breath", "unconscious", "seizure",
)

# Serious symptoms warranting prompt in-person care (but not always 120-level).
HIGH_SYMPTOMS = (
    "持续高热", "高烧不退", "剧烈头痛", "剧烈腹痛", "视物模糊", "肢体无力",
    "说话不清", "口角歪斜", "血便", "黑便", "持续呕吐",
)

# Co-occurring pairs that escalate to critical even if each token alone is milder.
CRITICAL_COMBINATIONS = (
    ("突然", "剧烈头痛"),
    ("突发", "头痛"),
    ("胸痛", "出汗"),
    ("胸痛", "左臂"),
    ("头痛", "呕吐"),
)

# Query markers indicating a medication dose/adjustment question — moderate risk,
# handled with conservative "confirm with a clinician" wording.
MODERATE_MARKERS = (
    "剂量", "服用多少", "吃几片", "用量", "加量", "减量", "停药",
    "dose", "dosage", "how much",
)

# Answer-side patterns: concrete dosing the assistant should not assert on its own.
_PRESCRIPTION_PATTERNS = (
    r"每\s*(?:天|日)\s*\d+\s*次",
    r"每次\s*\d+\s*(?:mg|毫克|g|克|片|粒|ml|毫升|iu|单位)",
    r"\d+\s*(?:mg|毫克|g|克|片|粒|ml|毫升|iu|单位)\s*(?:每|一)?\s*(?:天|日|次)",
    r"服用\s*\d+\s*(?:mg|毫克|片|粒)",
)

_SEVERITY_ORDER = {"normal": 0, "moderate": 1, "high": 2, "critical": 3}


def classify_severity(query: str) -> str:
    """Grade a query into ``critical / high / moderate / normal``."""
    text = (query or "").strip().lower()
    if not text:
        return "normal"
    if any(symptom.lower() in text for symptom in CRITICAL_SYMPTOMS):
        return "critical"
    for first, second in CRITICAL_COMBINATIONS:
        if first.lower() in text and second.lower() in text:
            return "critical"
    if any(symptom.lower() in text for symptom in HIGH_SYMPTOMS):
        return "high"
    if any(marker.lower() in text for marker in MODERATE_MARKERS):
        return "moderate"
    return "normal"


def is_at_least(severity: str, threshold: str) -> bool:
    """True when ``severity`` is at or above ``threshold`` on the severity scale."""
    return _SEVERITY_ORDER.get(severity, 0) >= _SEVERITY_ORDER.get(threshold, 0)


def detect_prescription_overreach(answer: str) -> bool:
    """True when an answer asserts specific dosing/prescription instructions."""
    text = str(answer or "")
    return any(re.search(pattern, text) for pattern in _PRESCRIPTION_PATTERNS)


def emergency_escalation_message(severity: str) -> str:
    """Render an escalation banner for ``critical`` / ``high``; empty otherwise."""
    if severity == "critical":
        return (
            "⚠️ **紧急提醒**\n\n"
            "你描述的症状包含需要**立即处理**的危险信号。请**立刻拨打 120 或前往最近医院急诊科**，"
            "不要等待在线回复或自行用药。"
        )
    if severity == "high":
        return (
            "⚠️ **风险提醒**\n\n"
            "你描述的症状风险较高，建议**尽快线下就医**；若症状持续加重，请优先急诊评估。"
        )
    return ""


# Allergy phrasing produced by the memory extractor: "对X过敏" (optionally
# "对X类药物过敏"). Exact-match only — cross-reactivity (e.g. penicillin-class
# derivatives) is deliberately out of scope to keep false positives at zero.
_ALLERGY_RE = re.compile(r"对\s*([\u4e00-\u9fffA-Za-z0-9·]+?)\s*(?:类)?(?:药物)?过敏")


def extract_allergens(memories_text: str) -> list:
    """Pull allergen names out of long-term memory text ("对青霉素过敏" -> 青霉素)."""
    text = str(memories_text or "")
    allergens = []
    for match in _ALLERGY_RE.finditer(text):
        item = match.group(1).strip()
        if item and item not in allergens:
            allergens.append(item)
    return allergens


def build_allergy_conflict_note(memories_text: str, answer_text: str) -> str:
    """Warn when the answer mentions a substance the user is known to be allergic to.

    Memory x safety cross-check: returns an appendable banner, or "" when there
    is no conflict. Pure function — never raises."""
    answer = str(answer_text or "")
    if not answer:
        return ""
    hits = [item for item in extract_allergens(memories_text) if item in answer]
    if not hits:
        return ""
    joined = "、".join(hits)
    return (
        f"\n\n⚠️ **过敏提醒**：根据你的健康档案，你对 **{joined}** 过敏，"
        "上文提到的相关药物请勿自行使用，务必先咨询医生或药师。"
    )
