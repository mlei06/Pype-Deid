"""End-to-end training orchestration."""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

from pypedeid.training.config import TrainingConfig

logger = logging.getLogger(__name__)


def _detect_device(explicit: str | None) -> str:
    """Return the device string to use, auto-detecting when explicit is None."""
    if explicit is not None:
        return explicit
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def run_training(
    cfg: TrainingConfig,
    *,
    models_dir: Path,
    corpora_dir: Path,
) -> Path:
    """Run end-to-end training. Returns the final model directory path."""
    # Step 1: check deps
    try:
        from transformers import (
            AutoModelForTokenClassification,
            AutoTokenizer,
            DataCollatorForTokenClassification,
            EarlyStoppingCallback,
            Trainer,
            TrainingArguments,
            set_seed,
        )
    except ImportError as exc:
        raise ImportError(
            "Training requires additional dependencies. Install with:\n"
            "  pip install 'pypedeid[train]'"
        ) from exc

    from pypedeid.training.base_model import resolve_base_model
    from pypedeid.training.datasets import (
        _prepare_training_units,
        build_hf_datasets,
        tokenize_and_align,
    )
    from pypedeid.training.errors import OutputExists, TrainingError
    from pypedeid.training.manifest import write_manifest_v2
    from pypedeid.training.metrics import build_metrics_report, make_compute_metrics

    # Step 2: guard output directory
    final_dir = models_dir / "huggingface" / cfg.output_name
    staging_dir = models_dir / "huggingface" / f"{cfg.output_name}.tmp.{os.getpid()}"
    staging_model_dir = staging_dir / "model"
    staging_checkpoints_dir = staging_dir / "checkpoints"

    if final_dir.exists() and not cfg.overwrite:
        raise OutputExists(
            f"Output directory {final_dir} already exists. "
            "Pass overwrite=True (or --overwrite on the CLI) to replace it."
        )

    staging_model_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 3: resolve base model
        resolved = resolve_base_model(cfg.base_model, models_dir)

        # Step 5: detect device (done before loading tokenizer/model so we can print it)
        device = _detect_device(cfg.device)
        print(f"\nDevice: {device}")
        logger.info("Training device: %s", device)

        # Step 6: load tokenizer
        tokenizer = AutoTokenizer.from_pretrained(resolved.tokenizer_source, use_fast=True)

        # Step 4: build datasets (tokenizer needed for alignment)
        train_ds, eval_ds, bio_labels = build_hf_datasets(cfg, corpora_dir, tokenizer)

        train_doc_count = len(train_ds)
        eval_doc_count = len(eval_ds) if eval_ds is not None else 0

        label2id = {label: i for i, label in enumerate(bio_labels)}
        id2label = {i: label for i, label in enumerate(bio_labels)}
        num_labels = len(bio_labels)

        # Detect head reinitialisation
        head_reinitialised = False
        if resolved.kind == "local" and resolved.saved_label_space:
            parent_bio_count = len(resolved.saved_label_space) * 2 + 1
            if parent_bio_count != num_labels:
                head_reinitialised = True
                msg = (
                    f"classifier head will be reinitialised: parent had "
                    f"{parent_bio_count} BIO labels, new config has {num_labels}."
                )
                logger.warning(msg)
                print(f"\n{'=' * 60}\nWARNING: {msg}\n{'=' * 60}\n")

        # Load model
        model = AutoModelForTokenClassification.from_pretrained(
            resolved.source,
            num_labels=num_labels,
            id2label=id2label,
            label2id=label2id,
            ignore_mismatched_sizes=True,
        )

        # Step 7: freeze encoder
        if cfg.freeze_encoder:
            has_classifier = any(
                name.startswith("classifier") for name, _ in model.named_parameters()
            )
            if not has_classifier:
                raise TrainingError(
                    "freeze_encoder=True but model has no 'classifier' top-level module. "
                    "Expected AutoModelForTokenClassification convention."
                )
            frozen = 0
            for name, param in model.named_parameters():
                if not name.startswith("classifier"):
                    param.requires_grad = False
                    frozen += 1
            logger.info("Froze %d parameter groups; classifier remains trainable.", frozen)

        # Step 8: seed
        set_seed(cfg.hyperparams.seed)

        # Step 9: build TrainingArguments
        import inspect
        import math

        hp = cfg.hyperparams
        eval_strategy = "epoch" if eval_ds is not None else "no"

        # warmup_ratio was deprecated in transformers 5.x; compute warmup_steps explicitly
        ta_params = inspect.signature(TrainingArguments.__init__).parameters
        steps_per_epoch = math.ceil(len(train_ds) / hp.per_device_train_batch_size)
        total_steps_estimate = math.ceil(steps_per_epoch * hp.epochs)
        warmup_steps = int(total_steps_estimate * hp.warmup_ratio)

        ta_kwargs: dict = dict(
            output_dir=str(staging_checkpoints_dir),
            num_train_epochs=hp.epochs,
            learning_rate=hp.learning_rate,
            per_device_train_batch_size=hp.per_device_train_batch_size,
            per_device_eval_batch_size=hp.per_device_eval_batch_size,
            weight_decay=hp.weight_decay,
            gradient_accumulation_steps=hp.gradient_accumulation_steps,
            fp16=hp.fp16,
            bf16=hp.bf16,
            gradient_checkpointing=hp.gradient_checkpointing,
            logging_steps=hp.logging_steps,
            eval_strategy=eval_strategy,
            save_strategy=eval_strategy,
            load_best_model_at_end=(eval_ds is not None),
            seed=hp.seed,
            report_to="none",
        )
        # Prefer warmup_steps (transformers v5.2+ deprecates warmup_ratio)
        if "warmup_steps" in ta_params:
            ta_kwargs["warmup_steps"] = warmup_steps
        elif "warmup_ratio" in ta_params:
            ta_kwargs["warmup_ratio"] = hp.warmup_ratio

        if hp.eval_steps is not None:
            ta_kwargs["eval_steps"] = hp.eval_steps
        if device == "cpu":
            if "use_cpu" in ta_params:
                ta_kwargs["use_cpu"] = True
            else:
                ta_kwargs["no_cuda"] = True

        training_args = TrainingArguments(**ta_kwargs)

        # Step 10: build Trainer
        callbacks = []
        if hp.early_stopping_patience is not None and eval_ds is not None:
            callbacks.append(
                EarlyStoppingCallback(early_stopping_patience=hp.early_stopping_patience)
            )

        # tokenizer was renamed to processing_class in transformers 5.x
        trainer_params = inspect.signature(Trainer.__init__).parameters
        tokenizer_kwarg = "processing_class" if "processing_class" in trainer_params else "tokenizer"

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_ds,
            eval_dataset=eval_ds,
            **{tokenizer_kwarg: tokenizer},
            data_collator=DataCollatorForTokenClassification(tokenizer=tokenizer),
            compute_metrics=make_compute_metrics(id2label),
            callbacks=callbacks or None,
        )

        # Step 11: train
        t0 = time.perf_counter()
        train_result = trainer.train()
        train_runtime_sec = time.perf_counter() - t0
        total_steps = train_result.global_step

        # Step 12: final eval + full metrics
        metrics: dict = {}
        if eval_ds is not None:
            pred_output = trainer.predict(eval_ds)
            metrics = build_metrics_report(
                pred_output.predictions, pred_output.label_ids, id2label
            )

        # Step 12b: held-out test set evaluation
        test_metrics: dict | None = None
        test_doc_count = 0
        if cfg.test_dataset is not None:
            from pypedeid.dataset_store import load_dataset_documents
            test_docs = load_dataset_documents(corpora_dir, cfg.test_dataset)
            test_doc_count = len(test_docs)
            if test_docs:
                if cfg.label_remap:
                    from pypedeid.training.datasets import _remap_doc
                    test_docs = [_remap_doc(doc, cfg.label_remap) for doc in test_docs]
                test_units = _prepare_training_units(test_docs, cfg.segmentation)
                test_encoded = [
                    tokenize_and_align(unit, tokenizer, label2id, cfg.hyperparams.max_length)
                    for unit in test_units
                ]
                import datasets as hf_datasets
                test_ds = hf_datasets.Dataset.from_list(test_encoded)
                print(f"\nEvaluating on test set ({test_doc_count} documents)...")
                test_pred = trainer.predict(test_ds)
                test_metrics = build_metrics_report(
                    test_pred.predictions, test_pred.label_ids, id2label
                )
                overall = test_metrics.get("overall", {})
                print(
                    f"Test — P: {overall.get('precision', 0):.4f}  "
                    f"R: {overall.get('recall', 0):.4f}  "
                    f"F1: {overall.get('f1', 0):.4f}"
                )

        # Step 13: save model + tokenizer
        trainer.save_model(str(staging_model_dir))
        tokenizer.save_pretrained(str(staging_model_dir))

        # Step 14: copy Trainer artifacts
        training_artifact_dir = staging_model_dir / "training"
        training_artifact_dir.mkdir(exist_ok=True)
        if staging_checkpoints_dir.exists():
            checkpoints = sorted(staging_checkpoints_dir.iterdir())
            if checkpoints:
                last_ckpt = checkpoints[-1]
                for artifact in ("trainer_state.json", "training_args.bin"):
                    src = last_ckpt / artifact
                    if src.exists():
                        shutil.copy2(src, training_artifact_dir / artifact)

        # Step 15: delete checkpoints
        if staging_checkpoints_dir.exists():
            shutil.rmtree(staging_checkpoints_dir)

        # Step 16: write manifest
        user_facing_labels = sorted(label[2:] for label in bio_labels if label.startswith("B-"))
        base_model_display = (
            cfg.base_model if resolved.kind == "hub" else resolved.source
        )
        write_manifest_v2(
            staging_model_dir,
            name=cfg.output_name,
            base_model=base_model_display,
            parent_model_name=resolved.parent_model_name,
            tokenizer_source=resolved.tokenizer_source,
            labels=user_facing_labels,
            bio_labels=bio_labels,
            training_config=cfg.model_dump(mode="json"),
            train_dataset=cfg.train_dataset,
            train_documents=train_doc_count,
            eval_dataset=cfg.eval_dataset,
            eval_fraction=cfg.eval_fraction,
            eval_documents=eval_doc_count,
            seed=cfg.hyperparams.seed,
            device_used=device,
            total_steps=total_steps,
            train_runtime_sec=train_runtime_sec,
            head_reinitialised=head_reinitialised,
            metrics=metrics,
            test_dataset=cfg.test_dataset,
            test_documents=test_doc_count,
            test_metrics=test_metrics,
            segmentation=cfg.segmentation,
        )

        # Step 17: atomic promotion
        if final_dir.exists():
            shutil.rmtree(final_dir)
        shutil.move(str(staging_model_dir), str(final_dir))
        shutil.rmtree(staging_dir, ignore_errors=True)

        logger.info("Training complete. Model saved to %s", final_dir)
        print(f"\nModel saved to: {final_dir}")
        return final_dir

    except Exception:
        logger.error(
            "Training failed. Staging directory preserved for debugging: %s", staging_dir
        )
        raise
