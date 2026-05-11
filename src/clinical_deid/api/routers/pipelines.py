"""Pipeline CRUD — filesystem-backed.

Each pipeline is a JSON file in ``pipelines/``.  Create, list, update, delete
all operate on the filesystem — no database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from clinical_deid.api.auth import require_admin, require_admin_or_inference
from clinical_deid.api.schemas import (
    BlacklistMergeResponse,
    ComputeLabelsRequest,
    ComputeLabelsResponse,
    CreatePipelineRequest,
    LabelSpaceBundle,
    NerBuiltinInfo,
    ParseListFileResult,
    ParseListFilesResponse,
    PipelineDetail,
    PipeReadinessRequest,
    PipeReadinessResponse,
    PipeTypeInfo,
    PrefixLabelSpaceRequest,
    PrefixLabelSpaceResponse,
    RenamePipelineRequest,
    UpdatePipelineRequest,
    ValidatePipelineRequest,
    ValidatePipelineResponse,
)
from clinical_deid.config import get_settings
from clinical_deid.pipeline_store import (
    delete_pipeline,
    list_pipelines,
    load_pipeline_config,
    rename_pipeline,
    save_pipeline_config,
)
from clinical_deid.dictionary_store import DictionaryStore
from clinical_deid.pipes.regex_ner import builtin_regex_label_names
from clinical_deid.pipes.label_space import (
    enrich_pipeline_config_with_label_space,
    effective_output_labels_from_pipeline,
    try_effective_input_labels_before_step,
)
from clinical_deid.pipes.registry import (
    compute_base_labels,
    get_catalog_entry,
    get_label_space_bundle,
    load_pipeline,
    pipe_availability,
    pipe_check_ready,
    pipe_dependencies,
    registered_pipes,
    resolve_dynamic_options,
    validate_pipeline_config,
)
from clinical_deid.pipes.ui_schema import pipe_config_json_schema
from clinical_deid.pipes.whitelist.lists import parse_list_file

# Admin-only by default; inference keys may call ``POST .../pipe-types/{name}/labels`` only.
router = APIRouter(prefix="/pipelines", tags=["pipelines"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB per file


def _pipelines_dir():
    return get_settings().pipelines_dir


async def _read_upload(uf: UploadFile) -> str:
    raw = await uf.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file {uf.filename!r} exceeds {MAX_UPLOAD_BYTES // 1024} KB limit",
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422, detail=f"file {uf.filename!r} is not valid UTF-8"
        ) from exc


def _validate_config(config: dict) -> None:
    errors = validate_pipeline_config(config)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))


# ---------------------------------------------------------------------------
# Static routes — MUST be before /{pipeline_name}
# ---------------------------------------------------------------------------


@router.get("/pipe-types", response_model=list[PipeTypeInfo], dependencies=[require_admin])
def list_pipe_types() -> list[PipeTypeInfo]:
    """List all known pipe types and install status."""
    reg = registered_pipes()
    result: list[PipeTypeInfo] = []
    for entry in pipe_availability():
        config_schema = None
        config_cls = reg.get(entry["name"])
        if config_cls is not None:
            config_schema = pipe_config_json_schema(config_cls)
        if config_schema:
            # Always inject ui_pipe_type so bundle-mode detectors (whose default
            # base_labels may be empty until a model is selected) can still wire
            # the label-mapping widget to the per-pipe label-space bundle.
            _inject_base_labels(
                config_schema, entry.get("base_labels") or [], entry["name"]
            )
            _inject_dict_info(config_schema)
            _inject_dynamic_options(config_schema)
        result.append(PipeTypeInfo(**entry, config_schema=config_schema))
    return result


_LABEL_AWARE_WIDGETS = {"label_space", "label_regex", "unified_label", "whitelist_label"}


def _inject_base_labels(
    config_schema: dict, base_labels: list[str], pipe_type: str
) -> None:
    """Embed ``ui_base_labels``, ``ui_pipe_type``, and (for unified_label)
    ``ui_builtin_patterns`` into any label-aware property schema so the
    frontend widget can read them directly."""
    from clinical_deid.pipes.regex_ner import BUILTIN_REGEX_PATTERNS

    for prop in config_schema.get("properties", {}).values():
        if not isinstance(prop, dict):
            continue
        widget = prop.get("ui_widget")
        if widget not in _LABEL_AWARE_WIDGETS:
            continue
        prop["ui_base_labels"] = base_labels
        prop["ui_pipe_type"] = pipe_type
        if widget == "unified_label":
            prop["ui_builtin_patterns"] = {
                label: pat for label, pat in BUILTIN_REGEX_PATTERNS.items()
            }
        if widget == "whitelist_label":
            store = DictionaryStore(get_settings().dictionaries_dir)
            wl_dicts = store.list_dictionaries(kind="whitelist")
            prop["ui_whitelist_dictionaries"] = [
                {
                    "name": d.name,
                    "filename": d.filename,
                    "term_count": d.term_count,
                }
                for d in wl_dicts
            ]


def _inject_dict_info(config_schema: dict) -> None:
    """Inject dictionary metadata into blacklist_dicts widgets."""
    for prop in config_schema.get("properties", {}).values():
        if not isinstance(prop, dict):
            continue
        if prop.get("ui_widget") == "blacklist_dicts":
            store = DictionaryStore(get_settings().dictionaries_dir)
            bl_dicts = store.list_dictionaries(kind="blacklist")
            prop["ui_blacklist_dicts"] = [
                {
                    "name": d.name,
                    "filename": d.filename,
                    "term_count": d.term_count,
                }
                for d in bl_dicts
            ]


def _inject_dynamic_options(config_schema: dict) -> None:
    """Populate ``enum`` for properties that declare a ``ui_options_source``.

    Resolvers are looked up via the catalog (``PipeCatalogEntry.dynamic_options_fns``)
    so each pipe owns its own option sources — no central registry to update when
    adding a new detector.
    """
    for prop in config_schema.get("properties", {}).values():
        if not isinstance(prop, dict):
            continue
        source = prop.get("ui_options_source")
        if not source:
            continue
        options = resolve_dynamic_options(source)
        if options:
            prop["enum"] = options


@router.post(
    "/pipe-types/{name}/labels",
    response_model=ComputeLabelsResponse,
    dependencies=[require_admin_or_inference],
)
def compute_pipe_labels(name: str, body: ComputeLabelsRequest | None = None) -> ComputeLabelsResponse:
    """Compute the effective base labels for a pipe type given optional config.

    Returns post-``entity_map`` canonical labels (the keys of ``label_mapping``).  For
    detectors with ``label_source == 'bundle'``, prefer the bundle endpoint instead —
    it lets the client switch models without a server round-trip.
    """
    config = body.config if body else None
    labels = compute_base_labels(name, config)
    return ComputeLabelsResponse(labels=labels)


@router.post(
    "/pipe-types/{name}/readiness",
    response_model=PipeReadinessResponse,
    dependencies=[require_admin],
)
def pipe_readiness(
    name: str, body: PipeReadinessRequest | None = None
) -> PipeReadinessResponse:
    """Check whether a pipe type can actually run, given its current config.

    Combines the catalog's ``check_ready`` hook (runtime-only deps like a
    Docker sidecar or downloaded weights) with ``dependencies_fn`` (config-
    dependent deps like a referenced model name). The response is shaped for
    the playground rail to render a status badge per pipe.
    """
    if get_catalog_entry(name) is None:
        raise HTTPException(status_code=404, detail=f"unknown pipe type {name!r}")
    config = body.config if body else None
    runtime = pipe_check_ready(name)
    missing = pipe_dependencies(name, config) if runtime["installed"] else []
    ok = bool(runtime["installed"] and runtime["ready"] and not missing)
    return PipeReadinessResponse(
        installed=runtime["installed"],
        ok=ok,
        missing=missing,
        ready_details=runtime["ready_details"],
        install_hint=runtime["install_hint"],
    )


@router.post(
    "/prefix-label-space",
    response_model=PrefixLabelSpaceResponse,
    dependencies=[require_admin],
)
def prefix_label_space(body: PrefixLabelSpaceRequest) -> PrefixLabelSpaceResponse:
    """Symbolic span labels entering the pipe at *step_index* (for ``label_mapper`` UI hints)."""
    labels, err = try_effective_input_labels_before_step(body.config, body.step_index)
    if labels is None:
        return PrefixLabelSpaceResponse(labels=[], error=err)
    return PrefixLabelSpaceResponse(labels=labels, error=None)


@router.get(
    "/pipe-types/{name}/label-space-bundle",
    response_model=LabelSpaceBundle,
    dependencies=[require_admin],
)
def pipe_label_space_bundle(name: str) -> LabelSpaceBundle:
    """Return the per-model label space for a detector that declares ``label_source = bundle``.

    The catalog routes the request to that pipe's ``label_space_bundle_fn``.  The
    response shape is identical for every detector — frontend reads
    ``PipeTypeInfo.bundle_key_semantics`` to know whether keys are raw NER tags
    or Presidio entity names.
    """
    bundle = get_label_space_bundle(name)
    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail=f"pipe {name!r} does not expose a label-space bundle",
        )
    return LabelSpaceBundle(**bundle)


@router.get("/ner/builtins", response_model=NerBuiltinInfo, dependencies=[require_admin])
def ner_builtins() -> NerBuiltinInfo:
    return NerBuiltinInfo(
        regex_labels=builtin_regex_label_names(),
        whitelist_labels=[],
    )


@router.post("/whitelist/parse-lists", response_model=ParseListFilesResponse, dependencies=[require_admin])
async def whitelist_parse_lists(
    files: Annotated[list[UploadFile], File()],
    labels: Annotated[list[str], Form()],
) -> ParseListFilesResponse:
    if not files:
        raise HTTPException(status_code=422, detail="at least one file is required")
    if len(files) != len(labels):
        raise HTTPException(
            status_code=422,
            detail=f"expected same number of files and labels (got {len(files)} files, {len(labels)} labels)",
        )
    results: list[ParseListFileResult] = []
    for uf, label in zip(files, labels, strict=True):
        text = await _read_upload(uf)
        terms = parse_list_file(text, filename=uf.filename or "")
        results.append(
            ParseListFileResult(
                label=label.strip().upper(),
                filename=uf.filename or "",
                terms=terms,
                count=len(terms),
            )
        )
    return ParseListFilesResponse(results=results)


@router.post("/blacklist/parse-wordlists", response_model=BlacklistMergeResponse, dependencies=[require_admin])
async def blacklist_parse_wordlists(
    files: Annotated[list[UploadFile], File()],
) -> BlacklistMergeResponse:
    if not files:
        raise HTTPException(status_code=422, detail="at least one file is required")
    merged: set[str] = set()
    names: list[str] = []
    for uf in files:
        text = await _read_upload(uf)
        for t in parse_list_file(text, filename=uf.filename or ""):
            u = t.strip()
            if u:
                merged.add(u)
        names.append(uf.filename or "")
    out = sorted(merged, key=lambda x: x.casefold())
    return BlacklistMergeResponse(terms=out, count=len(out), source_files=names)


# ---------------------------------------------------------------------------
# Pipeline CRUD — filesystem
# ---------------------------------------------------------------------------


@router.post("", response_model=PipelineDetail, status_code=201, dependencies=[require_admin])
def create_pipeline(body: CreatePipelineRequest) -> PipelineDetail:
    """Create a named pipeline (writes JSON file)."""
    _validate_config(body.config)
    config_to_save = enrich_pipeline_config_with_label_space(body.config)
    pdir = _pipelines_dir()
    path = pdir / f"{body.name}.json"
    if path.exists():
        raise HTTPException(status_code=409, detail="pipeline name already exists")
    save_pipeline_config(pdir, body.name, config_to_save)
    return PipelineDetail(name=body.name, config=config_to_save)


@router.get("", response_model=list[PipelineDetail], dependencies=[require_admin])
def list_all_pipelines(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[PipelineDetail]:
    """List saved pipelines (paginated)."""
    pipelines = list_pipelines(_pipelines_dir())
    pipelines = pipelines[offset : offset + limit]
    return [PipelineDetail(name=p.name, config=p.config) for p in pipelines]


@router.get("/{pipeline_name}", response_model=PipelineDetail, dependencies=[require_admin])
def get_pipeline(pipeline_name: str) -> PipelineDetail:
    try:
        config = load_pipeline_config(_pipelines_dir(), pipeline_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PipelineDetail(name=pipeline_name, config=config)


@router.put("/{pipeline_name}", response_model=PipelineDetail, dependencies=[require_admin])
def update_pipeline(pipeline_name: str, body: UpdatePipelineRequest) -> PipelineDetail:
    pdir = _pipelines_dir()
    path = pdir / f"{pipeline_name}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"pipeline {pipeline_name!r} not found")
    if body.config is not None:
        _validate_config(body.config)
        config_to_save = enrich_pipeline_config_with_label_space(body.config)
        save_pipeline_config(pdir, pipeline_name, config_to_save)
    config = load_pipeline_config(pdir, pipeline_name)
    return PipelineDetail(name=pipeline_name, config=config)


@router.delete("/{pipeline_name}", status_code=204, dependencies=[require_admin])
def delete_pipeline_endpoint(pipeline_name: str) -> None:
    try:
        delete_pipeline(_pipelines_dir(), pipeline_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{pipeline_name}/rename",
    response_model=PipelineDetail,
    dependencies=[require_admin],
)
def rename_pipeline_endpoint(pipeline_name: str, body: RenamePipelineRequest) -> PipelineDetail:
    pdir = _pipelines_dir()
    try:
        rename_pipeline(pdir, pipeline_name, body.new_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    config = load_pipeline_config(pdir, body.new_name)
    return PipelineDetail(name=body.new_name, config=config)


@router.post("/{pipeline_name}/validate", response_model=ValidatePipelineResponse, dependencies=[require_admin])
def validate_pipeline(pipeline_name: str, body: ValidatePipelineRequest) -> ValidatePipelineResponse:
    pdir = _pipelines_dir()
    path = pdir / f"{pipeline_name}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"pipeline {pipeline_name!r} not found")
    config = body.config if body.config else load_pipeline_config(pdir, pipeline_name)
    try:
        pl = load_pipeline(config)
        labels = sorted(effective_output_labels_from_pipeline(pl))
        return ValidatePipelineResponse(
            valid=True,
            output_label_space=labels,
            output_label_space_updated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        return ValidatePipelineResponse(valid=False, error=str(exc))
