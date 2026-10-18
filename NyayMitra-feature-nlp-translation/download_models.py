"""Pre-download the gated models so service startup doesn't stall.

For the two IndicTrans2 checkpoints we skip pytorch_model.bin: the repo ships
both .bin and .safetensors of identical size, and transformers prefers
safetensors, so the .bin copy is a wasted ~1 GB.

The conformer is downloaded in full because model_onnx.py overrides
from_pretrained() with a bare snapshot_download(repo_id=...), which pulls
every file including the ONNX external-data weights under assets/.
"""
import os
import sys
import time

from huggingface_hub import snapshot_download

REPOS = [
    ("ai4bharat/indictrans2-en-indic-dist-200M", ["pytorch_model.bin"]),
    ("ai4bharat/indictrans2-indic-indic-dist-320M", ["pytorch_model.bin"]),
    ("ai4bharat/indic-conformer-600m-multilingual", None),
]

token = os.environ.get("HF_TOKEN")
if not token:
    sys.exit("HF_TOKEN is not set")

for repo, ignore in REPOS:
    started = time.time()
    print(f"\n=== {repo} ===", flush=True)
    try:
        path = snapshot_download(repo, token=token, ignore_patterns=ignore)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED {repo}: {type(exc).__name__}: {exc}", flush=True)
        continue
    elapsed = max(time.time() - started, 1e-6)
    size = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                size += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    print(
        f"OK {repo}: {size / 1048576:.0f} MB in {elapsed:.0f}s "
        f"({size / 1048576 / elapsed:.1f} MB/s)",
        flush=True,
    )

print("\nWARM COMPLETE", flush=True)
