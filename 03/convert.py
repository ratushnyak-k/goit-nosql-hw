import csv
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE
DST = BASE / "import"
DST.mkdir(exist_ok=True)

YEAR_RE = re.compile(r"\((\d{4})\)\s*$")


def convert(name, header, transform):
    rows = 0
    with open(SRC / f"{name}.dat", encoding="latin-1") as f_in, \
         open(DST / f"{name}.csv", "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(header)
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            writer.writerow(transform(line.split("::")))
            rows += 1
    print(f"{name}.csv: {rows} рядків")


def movie_row(parts):
    movie_id, title, genres = parts
    m = YEAR_RE.search(title)
    year = m.group(1) if m else ""
    return [movie_id, title, year, genres]


convert("movies", ["movieId", "title", "year", "genres"], movie_row)
convert("ratings", ["userId", "movieId", "rating", "timestamp"], lambda p: p)
convert("users", ["userId", "gender", "age", "occupation"], lambda p: p[:4])
