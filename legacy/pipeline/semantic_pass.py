"""Semantic pass: LLM extraction of relationships from narrative text.

Provider-agnostic via LangChain's init_chat_model(): set EXTRACTION_MODEL to a
"provider:model" string (e.g. "anthropic:claude-sonnet-5", "openai:gpt-5",
"ollama:llama3") and install the matching langchain-<provider> package.

The structured-output schema is the same Pydantic ExtractionResult used by the
structural pass, so the model's JSON is validated on arrival: bad dates,
unknown layers, self-loops, and hand-set weights are all rejected or corrected
before anything reaches the graph.
"""

from __future__ import annotations

import os

from legacy.pipeline.models import (
    ConfidenceTag,
    CriminalNode,
    ExtractionMethod,
    ExtractionResult,
    LayerType,
    NodeType,
    TemporalEdge,
)

DEFAULT_MODEL = "anthropic:claude-sonnet-5"
# Used when EXTRACTION_MODEL is unset but a Gemini key is present (user default).
GEMINI_DEFAULT_MODEL = "google_genai:gemini-2.5-flash-lite"


def resolve_model_name(explicit: str | None = None) -> str:
    """Pick the provider:model string. Precedence: explicit arg > EXTRACTION_MODEL env
    > Gemini default (if GEMINI_API_KEY/GOOGLE_API_KEY present) > anthropic default."""
    if explicit:
        return explicit
    if os.getenv("EXTRACTION_MODEL"):
        return os.environ["EXTRACTION_MODEL"]
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return GEMINI_DEFAULT_MODEL
    return DEFAULT_MODEL


def _prepare_provider_keys(model_name: str) -> None:
    """langchain-google-genai reads GOOGLE_API_KEY; accept the user's GEMINI_API_KEY too."""
    if model_name.startswith("google_genai") or "gemini" in model_name.lower():
        if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

SYSTEM_PROMPT = """You are an extraction engine supporting lawful criminal-network analysis \
of official legal and intelligence documents (court judgments, PCoI reports, police B-Reports, news).
Extract entities and relationships into the provided schema. Follow these rules exactly.

HONESTY RULES (non-negotiable):
- Never invent an edge. Extract only what the text supports.
- If a link is suspected but weakly sourced, tag it AMBIGUOUS rather than omitting it.
- Quote the exact supporting sentence in source_excerpt for every node and edge.

CONFIDENCE TAGS:
- EXTRACTED: the fact is stated as official record in the text (court finding, remand record,
  seizure list, charge sheet). Hard facts only.
- INFERRED: a probable link the text supports through investigative analysis or reporting
  (e.g. a traced financial transfer, observed contact) but not an adjudicated fact.
- AMBIGUOUS: suspected but unconfirmed (single informant, uncorroborated tip, speculation).
Do NOT set weight — it is derived from the tag automatically.

MULTIPLEX LAYERS (choose exactly one per edge):
- IDEOLOGICAL: shared or adopted extremist ideology, radicalisation, allegiance.
- FINANCIAL: money movement — transfers, hawala/undiyal, funding, laundering.
- PRISON_CO_LOCATION: physically co-located in a prison/remand facility.
- TRANSNATIONAL: cross-border links — foreign networks, smuggling routes, overseas handlers.

TEMPORAL RULES:
- Dates in ISO YYYY-MM-DD. Month-only precision -> first day of the month.
- If the text indicates the relationship is ongoing at reporting time, set end_date to null.
- If no date is stated, leave both dates null — do not guess.

ENTITY RULES:
- node_id: lowercase snake_case of the full name (e.g. "Kasun Wijeratne" -> kasun_wijeratne).
- Use node_type ORGANIZATION for groups, networks, and businesses; PERSON otherwise.
- Do NOT create nodes for countries, cities, prisons, or other places — put any place name
  in the edge's `location` field instead. Nodes are only people and organisations.
- Every edge's source and target must appear in the nodes list.
- relation is a short verb slug: met_in_prison, transferred_funds_to, adheres_to_ideology_of,
  routes_funds_through, recruits_for, supplies_narcotics_to, etc."""


