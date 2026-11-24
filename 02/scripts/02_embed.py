import argparse

import numpy as np

from common import EMBEDDINGS, ENCODER, encode, load_model, load_papers, paper_text, save_embeddings


def main():
    parser = argparse.ArgumentParser(description="Encode titles and abstracts with SPECTER2 Base.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--device", help="Override auto-detected PyTorch device (e.g. cpu or cuda).")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive.")
    frame = load_papers()
    texts = [paper_text(row.title, row.abstract) for row in frame.itertuples(index=False)]
    model = load_model(args.device)
    vectors = encode(model, texts, batch_size=args.batch_size, progress=True)
    save_embeddings(frame, vectors)
    print(f"Encoder: {ENCODER}")
    print(f"Texts: {len(vectors):,}; dimension: {vectors.shape[1]}; "
          f"first vector norm: {np.linalg.norm(vectors[0]):.6f}")
    print(f"Saved {EMBEDDINGS}")


if __name__ == "__main__":
    main()
