# scripts/01_load_data.py
import os
import pandas as pd
from pymongo import MongoClient
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.environ["MONGO_URI"]
DB_NAME = "spotify"
CSV_PATH = "dataset.csv"  # шлях до завантаженого файлу з Kaggle
BATCH_SIZE = 1000

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Видаляємо колекцію якщо існує — для ідемпотентного повторного запуску
db["tracks_raw"].drop()

df = pd.read_csv(CSV_PATH)
print(f"Завантажуємо {len(df)} треків...")

df["explicit"] = df["explicit"].astype(bool)

int_cols = ["popularity", "duration_ms", "key", "mode", "time_signature"]
for col in int_cols:
    df[col] = df[col].astype(int)

float_cols = [
    "danceability", "energy", "loudness", "speechiness",
    "acousticness", "instrumentalness", "liveness",
    "valence", "tempo",
]
for col in float_cols:
    df[col] = df[col].astype(float)

# Прибираємо записи, в яких немає виконавця або назви треку
query = df["artists"].isna() | df["track_name"].isna()
records = df[~query].to_dict("records")

# Завантажуємо батчами
for i in tqdm(range(0, len(records), BATCH_SIZE)):
    db["tracks_raw"].insert_many(records[i : i + BATCH_SIZE])

print(f"Завантажено документів: {db['tracks_raw'].count_documents({})}")
print("Приклад документа:")
print(db["tracks_raw"].find_one())
