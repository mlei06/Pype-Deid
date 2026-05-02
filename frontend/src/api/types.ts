/* ------------------------------------------------------------------ */
/* Mirrors of backend Pydantic schemas                                */
/* ------------------------------------------------------------------ */

// Output mode for process/redact/scrub endpoints
export type OutputMode = 'annotated' | 'redacted' | 'surrogate';

/** ``GET /health`` — also exposes active pack names for UIs. */
export interface HealthResponse {
  status: string;
  label_space_name: string;
  risk_profile_name: string;
  /** Present when the same ``X-API-Key`` the UI uses is sent; use to gate admin-only actions. */
  api_key_scope?: 'admin' | 'inference' | null;
}

// Domain
export interface EntitySpanResponse {
  start: number;
  end: number;
  label: string;
  text: string;
  confidence: number | null;
  source: string | null;
}

export interface ProcessRequest {
  text: string;
  request_id?: string;
}

export interface TraceFrame {
  path: string;
  stage: string;
  pipe_type: string;
  branch_index: number | null;
  extra: Record<string, unknown>;
  document?: {
    document: { id: string; text: string; metadata: Record<string, unknown> };
    spans: { start: number; end: number; label: string; confidence: number | null; source: string | null }[];
  };
  elapsed_ms?: number;
}

export interface ProcessResponse {
  request_id: string;
  original_text: string;
  redacted_text: string;
  spans: EntitySpanResponse[];
  pipeline_name: string;
  processing_time_ms: number;
  intermediary_trace: TraceFrame[] | null;
}

export interface SavedInferenceRunSummary {
  id: string;
  pipeline_name: string;
  saved_at: string;
  text_preview: string;
  span_count: number;
}

export interface SavedInferenceRunDetail extends ProcessResponse {
  id: string;
  saved_at: string;
}

// Pipelines
export interface PipeStep {
  type: string;
  config?: Record<string, unknown>;
}

export interface PipelineConfig {
  pipes: PipeStep[];
  description?: string;
  /** Cached symbolic output labels (set on save by the API). */
  output_label_space?: string[];
  output_label_space_updated_at?: string;
}

export interface PipelineDetail {
  name: string;
  config: PipelineConfig;
}

export interface CreatePipelineRequest {
  name: string;
  config: PipelineConfig;
}

export type LabelSource = 'none' | 'compute' | 'bundle' | 'both';
export type BundleKeySemantics = 'ner_raw' | 'presidio_entity';

export interface PipeTypeInfo {
  name: string;
  description: string;
  role: string;
  extra: string | null;
  install_hint: string;
  installed: boolean;
  config_schema: Record<string, unknown> | null;
  base_labels: string[] | null;
  /** How the playground discovers this pipe's label space. */
  label_source: LabelSource;
  /** For ``label_source: 'bundle'``: how to interpret ``labels_by_model`` keys. */
  bundle_key_semantics: BundleKeySemantics | null;
  deprecated?: boolean;
}

export interface ValidatePipelineResponse {
  valid: boolean;
  error: string | null;
  output_label_space?: string[] | null;
  output_label_space_updated_at?: string | null;
}

// Evaluation
export interface MatchMetrics {
  precision: number;
  recall: number;
  f1: number;
  tp: number;
  fp: number;
  fn: number;
}

export interface SaveSampleAsSpec {
  dataset_name: string;
  description?: string;
}

export interface EvalRunRequest {
  pipeline_name: string;
  dataset_path?: string;
  dataset_name?: string;
  /** Only documents with metadata.split in this list (optional). */
  dataset_splits?: string[];
  /** Full (split-filtered) corpus vs random subset. Defaults to "full". */
  eval_mode?: 'full' | 'sample';
  /** Required when eval_mode === "sample". */
  sample_size?: number;
  /** Integer → deterministic; omit → server draws a fresh seed and returns it. */
  sample_seed?: number;
  /** If set with eval_mode === "sample", persist the sampled docs as a new dataset. */
  save_sample_as?: SaveSampleAsSpec;
  /** Adds `metrics.document_level` to the response only (not persisted). */
  include_per_document?: boolean;
  /** Implies `include_per_document`; also includes text + gold/pred spans per doc. */
  include_per_document_spans?: boolean;
  /** For this run only, remap predicted labels before scoring against gold labels. */
  eval_pred_label_remap?: Record<string, string>;
}

export interface EvalSpanLite {
  start: number;
  end: number;
  label: string;
}

export interface EvalPerDocumentItem {
  document_id: string;
  metrics: Record<string, MatchMetrics>;
  risk_weighted_recall: number;
  false_positive_count: number;
  false_negative_count: number;
  text?: string;
  gold_spans?: EvalSpanLite[];
  pred_spans?: EvalSpanLite[];
  false_positives?: EvalSpanLite[];
  false_negatives?: EvalSpanLite[];
}

export interface EvalSampleInfo {
  eval_mode: 'sample';
  sample_size: number;
  sample_seed_used: number;
  sample_of_total: number;
  /** Set when save_sample_as succeeded on this run. */
  saved_dataset_name?: string;
}

