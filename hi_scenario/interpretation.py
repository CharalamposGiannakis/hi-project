"""Turn an untrusted interpretation into editable, canonical-shaped draft data."""

import re
from collections import Counter
from functools import cache
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator

from .model import Scenario
from .rdf import HINT
from .vocabulary import CATEGORIES, concepts


Question = Literal[
    "use_case", "goal", "tasks", "agents", "capabilities", "context", "team_constraints",
    "executions", "interactions", "experiments", "evaluations", "additional_notes",
]
MAX_DESCRIPTION_LENGTH = 20_000


class InterpretationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: dict[Question, Annotated[str, StringConstraints(strict=True, max_length=MAX_DESCRIPTION_LENGTH)]]

    @field_validator("description")
    @classmethod
    def check_description(cls, description: dict[Question, str]) -> dict[Question, str]:
        if not any(answer.strip() for answer in description.values()):
            raise ValueError("Enter a description in at least one section.")
        if sum(map(len, description.values())) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"Keep the complete description within {MAX_DESCRIPTION_LENGTH:,} characters.")
        return description


DiagnosticKind = Literal[
    "missing_information", "ambiguity", "unsupported_vocabulary", "unsupported_relationship",
    "structural", "technical_validation",
]


class Diagnostic(BaseModel):
    kind: DiagnosticKind
    message: str
    path: str | None = Field(default=None, exclude_if=lambda value: value is None)


class InterpretationFindings(BaseModel):
    status: Literal["complete", "incomplete"]
    model: str
    prompt_version: str
    prompt_sha256: str
    diagnostics: list[Diagnostic]


class InterpretationResult(BaseModel):
    scenario: dict[str, Any] | None
    interpretation: InterpretationFindings


_SCHEMA = Scenario.model_json_schema()
_IDENTIFIER_PATTERN = re.compile(_SCHEMA["properties"]["id"]["pattern"])
_SCENARIO_FIELDS = _SCHEMA["properties"].keys() - {"id"}
_MODEL_DIAGNOSTICS = {
    "missing_information", "ambiguity", "unsupported_vocabulary", "unsupported_relationship", "structural",
}

# Field categories are the same as those used by the RDF mapper. The actual
# term IDs are loaded from the approved thesaurus, including the Evaluation fallback.
_CONCEPT_FIELDS = {
    "Scenario": {"team_constraints": "Constraint"},
    "UseCase": {"concept": "UseCase", "domain": "Domain"},
    "Goal": {"concept": "Goal"},
    "Task": {"concept": "Task"},
    "Agent": {"roles": "Role"},
    "Context": {"concept": "Context", "phenomena": "Phenomenon", "constraints": "Constraint"},
    "Capability": {"concept": "Capability"},
    "Execution": {"concept": "TaskExecution", "method": "Method"},
    "Experiment": {"concept": "Experiment", "metrics": "Metric"},
    "Evaluation": {"concept": "Evaluation", "metrics": "Metric"},
    "Interaction": {"intent": "InteractionIntent", "modality": "InteractionModality"},
}
_REFERENCE_FIELDS = {
    "goal": {"required_tasks": "tasks"},
    "capabilities": {"agents": "agents", "tasks": "tasks"},
    "executions": {"agent": "agents", "task": "tasks"},
    "evaluations": {"experiment": "experiments", "executions": "executions"},
    "interactions": {"agents": "agents", "executions": "executions"},
}
_MANAGED_ID_PATH = re.compile(
    r"(?:scenario\.)?(?:id|(?:use_case|goal)\.id|"
    r"(?:tasks|agents|capabilities|executions|experiments|evaluations|interactions)(?:\.\d+|\[\d+\])\.id)"
)
_LABEL_SEPARATOR = re.compile(r"[\s_-]+")


def _is_managed_id_path(path: Any) -> bool:
    return isinstance(path, str) and _MANAGED_ID_PATH.fullmatch(path.strip()) is not None


@cache
def _approved_terms() -> dict[str, dict[str, str]]:
    return {category: {term["id"]: term["label"] for term in concepts(category)} for category in CATEGORIES}


def _category_for_path(path: str | None) -> str | None:
    if not path:
        return None
    fields = [part for part in re.split(r"[.\[\]]", path.strip().removeprefix("scenario.")) if part and not part.isdecimal()]
    if len(fields) == 1:
        return _CONCEPT_FIELDS["Scenario"].get(fields[0])
    if len(fields) != 2:
        return None
    section, field = fields
    schema = _SCHEMA["properties"].get(section, {})
    schema = schema.get("items", schema)
    schema = next((option for option in schema.get("anyOf", ()) if "$ref" in option), schema)
    title = schema.get("$ref", "").rsplit("/", 1)[-1]
    return _CONCEPT_FIELDS.get(title, {}).get(field)


