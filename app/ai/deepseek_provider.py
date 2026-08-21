"""Official DeepSeek adapter using validated JSON chat completions."""

import json
from json import JSONDecodeError
from typing import TypeVar

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

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
    SEARCH_QUERY_PROMPT_V1,
    SUMMARY_PROMPT_V1,
)

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class DeepSeekProvider:
    """DeepSeek implementation kept behind the application provider protocol."""

    def __init__(
        self,
        api_key: str,
        model: str,
        client: AsyncOpenAI | None = None,
        validation_attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("A DeepSeek API key is required")
        if validation_attempts < 1 or validation_attempts > 3:
            raise ValueError("DeepSeek validation attempts must be between 1 and 3")
        self.model_name = model
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            max_retries=0,
            timeout=60,
        )
        self._validation_attempts = validation_attempts

    async def close(self) -> None:
        await self._client.close()

    async def _parse(
        self, instructions: str, data: dict[str, object], schema: type[StructuredOutput]
    ) -> StructuredOutput:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        input_json = json.dumps(data, ensure_ascii=False)
        system_message = (
            f"{instructions}\nReturn one JSON object matching this JSON Schema exactly: "
            f"{schema_json}"
        )
        last_error: Exception | None = None

        for _ in range(self._validation_attempts):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": input_json},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=2_500,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("empty response")
                return schema.model_validate_json(content)
            except (JSONDecodeError, ValidationError, ValueError, IndexError) as exc:
                last_error = exc
            except OpenAIError as exc:
                last_error = exc

        raise AIProviderError(
            "The DeepSeek provider returned no valid structured output"
        ) from last_error

    async def interpret_claim(self, claim: str, detected_language: str) -> ClaimInterpretation:
        return await self._parse(
            CLAIM_INTERPRETATION_PROMPT_V1,
            {"untrusted_claim": claim, "detected_language": detected_language},
            ClaimInterpretation,
        )

    async def generate_search_queries(self, claim: str, detected_language: str) -> SearchQueries:
        return await self._parse(
            SEARCH_QUERY_PROMPT_V1,
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
