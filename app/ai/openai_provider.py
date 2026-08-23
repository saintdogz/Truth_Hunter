"""Single MVP online AI adapter using structured Responses API outputs."""

import json
from typing import TypeVar

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel

from app.ai.base import AIProviderError
from app.investigation.models import (
    AssessmentDraft,
    ClaimInterpretation,
    EvidenceAssessment,
    InvestigationSummary,
    SearchQueries,
    SourceDocument,
)
from app.investigation.prompts import (
    CLAIM_INTERPRETATION_PROMPT_V1,
    EVIDENCE_EVALUATION_PROMPT_V1,
    SEARCH_QUERY_PROMPT_V2,
    SUMMARY_PROMPT_V1,
)

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class OpenAIProvider:
    """OpenAI implementation kept behind the AIProvider protocol."""

    def __init__(self, api_key: str, model: str, client: AsyncOpenAI | None = None) -> None:
        if not api_key:
            raise ValueError("An OpenAI API key is required")
        self.model_name = model
        self._client = client or AsyncOpenAI(api_key=api_key, max_retries=2, timeout=60)

    async def close(self) -> None:
        await self._client.close()

    async def _parse(
        self, instructions: str, data: dict[str, object], schema: type[StructuredOutput]
    ) -> StructuredOutput:
        try:
            response = await self._client.responses.parse(
                model=self.model_name,
                instructions=instructions,
                input=json.dumps(data, ensure_ascii=False),
                text_format=schema,
                store=False,
                max_output_tokens=2_500,
            )
        except OpenAIError as exc:
            raise AIProviderError("The AI provider request failed") from exc
        parsed = response.output_parsed
        if parsed is None:
            raise AIProviderError("The AI provider returned no valid structured output")
        return parsed

    async def interpret_claim(self, claim: str, detected_language: str) -> ClaimInterpretation:
        return await self._parse(
            CLAIM_INTERPRETATION_PROMPT_V1,
            {"untrusted_claim": claim, "detected_language": detected_language},
            ClaimInterpretation,
        )

    async def generate_search_queries(self, claim: str, detected_language: str) -> SearchQueries:
        return await self._parse(
            SEARCH_QUERY_PROMPT_V2,
            {"untrusted_claim": claim, "input_language": detected_language},
            SearchQueries,
        )

    async def evaluate_evidence(self, claim: str, source: SourceDocument) -> EvidenceAssessment:
        return await self._parse(
            EVIDENCE_EVALUATION_PROMPT_V1,
            {
                "untrusted_claim": claim,
                "untrusted_source": source.model_dump(mode="json"),
            },
            EvidenceAssessment,
        )

    async def generate_summary(
        self,
        claim: str,
        assessment: AssessmentDraft,
        evidence: list[EvidenceAssessment],
        language: str,
    ) -> InvestigationSummary:
        return await self._parse(
            SUMMARY_PROMPT_V1,
            {
                "untrusted_claim": claim,
                "application_assessment": assessment.model_dump(mode="json"),
                "untrusted_evidence_summaries": [item.model_dump(mode="json") for item in evidence],
                "output_language": language,
            },
            InvestigationSummary,
        )