def _reports_approved_term(note: dict, path: str | None) -> bool:
    vocabulary = _approved_terms()
    category = _category_for_path(path)
    if category is None and isinstance(note.get("category"), str) and note["category"] in vocabulary:
        category = note["category"]

    term = note.get("term")
    if not isinstance(term, str) or not term.strip():
        # Fall back to an identifiable subject in older, free-text diagnostics.
        message = note["message"]
        subject_pattern = r"""(`[^`]+`|"[^"]+"|'[^']+'|“[^”]+”|‘[^’]+’|\b[A-Za-z][A-Za-z0-9]*\b)"""
        denied = re.search(
            subject_pattern + r"\s+(?:is|was)\s+(?:not\s+(?:an? approved|available|listed|included|present|in)|absent|missing|unavailable)\b",
            message, re.IGNORECASE,
        ) or re.search(
            r"\bno (?:approved )?(?:HINT )?(?:[A-Z][A-Za-z]+ )?(?:concept|term) (?:for|named|called) " + subject_pattern,
            message, re.IGNORECASE,
        )
        term = denied[1] if denied else message
    term = term.strip().strip("`\"'“”‘’").removeprefix(str(HINT))
    subject = " ".join(term.split()).casefold()
    categories = (category,) if category else vocabulary
    for name in categories:
        suffix = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).casefold()
        for identifier, label in vocabulary[name].items():
            label = " ".join(label.split()).casefold()
            if subject and subject in (identifier.casefold(), label, label.removesuffix(f" {suffix}")):
                return True
    return False


class _DraftRecovery:
    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics = diagnostics
        self.ids: dict[str, dict[str, str | None]] = {}
        self.generated_ids: set[str] = set()

    def add(self, kind: DiagnosticKind, path: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(kind=kind, path=path, message=message))

    def record(self, schema: dict, raw: dict, path: str = "") -> dict:
        name = schema["title"]
        fields = schema["properties"]
        required = set(schema.get("required", ()))
        if name == "Goal":
            # Canonical legacy input defaults to *all* tasks. Proposals must be explicit.
            required.add("required_tasks")
        draft: dict[str, Any] = {}
        for field in sorted(raw.keys() - fields.keys()):
            self.add("structural", path or "scenario", f"Ignored a field the canonical model does not accept: {field[:100]!r}.")
        for field, definition in fields.items():
            field_path = f"{path}.{field}" if path else field
            if field == "id":
                old_id = raw.get(field)
                if path and isinstance(old_id, str) and _IDENTIFIER_PATTERN.fullmatch(old_id):
                    draft[field] = old_id
                else:
                    draft[field] = str(uuid4())
                    self.generated_ids.add(draft[field])
                    if path and old_id is not None and (not isinstance(old_id, str) or old_id.strip()):
                        self.add("structural", field_path, "Assigned an editor ID because the model supplied an invalid one.")
                continue
            category = _CONCEPT_FIELDS.get(name, {}).get(field)
            definition = next((option for option in definition.get("anyOf", ()) if option.get("type") != "null"), definition)
            value = self.field(definition, raw.get(field), field_path, field in required, category)
            if value is not None:
                draft[field] = value
        return draft

    def field(self, schema: dict, value: Any, path: str, required: bool, category: str | None = None) -> Any:
        if "$ref" in schema:
            if isinstance(value, dict):
                if not required and not any(value.values()):
                    return None
                return self.record(_SCHEMA["$defs"][schema["$ref"].split("/")[-1]], value, path)
            if value is not None:
                self.add("structural", path, "Expected an object for this record.")
            if required:
                self.add("missing_information", path, "The interpretation did not supply this required record.")
                return self.record(_SCHEMA["$defs"][schema["$ref"].split("/")[-1]], {}, path)
            return None

        if schema.get("type") == "array":
            if not isinstance(value, list):
                if value is not None:
                    self.add("structural", path, "Expected a list for this field.")
                if not required:
                    return None
                value = []
            items = schema["items"]
            if len(value) < schema.get("minItems", int(required)):
                self.add("missing_information", path, "The interpretation supplied too few entries for this required list.")
            if "$ref" in items:
                return self.records(items, value, path)
            return [item for i, raw in enumerate(value)
                    if (item := self.field(items, raw, f"{path}.{i}", False, category)) is not None]

        if not isinstance(value, str) or not value.strip():
            if value is not None and not isinstance(value, str):
                self.add("structural", path, "Expected text for this field.")
            if required:
                self.add("missing_information", path, "The interpretation did not supply a value for this required field.")
                return ""
            return None
        if "enum" in schema and value not in schema["enum"]:
            self.add("structural", path, f"The proposed value {value[:100]!r} is outside the available options.")
            return "" if required else None
        if category and value not in _approved_terms()[category]:
            self.add("unsupported_vocabulary", path, f"Review {value[:150]!r} as a possible HINT {category} suggestion.")
            return "" if required else None
        return value if schema.get("pattern") == _IDENTIFIER_PATTERN.pattern else value.strip()

    def records(self, schema: dict, source: list, path: str) -> list[dict]:
        draft = []
        identifiers: dict[str, str | None] = {}
        counts = Counter(item["id"] for item in source if isinstance(item, dict) and isinstance(item.get("id"), str))
        for index, item in enumerate(source):
            if not isinstance(item, dict):
                self.add("structural", path, f"Skipped entry {index + 1} because it was not an object.")
                continue
            if not any(value for field, value in item.items() if field != "id"):
                continue
            record_path = f"{path}.{len(draft)}"
            record = self.field(schema, item, record_path, True)
            old_id = item.get("id")
            if isinstance(old_id, str) and old_id.strip():
                if counts[old_id] > 1:
                    self.add("structural", f"{record_path}.id", "Assigned a unique editor ID because the model used the same ID twice.")
                    record["id"] = str(uuid4())
                    self.generated_ids.add(record["id"])
                    identifiers[old_id] = None
                else:
                    identifiers[old_id] = record["id"]
            draft.append(record)
        self.ids[path] = identifiers
        return draft

    def resolve_reference(self, item: str, target: str, scenario: dict) -> str | None:
        ids = self.ids.get(target, {})
        if item in ids:
            return ids[item]
        # Match display labels or exact approved concepts within the target list.
        label = _LABEL_SEPARATOR.sub("-", item.strip().casefold())
        matches = [
            record["id"] for record in scenario.get(target, [])
            if item == record.get("concept") or label == _LABEL_SEPARATOR.sub("-", record.get("name", "").casefold())
        ]
        if len(matches) == 1 and matches[0] in self.generated_ids:
            return matches[0]
        return None

    def resolve_references(self, scenario: dict) -> None:
        for section, fields in _REFERENCE_FIELDS.items():
            records = scenario.get(section, [])
            if section == "goal":
                records = [records]
            for index, record in enumerate(records):
                path = section if section == "goal" else f"{section}.{index}"
                for field, target in fields.items():
                    value = record.get(field)
                    values = value if isinstance(value, list) else [value] if value else []
                    resolved = []
                    for item in values:
                        identifier = self.resolve_reference(item, target, scenario)
                        if identifier is None:
                            self.add("technical_validation", f"{path}.{field}",
                                     f"Reference {item[:100]!r} does not resolve to a unique entry in {target}.")
                        resolved.append(identifier if identifier is not None else item)
                    if resolved:
                        record[field] = resolved if isinstance(value, list) else resolved[0]


