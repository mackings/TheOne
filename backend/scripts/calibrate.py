"""Threshold calibration.

Usage: .venv/bin/python scripts/calibrate.py <dir with one folder per speaker of .flac/.wav> <model.onnx>
Prints FAR/FRR per threshold, score distributions and anti-spoof baseline stats.
"""
import sys, pathlib, numpy as np, soundfile as sf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.identity.infrastructure.embedder import SherpaOnnxEmbedder
from app.identity.domain.matcher import build_template, cosine
from app.identity.infrastructure.antispoof import BaselineAntiSpoof
root = pathlib.Path(sys.argv[1])
emb = SherpaOnnxEmbedder(pathlib.Path(sys.argv[2]))
asp = BaselineAntiSpoof()
N_ENROL, N_PROBE = 3, 6
speakers = {}
for spk_dir in sorted(p for p in root.glob("*") if p.is_dir()):
    picked = []
    for f in sorted(list(spk_dir.rglob("*.flac")) + list(spk_dir.rglob("*.wav"))):
        if 2.5 <= sf.info(f).duration <= 12: picked.append(f)
        if len(picked) >= N_ENROL + N_PROBE: break
    if len(picked) < N_ENROL + N_PROBE: continue
    embs, spoofs = [], []
    for f in picked:
        x, sr = sf.read(f, dtype="float32"); embs.append(emb.embed(x, sr)); spoofs.append(asp.score(x, sr).score)
    speakers[spk_dir.name] = (embs, spoofs)
print("model:", emb.name, "speakers:", len(speakers), "clips:", sum(len(e) for e, _ in speakers.values()))
same, other = [], []
tpl = {s: build_template(e[:N_ENROL]).template for s, (e, _) in speakers.items()}
for s, (e, _) in speakers.items():
    for p in e[N_ENROL:]:
        same.append(cosine(tpl[s], p))
        for o, t in tpl.items():
            if o != s: other.append(cosine(t, p))
same, other = np.array(same), np.array(other)
print(f"same  n={len(same)} min={same.min():.3f} p1={np.percentile(same,1):.3f} p5={np.percentile(same,5):.3f} median={np.median(same):.3f}")
print(f"other n={len(other)} max={other.max():.3f} p99.9={np.percentile(other,99.9):.3f} p99={np.percentile(other,99):.3f} median={np.median(other):.3f}")
for th in np.arange(0.20, 0.80, 0.025):
    print(f"th={th:.3f} FAR={(other >= th).mean():.4f} FRR={(same < th).mean():.4f}")
sp = np.array([s for _, ss in speakers.values() for s in ss])
print(f"spoof baseline on real speech: median={np.median(sp):.2f} p95={np.percentile(sp,95):.2f} max={sp.max():.2f}")
cons = [build_template(e[:N_ENROL]).consistency for e, _ in speakers.values()]
print(f"enrolment consistency: min={min(cons):.2f} median={np.median(cons):.2f}")
