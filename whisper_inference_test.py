#!/usr/bin/env python3
"""
Compare baseline Whisper small vs fine-tuned whisper-provoc-v1
Uses the same MLS dev split (50 samples/lang) as the training eval loop
to reproduce the reported 70.18% → 50.90% WER numbers.
"""
import os
os.environ["DATASETS_AUDIO_BACKEND"] = "soundfile"

import torch
import numpy as np
import evaluate
from datasets import load_dataset, Dataset
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import whisper as openai_whisper

DEVICE          = "cuda" if torch.cuda.is_available() else "cpu"
FINETUNED_PATH  = "./whisper-provoc-small/final"
SAMPLES_PER_LANG = 50
LANGUAGES       = ["en", "fr", "es"]

wer_metric = evaluate.load("wer")


def load_mls_dev(lang: str, n: int) -> Dataset:
    print(f"  Loading MLS dev — {lang} ({n} samples)...")
    if lang == "en":
        ds = load_dataset("parler-tts/mls_eng", split="dev", streaming=True)
    else:
        lang_map = {"fr": "french", "es": "spanish"}
        ds = load_dataset(
            "facebook/multilingual_librispeech",
            lang_map[lang], split="dev", streaming=True
        )
    return Dataset.from_list(list(ds.take(n)))


print("Loading baseline openai/whisper-small...")
baseline = openai_whisper.load_model("small").to(DEVICE)

print(f"Loading fine-tuned model from {FINETUNED_PATH}...")
ft_processor = WhisperProcessor.from_pretrained(FINETUNED_PATH)
ft_model     = WhisperForConditionalGeneration.from_pretrained(
    FINETUNED_PATH).to(DEVICE)
ft_model.eval()

print("\nLoading MLS dev splits...")
lang_datasets = {lang: load_mls_dev(lang, SAMPLES_PER_LANG) for lang in LANGUAGES}

results = []
print(f"\n{'='*72}")
print(f"{'Language':<12} {'Samples':>8} {'Baseline WER':>14} {'Fine-tuned WER':>16} {'Delta':>8}")
print(f"{'='*72}")

for lang in LANGUAGES:
    ds = lang_datasets[lang]
    base_preds, ft_preds, refs = [], [], []

    for sample in ds:
        audio_array = np.array(sample["audio"]["array"], dtype=np.float32)
        sr          = sample["audio"]["sampling_rate"]
        reference   = sample["transcript"].strip()

        # Baseline — openai whisper API (operates on raw array)
        audio_16k = openai_whisper.audio.pad_or_trim(
            torch.from_numpy(audio_array).float()
        )
        mel      = openai_whisper.log_mel_spectrogram(audio_16k).to(DEVICE)
        opts     = openai_whisper.DecodingOptions(language=lang, fp16=(DEVICE == "cuda"))
        base_out = openai_whisper.decode(baseline, mel, opts)
        base_preds.append(base_out.text.strip())

       # Fine-tuned — force correct language token to prevent hallucination
        inputs = ft_processor(
            audio_array, sampling_rate=sr, return_tensors="pt"
        ).input_features.to(DEVICE)
        forced_decoder_ids = ft_processor.get_decoder_prompt_ids(
            language=lang, task="transcribe"
        )
        with torch.no_grad():
            ids = ft_model.generate(inputs, forced_decoder_ids=forced_decoder_ids)
        ft_preds.append(
            ft_processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
        )

        refs.append(reference)

    base_wer = wer_metric.compute(predictions=base_preds, references=refs) * 100
    ft_wer   = wer_metric.compute(predictions=ft_preds,   references=refs) * 100
    delta    = base_wer - ft_wer
    results.append((base_wer, ft_wer, delta))

    arrow = "v" if delta > 0 else "^"
    print(f"{lang:<12} {len(ds):>8} {base_wer:>13.2f}% {ft_wer:>15.2f}%  "
          f"{arrow}{abs(delta):.2f}%")

avg_base = np.mean([r[0] for r in results])
avg_ft   = np.mean([r[1] for r in results])
avg_imp  = np.mean([r[2] for r in results])
rel_imp  = (avg_imp / avg_base) * 100

print(f"{'='*72}")
print(f"{'AVERAGE':<12} {SAMPLES_PER_LANG * len(LANGUAGES):>8} "
      f"{avg_base:>13.2f}% {avg_ft:>15.2f}%  "
      f"{'v' if avg_imp > 0 else '^'}{abs(avg_imp):.2f}%")
print(f"{'='*72}")
print(f"\nBaseline WER  : {avg_base:.2f}%")
print(f"Fine-tuned WER: {avg_ft:.2f}%")
print(f"Absolute improvement : {avg_imp:.2f}%")
print(f"Relative improvement : {rel_imp:.1f}%")
print(f"\nConclusion: Fine-tuned whisper-provoc-v1 achieves {rel_imp:.1f}% relative "
      f"WER improvement over baseline Whisper small.")
