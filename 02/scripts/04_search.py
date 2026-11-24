import argparse

import numpy as np

from common import (FILTER_QUERY, PAPERS_INDEX, SEMANTIC_QUERY, TOP_K, encode, load_embeddings, load_model,
                    load_papers, namespace, open_index, pinecone_client, preview, query)


def local_scores(matrix, vector):
    # Use float64 for the comparison, not for index storage.
    matrix = matrix.astype(np.float64)
    vector = vector.astype(np.float64)
    dot = matrix @ vector
    cosine = dot / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(vector))
    l2 = np.linalg.norm(matrix - vector, axis=1)
    return {"cosine": cosine, "dot product": dot, "L2": l2}


def show_matches(matches, abstracts):
    if not matches:
        print("No matches for this filter in the indexed sample.")
    for rank, hit in enumerate(matches, 1):
        m = hit.metadata
        abstract = abstracts.get(m["arxiv_id"], m["abstract"])
        print(f"{rank}. {m['title']} | {m['category']} | {int(m['year'])} | "
              f"{m['arxiv_id']} | score={hit.score:.6f}")
        print(f"   {preview(abstract)}")


def show_local(frame, matrix, vector):
    print("\nLocal comparison for the unfiltered query")
    ordered = {}
    for metric, scores in local_scores(matrix, vector).items():
        top = np.argsort(scores if metric == "L2" else -scores, kind="stable")[:TOP_K]
        ordered[metric] = top.tolist()
        print(f"\n{metric}:")
        for pos in top:
            paper = frame.iloc[pos]
            print(f"  {scores[pos]:.8f} | {paper['id']} | {paper['title']}")
    for metric in ("dot product", "L2"):
        print(f"Cosine vs {metric}: same order = {ordered['cosine'] == ordered[metric]}, "
              f"common articles = {len(set(ordered['cosine']) & set(ordered[metric]))}")


def main():
    parser = argparse.ArgumentParser(description="Search Pinecone and compare three exact local metrics.")
    parser.add_argument("--query", default=SEMANTIC_QUERY)
    parser.add_argument("--local-only", action="store_true", help="Compare local metrics without Pinecone.")
    args = parser.parse_args()
    frame = load_papers()
    matrix = load_embeddings(frame)
    index = None if args.local_only else open_index(pinecone_client(), PAPERS_INDEX)
    model = load_model()
    vector, rl_vector = encode(model, [args.query, FILTER_QUERY])
    print(f'Query: "{args.query}"')
    if index is not None:
        target = namespace(frame)
        abstracts = frame.set_index("id")["abstract"].to_dict()
        print(f"\nPinecone semantic top-{TOP_K} (no filter):")
        semantic = query(index, target, vector)
        if not semantic:
            raise SystemExit("No matches in this corpus namespace. Run 03_load_to_pinecone.py first.")
        show_matches(semantic, abstracts)
        end = frame.attrs["as_of_year"]
        start = end - 4
        filters = [
            (f"A: cs.LG and {start}–{end}", {"$and": [
                {"category": {"$eq": "cs.LG"}}, {"year": {"$gte": start}}, {"year": {"$lte": end}},
            ]}, frame["category"].eq("cs.LG") & frame["year"].between(start, end)),
            ("B: before 2015, any category", {"year": {"$lt": 2015}}, frame["year"].lt(2015)),
        ]
        for label, condition, mask in filters:
            print(f'\n{label} | query="{FILTER_QUERY}" | eligible in corpus: {mask.sum()}')
            show_matches(query(index, target, rl_vector, metadata_filter=condition), abstracts)
    show_local(frame, matrix, vector)


if __name__ == "__main__":
    main()
