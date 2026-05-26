#!/usr/bin/env python3
"""
Whisper small fine-tune on Multilingual LibriSpeech
Languages: EN, FR, ES
Hardware: RTX 3050 4GB VRAM
Tracking: MLflow
"""

import os
os.environ["DATASETS_AUDIO_BACKEND"] = "soundfile"

import torch
import mlflow
import numpy as np
from dataclasses import dataclass
from typing import Any, Dict, List, Union
from dotenv import load_dotenv

load_dotenv()

from datasets import load_dataset, DatasetDict, concatenate_datasets
from transformers import (
    WhisperFeatureExtractor,
    WhisperTokenizer,
    WhisperProcessor,
    WhisperForConditionalGeneration,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer,
)
import evaluate
from mlflow_config import setup_mlflow, log_whisper_params, register_model
# ── Config ────────────────────────────────────────────────────────────────────
MODEL_NAME     = "openai/whisper-small"
LANGUAGES      = ["en", "fr", "es"]
SAMPLES_PER_LANG = 500          # 1500 total — fits 4GB VRAM
MAX_LABEL_LEN  = 448
OUTPUT_DIR     = "./whisper-provoc-small"
EXPERIMENT     = "whisper-provoc-finetuning"
BATCH_SIZE     = 4
GRAD_ACCUM     = 8              # effective batch = 32
LEARNING_RATE  = 1e-5
WARMUP_STEPS   = 50
MAX_STEPS      = 400            # ~4-6 hours on RTX 3050
EVAL_STEPS     = 100
SAVE_STEPS     = 100
FP16           = torch.cuda.is_available()
DEVICE         = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Device: {DEVICE} | FP16: {FP16}")

# ── Load processor ────────────────────────────────────────────────────────────
feature_extractor = WhisperFeatureExtractor.from_pretrained(MODEL_NAME)
tokenizer = WhisperTokenizer.from_pretrained(
    MODEL_NAME, language="English", task="transcribe"
)
processor = WhisperProcessor.from_pretrained(
    MODEL_NAME, language="English", task="transcribe"
)

# ── Load and prepare dataset ──────────────────────────────────────────────────
def load_language_split(lang: str, split: str, n: int):
    print(f"Loading MLS — {lang} — {split} ({n} samples)...")
    actual_split = "dev" if split == "validation" else split

    if lang == "en":
        ds = load_dataset(
            "parler-tts/mls_eng",
            split=actual_split,
            streaming=True
        )
    else:
        lang_map = {"fr": "french", "es": "spanish"}
        ds = load_dataset(
            "facebook/multilingual_librispeech",
            lang_map[lang],
            split=actual_split,
            streaming=True
        )

    samples = list(ds.take(n))
    from datasets import Dataset
    return Dataset.from_list(samples)

def prepare_dataset(batch):
    audio = batch["audio"]
    batch["input_features"] = feature_extractor(
        audio["array"],
        sampling_rate=audio["sampling_rate"],
        return_tensors="pt"
    ).input_features[0]
    batch["labels"] = tokenizer(batch["transcript"]).input_ids
    return batch

print("Loading datasets...")
train_splits, eval_splits = [], []

for lang in LANGUAGES:
    train_splits.append(load_language_split(lang, "train", SAMPLES_PER_LANG))
    eval_splits.append(load_language_split(lang, "validation", 50))

train_dataset = concatenate_datasets(train_splits)
eval_dataset  = concatenate_datasets(eval_splits)

print(f"Train: {len(train_dataset)} samples | Eval: {len(eval_dataset)} samples")

train_dataset = train_dataset.cast_column("audio",
    train_dataset.features["audio"])
eval_dataset  = eval_dataset.cast_column("audio",
    eval_dataset.features["audio"])

train_dataset = train_dataset.map(
    prepare_dataset,
    remove_columns=train_dataset.column_names,
    num_proc=1
)
eval_dataset  = eval_dataset.map(
    prepare_dataset,
    remove_columns=eval_dataset.column_names,
    num_proc=1
)

# ── Data collator ─────────────────────────────────────────────────────────────
@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    processor: Any

    def __call__(self, features: List[Dict[str, Union[List[int], torch.Tensor]]]):
        input_features = [
            {"input_features": f["input_features"]} for f in features
        ]
        batch = self.processor.feature_extractor.pad(
            input_features, return_tensors="pt"
        )
        label_features = [{"input_ids": f["labels"]} for f in features]
        labels_batch = self.processor.tokenizer.pad(
            label_features, return_tensors="pt"
        )
        labels = labels_batch["input_ids"].masked_fill(
            labels_batch.attention_mask.ne(1), -100
        )
        if (labels[:, 0] == self.processor.tokenizer.bos_token_id).all().cpu().item():
            labels = labels[:, 1:]
        batch["labels"] = labels
        return batch

