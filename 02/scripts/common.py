"""Shared dataset, embedding and Pinecone utilities for HW02."""
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "arxiv-metadata-oai-snapshot.json"
PARQUET = ROOT / "data/arxiv_subset.parquet"
EMBEDDINGS = ROOT / "embeddings/embeddings.npy"
MANIFEST = EMBEDDINGS.with_suffix(".json")
DATASET_CONFIG = PARQUET.with_suffix(".json")
MODEL = "allenai/specter2_base"
DIM = 768
MAX_TOKENS = 512
ENCODER = f"{MODEL}:cls:l2:{MAX_TOKENS}:v1"
PAPERS_INDEX = "arxiv-papers"
SEMANTIC_QUERY = "teaching machines to recognize objects in pictures"
FILTER_QUERY = "reinforcement learning"
TOP_K = 5


def fingerprint(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def namespace(frame):
    return "hw02-" + frame.attrs["sha256"][:20] + "-cls-v1"


def load_papers():
    if not PARQUET.is_file():
        raise SystemExit("Run 01_prepare_data.py first.")
    frame = pd.read_parquet(PARQUET).reset_index(drop=True)
    frame.attrs["sha256"] = fingerprint(PARQUET)
    frame.attrs.update(json.loads(DATASET_CONFIG.read_text(encoding="utf-8")))
    return frame


def save_embeddings(frame, vectors):
    EMBEDDINGS.parent.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS, vectors, allow_pickle=False)
    MANIFEST.write_text(json.dumps({
        "encoder": ENCODER,
        "parquet_sha256": frame.attrs["sha256"],
        "embeddings_sha256": fingerprint(EMBEDDINGS),
    }, indent=2) + "\n", encoding="utf-8")


def load_embeddings(frame):
    if not EMBEDDINGS.is_file() or not MANIFEST.is_file():
        raise SystemExit("Run 02_embed.py first.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest != {
        "encoder": ENCODER,
        "parquet_sha256": frame.attrs["sha256"],
        "embeddings_sha256": fingerprint(EMBEDDINGS),
    }:
        raise SystemExit("Embedding artifacts do not match the corpus or encoder. Rerun 02_embed.py.")
    return validate_vectors(np.load(EMBEDDINGS, allow_pickle=False), len(frame))


def validate_vectors(vectors, count):
    if vectors.shape != (count, DIM) or not np.isfinite(vectors).all():
        raise ValueError(f"Expected {count} finite vectors of dimension {DIM}; got {vectors.shape}.")
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5):
        raise ValueError("Expected unit-normalized embeddings.")
    return vectors


def load_model(device=None):
    # Explicit CLS pooling matches the model card; automatic ST fallback uses mean pooling.
    from sentence_transformers import SentenceTransformer, models

    transformer = models.Transformer(MODEL, max_seq_length=MAX_TOKENS)
    pooling = models.Pooling(transformer.get_word_embedding_dimension(), pooling_mode="cls")
    return SentenceTransformer(modules=[transformer, pooling], device=device)


def paper_text(title, abstract):
    return f"{title} [SEP] {abstract}"


def encode(model, texts, batch_size=64, progress=False):
    vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=progress,
                           normalize_embeddings=True, convert_to_numpy=True)
    return validate_vectors(np.asarray(vectors, dtype=np.float32), len(texts))


def pinecone_client():
    from dotenv import load_dotenv
    from pinecone import Pinecone

    load_dotenv(ROOT / ".env")
    key = os.getenv("PINECONE_API_KEY", "").strip()
    if not key:
        raise SystemExit("Set PINECONE_API_KEY in 02/.env before running the Pinecone scripts.")
    return Pinecone(api_key=key)


def open_index(client, name, create=False):
    if not client.indexes.exists(name):
        if not create:
            raise SystemExit(f"Index {name!r} not found. Run the corresponding load script first.")
        client.indexes.create(
            name=name,
            schema={"fields": {"_values": {"type": "dense_vector", "dimension": DIM,
                                           "metric": "cosine"}}},
            deployment={"deployment_type": "managed", "cloud": "aws", "region": "us-east-1"},
            timeout=-1,
        )
    deadline = time.monotonic() + 180
    while True:
        config = client.indexes.describe(name)
        field = config.schema.fields.get("_values")
        if field is None or field.dimension != DIM or field.metric != "cosine":
            raise SystemExit(f"Index {name!r} must use {DIM} dimensions and cosine. No data overwritten.")
        if config.status.ready:
            return client.index(host=config.host)
        if time.monotonic() >= deadline:
            raise SystemExit(f"Index {name!r} did not become ready within 180 seconds.")
        time.sleep(3)


def upload(index, records, target, label, batch_size=200):
    from tqdm import tqdm

    with tqdm(total=len(records), desc=f"Upsert {label}", unit=" vectors") as progress:
        for batch in wire_batches(records, batch_size):
            response = index.upsert(vectors=batch, namespace=target)
            if response.upserted_count != len(batch):
                raise SystemExit(f"Incomplete upsert for {label}: {response.upserted_count}/{len(batch)}.")
            progress.update(len(batch))
    # Pinecone stats can lag behind successful writes.
    deadline = time.monotonic() + 120
    while True:
        stats = index.describe_index_stats()
        summary = stats.namespaces.get(target)
        visible = summary.vector_count if summary else 0
        if visible >= len(records) or time.monotonic() >= deadline:
            print(f"{label}: {visible}/{len(records)} vectors visible in {target}; "
                  f"total in index: {stats.total_vector_count}")
            if visible < len(records):
                raise SystemExit("Upserts finished but stats are not yet current. Retry before searching.")
            if visible > len(records):
                raise SystemExit("Namespace contains unexpected vectors. Check the index before searching.")
            return
        time.sleep(3)


def wire_batches(records, batch_size, byte_limit=1_900_000):
    # A 768-d vector serialized as JSON can be much larger than 768 float32s.
    batch, size = [], 128
    for record in records:
        width = len(json.dumps(record, ensure_ascii=True, separators=(",", ":"))) + 1
        if width + 128 > byte_limit:
            raise ValueError(f"Vector {record['id']} exceeds the upsert payload budget.")
        if len(batch) == batch_size or size + width > byte_limit:
            yield batch
            batch, size = [], 128
        batch.append(record)
        size += width
    if batch:
        yield batch


def query(index, target, vector, top_k=TOP_K, metadata_filter=None):
    kwargs = {"filter": metadata_filter} if metadata_filter is not None else {}
    return index.query(vector=vector.tolist(), namespace=target, top_k=top_k,
                       include_metadata=True, **kwargs).matches


def paper_id(pos):
    return f"paper_{pos}"


def preview(text, length=240):
    return text if len(text) <= length else text[:length].rstrip() + "…"
