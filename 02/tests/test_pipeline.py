import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import DIM, open_index, wire_batches

prepare = importlib.import_module("01_prepare_data")
upload_papers = importlib.import_module("03_load_to_pinecone")
search = importlib.import_module("04_search")
chunk = importlib.import_module("05_chunking")
hybrid = importlib.import_module("06_hybrid_search")


class PipelineTests(unittest.TestCase):
    def test_corpus_reserves_recent_cs_lg_and_uses_first_version(self):
        papers = [
            dict(id=str(i), title=f"Example {i}", abstract="A test abstract.", categories="math.CO",
                 versions=[{"created": "Mon, 2 Apr 2007 19:18:42 GMT"}], update_date="2026-01-01")
            for i in range(12)
        ]
        papers += [dict(id="recent", title="Learning", abstract="A recent example.",
                        categories="cs.LG cs.AI", update_date="2024-06-01")]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "snapshot.json"
            source.write_text("\n".join(map(json.dumps, papers)), encoding="utf-8")
            records, reserved, invalid = prepare.select_records(source, 10, 2026)
        self.assertEqual(len(records), 10)
        self.assertEqual((reserved, invalid), (1, 0))
        self.assertEqual(records[0]["year"], 2007)
        self.assertEqual((records[-1]["id"], records[-1]["category"]), ("recent", "cs.LG"))

    def test_metadata_and_batch_size(self):
        frame = pd.DataFrame([dict(id="test", title="Title", abstract="a" * 501,
                                   authors="b" * 201, year=2026, category="cs.LG")])
        records = upload_papers.article_records(frame, np.ones((1, DIM)))
        record = records[0]
        self.assertEqual(record["id"], "paper_0")
        self.assertEqual(len(record["metadata"]["abstract"]), 500)
        self.assertEqual(len(record["metadata"]["authors"]), 200)
        self.assertEqual(type(record["metadata"]["year"]), int)
        self.assertEqual([len(batch) for batch in wire_batches(records * 3, 2)], [2, 1])
        limit = len(json.dumps(record)) + 128
        self.assertEqual([len(batch) for batch in wire_batches(records * 3, 3, limit)], [1, 1, 1])

    def test_index_config(self):
        def create(**kwargs):
            self.assertEqual(kwargs["schema"]["fields"]["_values"]["dimension"], DIM)
            self.assertEqual(kwargs["deployment"]["deployment_type"], "managed")

        config = SimpleNamespace(schema=SimpleNamespace(fields={
            "_values": SimpleNamespace(dimension=DIM, metric="cosine")
        }), status=SimpleNamespace(ready=True), host="test.invalid")
        indexes = SimpleNamespace(exists=lambda name: False, describe=lambda name: config, create=create)
        client = SimpleNamespace(indexes=indexes, index=lambda *, host: host)
        self.assertEqual(open_index(client, "arxiv-papers", create=True), "test.invalid")

    def test_unit_vector_rankings_agree(self):
        vectors = np.array([[1, 0], [0, 1], [-1, 0]])
        scores = search.local_scores(vectors, np.array([1, 0]))
        np.testing.assert_allclose(scores["cosine"], scores["dot product"])
        np.testing.assert_allclose(scores["L2"] ** 2, 2 - 2 * scores["cosine"])
        np.testing.assert_array_equal(np.argsort(-scores["cosine"]), np.argsort(scores["L2"]))

    def test_fixed_coverage_and_semantic_boundaries(self):
        text = "Alpha beta gamma. Delta epsilon zeta. Eta theta iota."
        fits = lambda text: len(text.split()) <= 6
        fixed = chunk.fixed_chunks(text, fits, 5, 2)
        semantic, split = chunk.semantic_chunks(text, fits, 5)
        self.assertEqual(fixed[0].split()[-2:], fixed[1].split()[:2])
        self.assertEqual(fixed[-1].split()[-1], "iota.")
        self.assertEqual(semantic, ["Alpha beta gamma.", "Delta epsilon zeta.", "Eta theta iota."])
        self.assertEqual(split, 0)
        parts, split = chunk.semantic_chunks(text, lambda text: len(text.split()) <= 2, 5)
        self.assertEqual(" ".join(parts), text)
        self.assertEqual(split, 3)

    def test_rrf_uses_ranks_not_raw_scores(self):
        first = [("a", 10000), ("c", 0)]
        second = [("b", 0.9), ("c", 0.5)]
        self.assertEqual(hybrid.hybrid_search(first, second)[0], ("c", 2 / 62))


if __name__ == "__main__":
    unittest.main()
