from common import PAPERS_INDEX, load_embeddings, load_papers, namespace, open_index, paper_id, pinecone_client, upload


def article_records(frame, vectors):
    return [
        {
            "id": paper_id(i),
            "values": vectors[i].tolist(),
            "metadata": {
                "arxiv_id": row.id, "title": row.title, "abstract": row.abstract[:500],
                "authors": row.authors[:200], "year": int(row.year), "category": row.category,
            },
        }
        for i, row in enumerate(frame.itertuples(index=False))
    ]


def main():
    frame = load_papers()
    vectors = load_embeddings(frame)
    index = open_index(pinecone_client(), PAPERS_INDEX, create=True)
    upload(index, article_records(frame, vectors), namespace(frame), PAPERS_INDEX)


if __name__ == "__main__":
    main()