def _stamp(result: ExtractionResult, source_file: str) -> ExtractionResult:
    """Provenance is set by the pipeline, not trusted from the model."""
    for node in result.nodes:
        node.source_file = source_file
    for edge in result.edges:
        edge.source_file = source_file
        edge.extraction_method = ExtractionMethod.SEMANTIC
    return result


def extract_semantic(
    text: str,
    source_file: str,
    model_name: str | None = None,
    mock: bool = False,
) -> ExtractionResult:
    """Run the LLM pass over one narrative document (or use the offline mock)."""
    if mock:
        return _stamp(mock_extraction_result(), source_file)

    # Imported lazily so --mock runs without any LLM packages installed.
    from langchain.chat_models import init_chat_model
    from langchain_core.messages import HumanMessage, SystemMessage

    model_name = resolve_model_name(model_name)
    _prepare_provider_keys(model_name)
    llm = init_chat_model(model_name, temperature=0)
    structured_llm = llm.with_structured_output(ExtractionResult)

    result = structured_llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Source document: {source_file}\n\n"
                f"Extract all entities and relationships from the following text:\n\n{text}"
            ),
        ]
    )
    return _stamp(result, source_file)


def mock_extraction_result() -> ExtractionResult:
    """Deterministic stand-in for the LLM: the expected output for
    data/sample/b_report_excerpt.txt. Lets the full pipeline run offline."""
    return ExtractionResult(
        nodes=[
            CriminalNode(
                name="Kasun Wijeratne",
                aliases=["Podda"],
                nic="923456789V",
                source_excerpt='Kasun "Podda" WIJERATNE (NIC 923456789V) and Rizvi FAROOK were both held on E-Wing of Welikada Prison',
            ),
            CriminalNode(
                name="Rizvi Farook",
                source_excerpt='Kasun "Podda" WIJERATNE (NIC 923456789V) and Rizvi FAROOK were both held on E-Wing of Welikada Prison',
            ),
            CriminalNode(
                name="Eastern Front",
                node_type=NodeType.ORGANIZATION,
                source_excerpt='sympathetic to the ideology of the proscribed organisation known as "Eastern Front"',
            ),
            CriminalNode(
                name="Chennai Undiyal Courier Network",
                node_type=NodeType.ORGANIZATION,
                source_excerpt="routed through an undiyal courier network operating between Colombo and Chennai",
            ),
        ],
        edges=[
            TemporalEdge(
                source="kasun_wijeratne",
                target="rizvi_farook",
                relation="met_in_prison",
                layer=LayerType.PRISON_CO_LOCATION,
                confidence=ConfidenceTag.EXTRACTED,  # remand records = official record
                start_date="2023-03-01",
                end_date="2023-08-31",
                location="Welikada Prison",
                source_excerpt="both held on E-Wing of Welikada Prison between March 2023 and August 2023, during which period prison intelligence observed repeated contact",
            ),
            TemporalEdge(
                source="kasun_wijeratne",
                target="rizvi_farook",
                relation="transferred_funds_to",
                layer=LayerType.FINANCIAL,
                confidence=ConfidenceTag.INFERRED,  # traced by CID analysis, not adjudicated
                start_date="2023-06-01",
                end_date=None,  # "believed to be ongoing"
                location="Puttalam",
                source_excerpt="investigators traced an undiyal (hawala) transfer of LKR 4.2 million ... is believed to be ongoing",
            ),
            TemporalEdge(
                source="kasun_wijeratne",
                target="chennai_undiyal_courier_network",
                relation="routes_funds_through",
                layer=LayerType.TRANSNATIONAL,
                confidence=ConfidenceTag.INFERRED,
                start_date="2023-06-01",
                end_date=None,
                source_excerpt="the transfer was routed through an undiyal courier network operating between Colombo and Chennai",
            ),
            TemporalEdge(
                source="rizvi_farook",
                target="eastern_front",
                relation="adheres_to_ideology_of",
                layer=LayerType.IDEOLOGICAL,
                confidence=ConfidenceTag.AMBIGUOUS,  # single informant, no corroboration
                source_excerpt="Officers further suspect, on the basis of an informant statement, that Farook had been sympathetic to the ideology of the proscribed organisation",
            ),
        ],
    )
