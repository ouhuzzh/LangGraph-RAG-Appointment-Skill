from typing import List, Literal
from pydantic import BaseModel, Field

class QueryAnalysis(BaseModel):
    is_clear: bool = Field(
        description="Indicates if the user's question is clear and answerable."
    )
    questions: List[str] = Field(
        description="List of rewritten, self-contained questions."
    )
    clarification_needed: str = Field(
        description="Explanation if the question is unclear."
    )


class IntentAnalysis(BaseModel):
    intent: Literal["medical_rag", "triage", "clarification"] = Field(
        description="Intent classification. Must be one of: medical_rag, triage, clarification."
    )
    is_clear: bool = Field(
        description="Whether the user's request is clear enough to continue."
    )
    clarification_needed: str = Field(
        description="Clarification question if the request is not clear enough."
    )


class DepartmentRecommendation(BaseModel):
    department: str = Field(
        description="Single primary department recommendation."
    )
    reason: str = Field(
        description="Short reason for the department recommendation."
    )
    needs_clarification: bool = Field(
        description="Whether more information is required before making a recommendation."
    )
    clarification_needed: str = Field(
        description="Clarification question when more information is needed."
    )