def assemble_interpretation(raw: Any, model: str, prompt_version: str, *, prompt_sha256: str) -> InterpretationResult:
    diagnostics: list[Diagnostic] = []
    recovery = _DraftRecovery(diagnostics)
    envelope = raw if isinstance(raw, dict) else {}
    notes = envelope.get("diagnostics")
    if isinstance(notes, list):
        for note in notes:
            if (not isinstance(note, dict) or not isinstance(note.get("kind"), str)
                    or note["kind"] not in _MODEL_DIAGNOSTICS or not isinstance(note.get("message"), str)
                    or not note["message"].strip()):
                recovery.add("structural", "scenario", "The model returned an unreadable interpretation diagnostic.")
                continue
            path = note.get("path") if isinstance(note.get("path"), str) else None
            if note["kind"] == "unsupported_vocabulary" and _reports_approved_term(note, path):
                continue
            if note["kind"] == "missing_information" and _is_managed_id_path(path):
                continue
            diagnostics.append(Diagnostic(kind=note["kind"], message=note["message"].strip()[:1000],
                                          path=path[:150] if path else None))
    else:
        recovery.add("structural", "scenario", "The model did not return a list of interpretation diagnostics.")

    source = envelope.get("scenario")
    if "scenario" not in envelope and _SCENARIO_FIELDS.intersection(envelope):
        recovery.add("structural", "scenario", "Recovered the candidate from an unexpected response layout.")
        source = {field: value for field, value in envelope.items() if field != "diagnostics"}
    scenario = None
    if isinstance(source, dict) and any(source.get(field) for field in _SCENARIO_FIELDS):
        scenario = recovery.record(_SCHEMA, source)
        recovery.resolve_references(scenario)
        try:
            Scenario.model_validate(scenario)
        except ValidationError as error:
            for issue in error.errors(include_url=False, include_context=False, include_input=False):
                path = ".".join(map(str, issue["loc"])) or "scenario"
                recovery.add("technical_validation", path, issue["msg"])
    elif source is not None or "scenario" not in envelope:
        recovery.add("structural", "scenario", "The model did not return a readable scenario object.")
    elif not diagnostics:
        recovery.add("missing_information", "scenario", "The model did not identify a usable candidate from this description.")

    unique = {(note.kind, note.path, note.message): note for note in diagnostics}
    return InterpretationResult(scenario=scenario, interpretation=InterpretationFindings(
        status="complete" if scenario is not None and not unique else "incomplete",
        model=model, prompt_version=prompt_version, prompt_sha256=prompt_sha256, diagnostics=list(unique.values()),
    ))
