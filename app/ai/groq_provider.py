"""Groq adapter using strict structured chat completions."""

import json
from json import JSONDecodeError
from typing import Any, TypeVar

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


def _require_all_properties(value: Any) -> Any:
    """Adapt Pydantic schemas to Groq strict-mode's all-fields-required rule."""

    if isinstance(value, dict):
        result = {key: _require_all_properties(item) for key, item in value.items()}
        properties = result.get("properties")
        if isinstance(properties, dict):
            result["required"] = list(properties)
        return result
    if isinstance(value, list):
        return [_require_all_properties(item) for item in value]
    return value


class GroqProvider:
    """Groq implementation kept behind the application provider protocol."""

    def __init__(
        self,
        api_key: str,
        model: str,
        client: AsyncOpenAI | None = None,
        validation_attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("A Groq API key is required")
        if validation_attempts < 1 or validation_attempts > 3:
            raise ValueError("Groq validation attempts must be between 1 and 3")
        self.model_name = model
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            max_retries=0,
            timeout=60,
        )
        self._validation_attempts = validation_attempts

    async def close(self) -> None:
        await self._client.close()

    async def _parse(
        self, instructions: str, data: dict[str, object], schema: type[StructuredOutput]
    ) -> StructuredOutput:
        strict_schema = _require_all_properties(schema.model_json_schema())
        input_json = json.dumps(data, ensure_ascii=False)
        last_error: Exception | None = None

        for _ in range(self._validation_attempts):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": input_json},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.__name__,
                            "strict": True,
                            "schema": strict_schema,
                        },
                    },
                    temperature=0,
                    max_tokens=2_500,
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
            "The Groq provider returned no valid structured output"
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
