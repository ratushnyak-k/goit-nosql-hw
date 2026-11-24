import re
from collections import defaultdict

import numpy as np
from rank_bm25 import BM25Okapi

from common import (PAPERS_INDEX, TOP_K, encode, load_model, load_papers, namespace,
                    open_index, pinecone_client, query)

CANDIDATES = 20
QUERIES = ("BERT fine-tuning", "Yann LeCun convolutional networks",
           "making computers understand human emotions from text")


def tokenize(text):
    return re.findall(r"\b\w+\b", text.casefold())


def bm25_search(bm25, corpus, ids, text, top_k=CANDIDATES):
    tokens = tokenize(text)
    scores = bm25.get_scores(tokens)
    terms = set(tokens)
    ordered = np.argsort(-scores, kind="stable")
    return [(ids[i], float(scores[i])) for i in ordered if terms & corpus[i]][:top_k]


def vector_search(index, target, vector):
    return [(hit.metadata["arxiv_id"], hit.score) for hit in query(index, target, vector, CANDIDATES)]


def rrf(rankings, k=60):
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, (arxiv_id, _) in enumerate(ranking, 1):
            scores[arxiv_id] += 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def hybrid_search(bm25_ranking, vector_ranking, k=60, top_k=TOP_K):
    return rrf((bm25_ranking, vector_ranking), k)[:top_k]


def main():
    frame = load_papers()
    index = open_index(pinecone_client(), PAPERS_INDEX)
    target = namespace(frame)
    model = load_model()
    ids = frame["id"].tolist()
    titles = dict(zip(ids, frame["title"], strict=True))
    # Include authors as a searchable field for the author-name example.
    tokens = [tokenize(f"{row.title} {row.abstract} {row.authors}")
              for row in frame.itertuples(index=False)]
    bm25 = BM25Okapi(tokens)
    token_sets = [set(doc) for doc in tokens]
    rows = []
    for text, vector in zip(QUERIES, encode(model, list(QUERIES)), strict=True):
        print(f'\nQuery: "{text}"')
        lexical = bm25_search(bm25, token_sets, ids, text)
        dense = vector_search(index, target, vector)
        if not dense:
            raise SystemExit("No vector matches in this namespace. Run 03_load_to_pinecone.py first.")
        fused = hybrid_search(lexical, dense)
        for label, ranking in (("BM25", lexical), ("Pinecone", dense), ("RRF (k=60)", fused)):
            print(f"{label} top-{TOP_K}:")
            if not ranking:
                print("  No matching terms in the corpus.")
            for rank, (arxiv_id, score) in enumerate(ranking[:TOP_K], 1):
                print(f"  {rank}. {arxiv_id} | {titles[arxiv_id]} | score={score:.6f}")
        single_top = {item[0] for item in lexical[:TOP_K] + dense[:TOP_K]}
        new_ids = [arxiv_id for arxiv_id, _ in fused if arxiv_id not in single_top]
        print("In hybrid top-5 only:", ", ".join(new_ids) or "none")
        print("RRF k=1 top-5:", ", ".join(i for i, _ in hybrid_search(lexical, dense, k=1)))
        rows.append([text] + [", ".join(i for i, _ in ranking[:TOP_K]) or "—"
                              for ranking in (lexical, dense, fused)])
    print("\n| Query | BM25 IDs | Pinecone IDs | RRF IDs |")
    print("|---|---|---|---|")
    for row in rows:
        print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main()