export interface EvalRunSummary {
  id: string;
  pipeline_name: string;
  dataset_source: string;
  document_count: number;
  strict_f1: number;
  risk_weighted_recall: number;
  created_at: string;
}

export interface LabelMetricsDetail {
  strict: MatchMetrics;
  partial_overlap: MatchMetrics;
  token_level: MatchMetrics;
  support: number;
}

export interface LabelLeakage {
  label: string;
  gold_count: number;
  leaked_count: number;
  leakage_rate: number;
}

export interface LeakedSpan {
  label: string;
  original_text: string;
  found_at: number[];
}

export interface RedactionMetrics {
  gold_phi_count: number;
  leaked_phi_count: number;
  leakage_rate: number;
  redaction_recall: number;
  over_redaction_chars: number;
  original_length: number;
  redacted_length: number;
  per_label: LabelLeakage[];
  leaked_spans: LeakedSpan[];
}

export interface MacroAverage {
  precision: number;
  recall: number;
  f1: number;
  label_count: number;
}

export interface MacroMetrics {
  strict: MacroAverage;
  partial_overlap: MacroAverage;
  token_level: MacroAverage;
}

export interface EvalRunDetail extends EvalRunSummary {
  metrics: {
    overall: Record<string, MatchMetrics>;
    /** Unweighted mean of per-label P/R/F1. Absent on older eval runs. */
    macro?: MacroMetrics;
    per_label: Record<string, LabelMetricsDetail>;
    risk_weighted_recall: number;
    label_confusion: Record<string, Record<string, number>>;
    has_redaction?: boolean;
    redaction?: RedactionMetrics;
    sample?: EvalSampleInfo;
    /** Present only when the request enabled include_per_document[_spans]. */
    document_level?: EvalPerDocumentItem[];
    document_level_truncated?: boolean;
    document_level_total?: number;
    document_level_includes_spans?: boolean;
    /** Echoes eval-time mapping when eval_pred_label_remap was provided. */
    eval_pred_label_remap?: Record<string, string>;
  };
}

// Deploy config
export interface ModeEntry {
  pipeline: string;
  description: string;
}

export interface DeployConfig {
  modes: Record<string, ModeEntry>;
  default_mode: string | null;
  allowed_pipelines: string[] | null;
}

export interface ModeHealth {
  name: string;
  pipeline: string;
  description: string;
  available: boolean;
  missing: string[];
}

export interface DeployHealthResponse {
  modes: ModeHealth[];
  default_mode: string | null;
}

// Audit
export interface AuditLogSummary {
  id: string;
  timestamp: string;
  user: string;
  command: string;
  pipeline_name: string;
  source: string;
  doc_count: number;
  span_count: number;
  duration_seconds: number;
}

export interface AuditLogDetail extends AuditLogSummary {
  pipeline_config: Record<string, unknown>;
  dataset_source: string;
  error_count: number;
  metrics: Record<string, unknown>;
  notes: string;
  client_id: string;
  output_mode: string;
  service_type: string;
}

// Redact endpoint
export interface RedactRequest {
  text: string;
  spans: { start: number; end: number; label: string }[];
  output_mode: OutputMode;
  surrogate_seed?: number | null;
  surrogate_consistency?: boolean;
}

export interface RedactResponse {
  output_text: string;
  output_mode: OutputMode;
  span_count: number;
}

// Scrub endpoint
export interface ScrubRequest {
  text: string;
  mode?: string | null;
  output_mode?: OutputMode;
  request_id?: string;
}

export interface ScrubResponse {
  text: string;
  pipeline_used: string;
  output_mode: OutputMode;
  span_count: number;
  processing_time_ms: number;
}

export interface AuditStats {
  total_requests: number;
  avg_duration_seconds: number;
  total_spans_detected: number;
  top_pipelines: { pipeline_name: string; request_count: number }[];
  source_breakdown: Record<string, number>;
}

// Datasets
export type DatasetFormat = 'jsonl';

export interface DatasetSummary {
  name: string;
  description: string;
  data_path: string;
  format: DatasetFormat;
  document_count: number;
  total_spans: number;
  labels: string[];
  created_at: string;
}

export interface DatasetDetail extends DatasetSummary {
  analytics: DatasetAnalytics;
  metadata: Record<string, unknown>;
  /** Documents per `metadata.split`; missing/invalid split → `"(none)"`. */
  split_document_counts?: Record<string, number>;
  has_split_metadata?: boolean;
}

export interface PreviewCorpusLabelsRequest {
  path: string;
}

export interface PreviewCorpusLabelsResponse {
  labels: string[];
  document_count: number;
  resolved_path: string;
}

export interface DatasetAnalytics {
  document_count: number;
  total_spans: number;
  unique_label_count: number;
  label_counts: Record<string, number>;
  character_length: NumericSummary;
  token_count_estimate: NumericSummary;
  spans_per_document: NumericSummary;
  documents_by_span_count: Record<string, number>;
  span_character_length: NumericSummary;
  span_length_histogram: Record<string, number>;
  documents_with_overlapping_spans: number;
  overlapping_span_pairs: number;
  label_cooccurrence: Record<string, number>;
}