data_collator = DataCollatorSpeechSeq2SeqWithPadding(processor=processor)

# ── Metrics ───────────────────────────────────────────────────────────────────
wer_metric = evaluate.load("wer")

def compute_metrics(pred):
    pred_ids    = pred.predictions
    label_ids   = pred.label_ids
    label_ids[label_ids == -100] = tokenizer.pad_token_id
    pred_str    = tokenizer.batch_decode(pred_ids,   skip_special_tokens=True)
    label_str   = tokenizer.batch_decode(label_ids,  skip_special_tokens=True)
    wer = 100 * wer_metric.compute(predictions=pred_str, references=label_str)
    return {"wer": wer}

# ── Model ─────────────────────────────────────────────────────────────────────
print("Loading Whisper small...")
model = WhisperForConditionalGeneration.from_pretrained(MODEL_NAME)
model.config.forced_decoder_ids  = None
model.config.suppress_tokens     = []
model.config.use_cache            = False

# ── Training arguments ────────────────────────────────────────────────────────
training_args = Seq2SeqTrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    learning_rate=LEARNING_RATE,
    warmup_steps=WARMUP_STEPS,
    max_steps=MAX_STEPS,
    gradient_checkpointing=True,
    fp16=FP16,
    eval_strategy="steps",
    per_device_eval_batch_size=4,
    predict_with_generate=True,
    generation_max_length=MAX_LABEL_LEN,
    save_steps=SAVE_STEPS,
    eval_steps=EVAL_STEPS,
    logging_steps=25,
    report_to=["none"],           # we handle MLflow manually
    load_best_model_at_end=True,
    metric_for_best_model="wer",
    greater_is_better=False,
    push_to_hub=False,
    dataloader_num_workers=0,     # Windows compatibility
)

trainer = Seq2SeqTrainer(
    args=training_args,
    model=model,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    data_collator=data_collator,
    compute_metrics=compute_metrics,
    processing_class=processor.feature_extractor,
)

# ── Baseline WER (before fine-tuning) ────────────────────────────────────────
print("\nComputing baseline WER (before fine-tuning)...")
baseline_result = trainer.evaluate()
baseline_wer    = baseline_result["eval_wer"]
print(f"Baseline WER: {baseline_wer:.2f}%")

# ── MLflow run ────────────────────────────────────────────────────────────────
setup_mlflow(EXPERIMENT)

with mlflow.start_run(run_name="whisper-small-common-voice-EN-FR-ES") as run:
    run_id = run.info.run_id

    log_whisper_params(
        model_size="small",
        languages=LANGUAGES,
        num_samples=len(train_dataset),
        batch_size=BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        epochs=int(MAX_STEPS * BATCH_SIZE * GRAD_ACCUM / len(train_dataset))
    )

    mlflow.log_metric("baseline_wer", baseline_wer)

    print(f"\nStarting fine-tuning — MLflow run: {run_id}")
    print(f"MLflow UI: http://localhost:5001")
    trainer.train()

    print("\nComputing final WER (after fine-tuning)...")
    final_result = trainer.evaluate()
    final_wer    = final_result["eval_wer"]
    improvement  = baseline_wer - final_wer

    mlflow.log_metrics({
        "final_wer":    final_wer,
        "wer_improvement": improvement,
        "wer_improvement_pct": (improvement / baseline_wer) * 100
    })

    print(f"\n{'='*50}")
    print(f"Baseline WER:  {baseline_wer:.2f}%")
    print(f"Fine-tuned WER: {final_wer:.2f}%")
    print(f"Improvement:   {improvement:.2f}% ({(improvement/baseline_wer)*100:.1f}% relative)")
    print(f"{'='*50}\n")

    # Save model locally
    model_save_path = f"{OUTPUT_DIR}/final"
    trainer.save_model(model_save_path)
    processor.save_pretrained(model_save_path)
    print(f"Model saved to {model_save_path}")

    # Log model artifact to MLflow
    mlflow.log_artifacts(model_save_path, artifact_path="whisper-provoc")

    # Register in MLflow model registry
    mlflow.set_tag("wer", f"{final_wer:.4f}")
    mlflow.set_tag("baseline_wer", f"{baseline_wer:.4f}")
    mlflow.set_tag("languages", "en,fr,es")
    mlflow.set_tag("base_model", MODEL_NAME)

    registered = mlflow.register_model(
        f"runs:/{run_id}/whisper-provoc",
        "whisper-provoc-v1"
    )
    print(f"Model registered: whisper-provoc-v1 version {registered.version}")
    print(f"\nMLflow run ID: {run_id}")
    print(f"View at: http://localhost:5001/#/experiments/1/runs/{run_id}")

print("\nFine-tuning complete.")
