"""Optional frozen DINOv2 encoder with content-addressed, model-specific caching."""

import hashlib
import json
from pathlib import Path
import tempfile
from typing import Protocol

import numpy as np
from PIL import Image
from PIL import __version__ as pillow_version

from .preprocess import dinov2_pixels, load_rgb

DINO_REVISION = "ed25f3a31f01632728cabb09d1542f84ab7b0056"


class Encoder(Protocol):
    @property
    def identity(self) -> str: ...

    def encode(self, images: list[str | Path | Image.Image]) -> np.ndarray: ...


class DinoV2Encoder:
    """CPU by default; download once explicitly, then pass offline=True.

    Pin revision to a Hugging Face commit for reproducible runs. No random or
    handcrafted fallback is substituted if the actual encoder is unavailable.
    """

    def __init__(self, model_name="facebook/dinov2-small", revision=DINO_REVISION,
                 cache_dir=".cache/huggingface", offline=False, device="cpu"):
        try:
            import torch
            from transformers import Dinov2Model
        except ImportError as exc:
            raise RuntimeError("Install the vision extra: pip install -e '.[vision]'") from exc
        self.torch = torch
        self.device = device
        self.model = Dinov2Model.from_pretrained(
            model_name, revision=revision, cache_dir=str(cache_dir), local_files_only=offline
        ).eval().to(device)
        resolved = getattr(self.model.config, "_commit_hash", None)
        self._identity = (f"{model_name}@{resolved or revision}:cls:resize256-crop224-imagenet:v1"
                          f":pillow{pillow_version}")

    @property
    def identity(self):
        return self._identity

    def encode(self, images):
        pixels = np.stack([dinov2_pixels(image) for image in images])
        with self.torch.inference_mode():
            output = self.model(pixel_values=self.torch.from_numpy(pixels).to(self.device))
        return output.last_hidden_state[:, 0].cpu().numpy()


class CachedEncoder:
    def __init__(self, encoder: Encoder, cache_dir=".cache/embeddings"):
        self.encoder = encoder
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def identity(self):
        return self.encoder.identity

    def encode(self, images):
        result = []
        for image in images:
            rgb = load_rgb(image)
            digest = hashlib.sha256(self.identity.encode())
            digest.update(json.dumps(rgb.size).encode())
            digest.update(rgb.tobytes())
            path = self.cache_dir / f"{digest.hexdigest()}.npy"
            if path.exists():
                vector = np.load(path, allow_pickle=False)
            else:
                vector = np.asarray(self.encoder.encode([rgb])[0], dtype=np.float32)
                with tempfile.NamedTemporaryFile(dir=self.cache_dir, suffix=".tmp", delete=False) as handle:
                    temporary = Path(handle.name)
                    np.save(handle, vector, allow_pickle=False)
                temporary.replace(path)
            if vector.ndim != 1 or not np.isfinite(vector).all() or np.linalg.norm(vector) <= 1e-12:
                raise ValueError(f"Invalid embedding in {path}")
            result.append(vector)
        return np.stack(result)