export interface NumericSummary {
  mean: number;
  min: number;
  max: number;
  std: number;
}

export interface DocumentPreview {
  document_id: string;
  text_preview: string;
  span_count: number;
  labels: string[];
  /** Present when the API includes it; may be omitted in older responses. */
  split?: string | null;
}

export interface DatasetPreviewResponse {
  items: DocumentPreview[];
  total: number;
}

export interface DocumentDetail {
  document_id: string;
  text: string;
  metadata: Record<string, unknown>;
  spans: { start: number; end: number; label: string; confidence?: number | null; source?: string | null }[];
}

export type TrainingExportFormat = 'conll' | 'spacy' | 'huggingface' | 'brat' | 'jsonl';

export interface UpdateDocumentRequest {
  spans: { start: number; end: number; label: string; confidence?: number | null; source?: string | null }[];
  text?: string | null;
}

export interface ExportTrainingRequest {
  format: TrainingExportFormat;
  filename?: string;
}

export interface ExportTrainingResponse {
  path: string;
  format: string;
  document_count: number;
  total_spans: number;
}

export interface RegisterDatasetRequest {
  name: string;
  data_path: string;
  format: DatasetFormat;
  description?: string;
}

export interface ImportBratRequest {
  name: string;
  brat_path: string;
  description?: string;
}

export interface ImportSourceCandidate {
  label: string;
  data_path: string;
  suggested_format: DatasetFormat;
}

export interface ImportSourcesResponse {
  corpora_root: string;
  candidates: ImportSourceCandidate[];
}

export type BratImportKind = 'brat-dir' | 'brat-corpus';

export interface BratImportCandidate {
  label: string;
  data_path: string;
  kind: BratImportKind;
}

export interface BratImportSourcesResponse {
  corpora_root: string;
  candidates: BratImportCandidate[];
}

export interface RefreshResultEntry {
  name: string;
  status: 'ok' | 'error';
  error: string | null;
}

export interface ComposeRequest {
  output_name: string;
  source_datasets: string[];
  strategy: 'merge' | 'interleave' | 'proportional';
  weights?: number[];
  target_documents?: number;
  seed?: number;
  shuffle?: boolean;
  description?: string;
}

export type TransformMode = 'full' | 'schema' | 'sampling' | 'partitioning';

export interface TransformRequest {
  source_dataset: string;
  /** Required when in_place is false. Ignored when in_place is true. */
  output_name?: string;
  /** When true, overwrite the source dataset; output_name is ignored. */
  in_place?: boolean;
  /** Only include documents whose metadata.split is in this list. */
  source_splits?: string[];
  drop_labels?: string[];
  keep_labels?: string[];
  label_mapping?: Record<string, string>;
  target_documents?: number;
  boost_label?: string;
  boost_extra_copies?: number;
  resplit?: Record<string, number>;
  strip_splits?: boolean;
  seed?: number;
  description?: string;
  transform_mode?: TransformMode;
  resplit_shuffle?: boolean;
  /** Strip split metadata on targeted documents before re-partitioning. */
  flatten_target_splits?: boolean;
}

export interface DatasetLabelFrequency {
  label: string;
  count: number;
}

export interface DatasetSchemaResponse {
  dataset: string;
  document_count: number;
  total_spans: number;
  labels: DatasetLabelFrequency[];
}

export interface TransformPreviewRequest {
  source_dataset: string;
  /** New dataset (default) vs in-place; must match the transform you will run. */
  in_place?: boolean;
  source_splits?: string[];
  drop_labels?: string[];
  keep_labels?: string[];
  label_mapping?: Record<string, string>;
  target_documents?: number;
  boost_label?: string;
  boost_extra_copies?: number;
  resplit?: Record<string, number>;
  strip_splits?: boolean;
  seed?: number;
  transform_mode?: TransformMode;
  resplit_shuffle?: boolean;
  flatten_target_splits?: boolean;
}

export interface TransformPreviewResponse {
  source_document_count: number;
  source_span_count: number;
  spans_dropped_by_filter: number;
  spans_kept_after_filter: number;
  spans_renamed: number;
  projected_document_count: number;
  projected_span_count: number;
  split_document_counts: Record<string, number> | null;
  /** Documents not selected by source_splits (if any), unchanged in a full transform. */
  untouched_document_count?: number;
  conflicts: string[];
}

export interface GenerateRequest {
  output_name: string;
  count: number;
  phi_types?: string[];
  special_rules?: string;
  description?: string;
}

// Dictionaries
export interface DictionaryInfo {
  kind: 'whitelist' | 'blacklist';
  label: string | null;
  name: string;
  filename: string;
  term_count: number;
}

export interface DictionaryPreview {
  kind: string;
  label: string | null;
  name: string;
  term_count: number;
  sample_terms: string[];
  file_size_bytes: number;
}

export interface DictionaryTermsPage {
  terms: string[];
  total: number;
  offset: number;
  limit: number;
  search: string | null;
}

export interface DictionaryUploadResult {
  info: DictionaryInfo;
  message: string;
}
