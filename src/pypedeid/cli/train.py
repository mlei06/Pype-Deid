"""``train`` subgroup — fine-tune HF encoder models."""

from __future__ import annotations

import json
from pathlib import Path

import click

from pypedeid.cli._common import corpora_dir, models_dir
from pypedeid.cli.root import main


@main.group()
def train() -> None:
    """Fine-tune HF encoder models for PHI NER (requires pip install '.[train]')."""


@train.command(name="run")
@click.option("--base", "base_model", required=False, default=None, help="HF Hub id or 'local:<name>'.")
@click.option("--train-dataset", required=False, default=None, help="Registered dataset name.")
@click.option("--extra-train-dataset", "extra_train_datasets", multiple=True,
              help="Additional dataset(s) to merge into training (repeatable).")
@click.option("--output", "output_name", required=False, default=None, help="Output model name.")
@click.option("--eval-dataset", default=None, help="Separate eval dataset name.")
@click.option("--eval-fraction", type=float, default=None, help="Fraction of train set to use for eval.")
@click.option("--eval-test-dataset", "test_dataset", default=None, help="Held-out test dataset evaluated once after training.")
@click.option("--epochs", type=float, default=None)
@click.option("--lr", "learning_rate", type=float, default=None)
@click.option("--batch-size", "per_device_train_batch_size", type=int, default=None)
@click.option("--max-length", type=int, default=None)
@click.option("--freeze-encoder", is_flag=True, default=False)
@click.option("--segmentation", type=click.Choice(["truncate", "sentence"]), default=None,
              help="How to split docs for training. 'truncate' (default) crops long "
                   "docs at max-length; 'sentence' splits into sentences and trains "
                   "one example per sentence.")
@click.option("--device", default=None, help="cpu | cuda | cuda:N | mps")
@click.option("--overwrite", is_flag=True, default=False)
@click.option("--config", "config_path", type=click.Path(exists=True), default=None,
              help="JSON config file. Mutually exclusive with all other flags.")
def train_run(
    base_model: str | None,
    train_dataset: str | None,
    extra_train_datasets: tuple[str, ...],
    output_name: str | None,
    eval_dataset: str | None,
    eval_fraction: float | None,
    test_dataset: str | None,
    epochs: float | None,
    learning_rate: float | None,
    per_device_train_batch_size: int | None,
    max_length: int | None,
    freeze_encoder: bool,
    segmentation: str | None,
    device: str | None,
    overwrite: bool,
    config_path: str | None,
) -> None:
    """Fine-tune an HF encoder model for PHI NER.

    \b
    Examples:
      pypedeid train run \\
        --base emilyalsentzer/Bio_ClinicalBERT \\
        --train-dataset i2b2-2014 --eval-fraction 0.1 \\
        --output clinical-bert-v1 --epochs 3

      pypedeid train run \\
        --base local:clinical-bert-v1 \\
        --train-dataset internal-2026 \\
        --output clinical-bert-v2 --freeze-encoder

      pypedeid train run --config training/my_run.json
    """
    from pypedeid.training.config import TrainingConfig, TrainingHyperparams
    from pypedeid.training.errors import TrainingError
    from pypedeid.training.runner import run_training

    if config_path is not None:
        if any([eval_dataset, eval_fraction, test_dataset, epochs, learning_rate,
                per_device_train_batch_size, max_length, freeze_encoder, segmentation,
                device, overwrite, extra_train_datasets]):
            click.echo("Error: --config cannot be combined with other flags.", err=True)
            raise SystemExit(1)
        raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
        try:
            cfg = TrainingConfig(**raw)
        except Exception as exc:
            click.echo(f"Error in config file: {exc}", err=True)
            raise SystemExit(1)
    else:
        if not base_model or not train_dataset or not output_name:
            click.echo(
                "Error: --base, --train-dataset, and --output are required when not using --config.",
                err=True,
            )
            raise SystemExit(1)

        hp_overrides: dict = {}
        if epochs is not None:
            hp_overrides["epochs"] = epochs
        if learning_rate is not None:
            hp_overrides["learning_rate"] = learning_rate
        if per_device_train_batch_size is not None:
            hp_overrides["per_device_train_batch_size"] = per_device_train_batch_size
        if max_length is not None:
            hp_overrides["max_length"] = max_length

        try:
            cfg_kwargs: dict = dict(
                base_model=base_model,
                train_dataset=train_dataset,
                extra_train_datasets=list(extra_train_datasets),
                output_name=output_name,
                eval_dataset=eval_dataset,
                eval_fraction=eval_fraction,
                test_dataset=test_dataset,
                freeze_encoder=freeze_encoder,
                device=device,
                overwrite=overwrite,
                hyperparams=TrainingHyperparams(**hp_overrides) if hp_overrides else TrainingHyperparams(),
            )
            if segmentation is not None:
                cfg_kwargs["segmentation"] = segmentation
            cfg = TrainingConfig(**cfg_kwargs)
        except Exception as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1)

    try:
        final_path = run_training(
            cfg,
            models_dir=models_dir(),
            corpora_dir=corpora_dir(),
        )
        click.echo(f"Training complete: {final_path}")
    except TrainingError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    except ImportError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@train.command(name="show")
@click.argument("name")
def train_show(name: str) -> None:
    """Show manifest, metrics, and training lineage for a model."""
    from pypedeid.models import get_model

    try:
        info = get_model(models_dir(), name)
    except KeyError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    click.echo(f"Name:           {info.name}")
    click.echo(f"Framework:      {info.framework}")
    click.echo(f"Schema version: {info.schema_version or 1}")
    click.echo(f"Labels:         {', '.join(info.labels)}")
    click.echo(f"Base model:     {info.base_model or '—'}")
    click.echo(f"Parent model:   {info.parent_model or '—'}")
    click.echo(f"Has CRF:        {info.has_crf}")

    training = info.training_meta
    if training:
        click.echo("\nTraining:")
        click.echo(f"  Dataset:      {training.get('train_dataset', '—')}")
        click.echo(f"  Documents:    {training.get('train_documents', '—')}")
        click.echo(f"  Device:       {training.get('device_used', '—')}")
        click.echo(f"  Steps:        {training.get('total_steps', '—')}")
        click.echo(f"  Runtime:      {training.get('train_runtime_sec', '—')}s")
        click.echo(f"  Trained at:   {training.get('trained_at', '—')}")
        if training.get("head_reinitialised"):
            click.echo("  ⚠  Head was reinitialised (label space changed from parent)")

    metrics = info.metrics
    if metrics and metrics.get("overall"):
        o = metrics["overall"]
        click.echo(
            f"\nMetrics (overall):  "
            f"P={o.get('precision', 0):.4f}  "
            f"R={o.get('recall', 0):.4f}  "
            f"F1={o.get('f1', 0):.4f}"
        )
        per_label = metrics.get("per_label", {})
        if per_label:
            click.echo(f"\n{'Label':<22} {'P':>8} {'R':>8} {'F1':>8} {'Support':>8}")
            click.echo("-" * 56)
            for label, lm in sorted(per_label.items()):
                click.echo(
                    f"{label:<22} {lm.get('precision', 0):>8.4f} "
                    f"{lm.get('recall', 0):>8.4f} {lm.get('f1', 0):>8.4f} "
                    f"{lm.get('support', 0):>8}"
                )
    else:
        click.echo("\nNo metrics recorded (trained without eval split).")
