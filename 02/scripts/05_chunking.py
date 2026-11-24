import re
from collections import Counter

from common import (FILTER_QUERY, MAX_TOKENS, SEMANTIC_QUERY, TOP_K, encode, load_model, load_papers,
                    namespace, open_index, paper_text, pinecone_client, preview, query, upload)

MAX_WORDS = 100
OVERLAP = 20
SENTENCE_BREAK = re.compile(
    r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bet al\.)(?<!\b[A-Z]\.)(?<!\bFig\.)(?<!\bEq\.)"
    r"(?<=[.!?])\s+(?=[A-Z0-9\"(])"
)
QUERIES = (SEMANTIC_QUERY, FILTER_QUERY, "How do neural networks generalize to unseen data?")


def word_windows(words, limit, overlap):
    for start in range(0, len(words), limit - overlap):
        end = start + limit
        yield " ".join(words[start:end])
        if end >= len(words):
            break


def enforce_budget(text, fits):
    if fits(text):
        return [text]
    words = text.split()
    if len(words) > 1:
        middle = len(words) // 2
        left, right = " ".join(words[:middle]), " ".join(words[middle:])
    else:
        middle = len(text) // 2
        if not middle:
            raise ValueError("Tokenizer budget is too small for a single character.")
        left, right = text[:middle], text[middle:]
    return enforce_budget(left, fits) + enforce_budget(right, fits)


def fixed_chunks(text, fits, size=MAX_WORDS, overlap=OVERLAP):
    return [part for window in word_windows(text.split(), size, overlap)
            for part in enforce_budget(window, fits)]


def semantic_chunks(text, fits, size=MAX_WORDS):
    chunks, current = [], ""
    split_sentences = 0
    for sentence in SENTENCE_BREAK.split(text):
        words = sentence.split()
        if len(words) > size or not fits(sentence):
            if current:
                chunks.append(current)
                current = ""
            # An individual sentence can exceed either hard limit.
            parts = fixed_chunks(sentence, fits, size, overlap=0)
            chunks.extend(parts)
            split_sentences += 1
            continue
        combined = f"{current} {sentence}".strip()
        if current and (len(combined.split()) > size or not fits(combined)):
            chunks.append(current)
            current = sentence
        else:
            current = combined
    if current:
        chunks.append(current)
    return chunks, split_sentences


def longest_papers(frame, tokenizer):
    sizes = []
    for start in range(0, len(frame), 256):
        abstracts = frame.iloc[start:start + 256]["abstract"].tolist()
        tokens = tokenizer(abstracts, add_special_tokens=False, truncation=False, verbose=False)
        sizes.extend(map(len, tokens["input_ids"]))
    return frame.assign(abstract_tokens=sizes).nlargest(30, "abstract_tokens")


def token_count(tokenizer, text):
    return len(tokenizer(text, truncation=False, verbose=False)["input_ids"])


def build_chunks(papers, tokenizer):
    groups = {"fixed": [], "semantic": []}
    forced_splits = 0
    for row in papers.itertuples(index=False):
        # Reserve space for chunk text even if an unusually long title appears.
        title = row.title
        if token_count(tokenizer, title) > 130:
            offsets = tokenizer(title, add_special_tokens=False, truncation=True, max_length=128,
                                return_offsets_mapping=True)["offset_mapping"]
            title = title[:offsets[-1][1]]

        def fits(text):
            return token_count(tokenizer, paper_text(title, text)) <= MAX_TOKENS

        semantic, split = semantic_chunks(row.abstract, fits)
        forced_splits += split
        for method, chunks in (("fixed", fixed_chunks(row.abstract, fits)), ("semantic", semantic)):
            for number, text in enumerate(chunks, 1):
                metadata = dict(arxiv_id=row.id, title=row.title, chunk_text=text, chunk_number=number,
                                year=int(row.year), category=row.category)
                groups[method].append((paper_text(title, text), metadata))
    return groups, forced_splits


def main():
    frame = load_papers()
    client = pinecone_client()
    model = load_model()
    papers = longest_papers(frame, model.tokenizer)
    groups, forced_splits = build_chunks(papers, model.tokenizer)
    print(f"Papers: {len(papers)}; longest abstract: {papers['abstract_tokens'].max()} tokens; "
          f"abstracts above {MAX_TOKENS}: {(papers['abstract_tokens'] > MAX_TOKENS).sum()}")
    print(f"Fixed: {MAX_WORDS} words, {OVERLAP} overlap; semantic: "
          f"{MAX_WORDS} words, with {forced_splits} oversized sentences split.")
    target = f"{namespace(frame)}-chunks-w{MAX_WORDS}-o{OVERLAP}-v1"
    indexes = {}
    for method, chunks in groups.items():
        lengths = [len(metadata["chunk_text"].split()) for _, metadata in chunks]
        print(f"{method}: {len(chunks)} chunks; mean length {sum(lengths) / len(lengths):.1f} words")
        vectors = encode(model, [text for text, _ in chunks], progress=True)
        records = [
            {"id": f"chunk_{i}", "values": vector.tolist(), "metadata": metadata}
            for i, (vector, (_, metadata)) in enumerate(zip(vectors, chunks, strict=True))
        ]
        index_name = f"arxiv-chunks-{method}"
        index = open_index(client, index_name, create=True)
        upload(index, records, target, index_name, batch_size=100)
        indexes[method] = index
    for text, vector in zip(QUERIES, encode(model, list(QUERIES)), strict=True):
        print(f'\nQuery: "{text}"')
        for method, index in indexes.items():
            matches = query(index, target, vector)
            print(f"{method} top-{TOP_K}:")
            if not matches:
                print("  No matches.")
            for rank, hit in enumerate(matches, 1):
                m = hit.metadata
                print(f"  {rank}. {m['title']} | {m['arxiv_id']} | "
                      f"chunk {int(m['chunk_number'])} | score={hit.score:.6f}")
                print(f"     {preview(m['chunk_text'])}")
            counts = Counter(hit.metadata["arxiv_id"] for hit in matches)
            print(f"  Distinct papers: {len(counts)}; repeated same-paper hits: {sum(counts.values()) - len(counts)}")


if __name__ == "__main__":
    main()
