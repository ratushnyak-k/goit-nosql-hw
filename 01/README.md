# ДЗ 1 — MongoDB: схема, запити, індекси (Spotify Tracks Dataset)

## Структура

```
01/
├── .env.example            # шаблон .env
├── requirements.txt
├── scripts/
│   ├── 01_load_data.py     # CSV -> колекція tracks_raw
│   └── 02_transform.js     # tracks_raw -> tracks (aggregation pipeline)
└── queries/
    ├── part2_queries.js    # Частина 2 — 4 запити
    └── part2_queries.js    # Частина 2 — 4 запити
```

## Налаштування оточення

1. Створіть кластер **MongoDB Atlas M0** (AWS), користувача в Database Access, IP у Network Access, скопіюйте рядок `mongodb+srv://...`.
2. Встановіть залежності:
   ```bash
   cd 01
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Створіть `.env` у папці `01/`:
   ```
   MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/
   ```
4. Завантажте датасет [Spotify Tracks Dataset](https://www.kaggle.com/datasets/maharshipandya/-spotify-tracks-dataset) і покладіть `dataset.csv` у папку `01/`:
   ```bash
   kaggle datasets download -d maharshipandya/-spotify-tracks-dataset --unzip
   ```
5. Порядок запуску (потрібен `mongosh`):
   ```bash
   python scripts/01_load_data.py
   mongosh "$MONGO_URI" --file scripts/02_transform.js
   mongosh "$MONGO_URI" --file queries/part2_queries.js
   ```

Після завантаження: `tracks_raw` — **113 999** документів (1 рядок без виконавця/назви відкинуто), `tracks` — **113 999**.

## Частина 1 — Схема даних

Приклад документа в колекції `tracks`:

```json
{
  "_id": { "$oid": "6ae89b74b57451b6dfed1e6f" },
  "track_id": "5SuOikwiRyPMVoIQDJUgSV",
  "album_name": "Comedy",
  "track_name": "Comedy",
  "popularity": 73,
  "duration_ms": 230666,
  "explicit": false,
  "track_genre": "acoustic",
  "artists": ["Gen Hoshino"],
  "audio_features": {
    "danceability": 0.676, "energy": 0.461, "loudness": -6.746,
    "speechiness": 0.143, "acousticness": 0.0322, "instrumentalness": 0.00000101,
    "liveness": 0.358, "valence": 0.715, "tempo": 87.917,
    "key": 1, "mode": 0, "time_signature": 4
  },
  "duration_sec": 230.7,
  "popularity_tier": "high"
}
```

| Поле | Тип | Опис |
|---|---|---|
| `track_id` | string | Spotify ID (не унікальний: один трек може бути в кількох жанрах) |
| `track_name`, `album_name` | string | назва треку / альбому |
| `artists` | array<string> | виконавці, з рядка `"A;B"` → `["A","B"]` |
| `popularity` | int | 0–100 |
| `popularity_tier` | string | `high` (≥70), `medium` (40–69), `low` (<40) |
| `duration_ms` / `duration_sec` | int / double | тривалість; секунди округлені до 0.1 |
| `explicit` | bool | наявність explicit-контенту |
| `track_genre` | string | жанр (114 жанрів) |
| `audio_features` | object | 12 аудіохарактеристик |

### Питання 1. Чому `audio_features` — окремий вкладений об'єкт?

Аудіохарактеристики — це одна логічна група (12 числових метрик від Spotify API), що описує «звучання», на відміну від метаданих (назва, альбом, жанр, популярність). Вкладення дає:

- **Читабельність і семантику**: документ має очевидну структуру; одразу видно, що є метаданими, а що — ознаками для аналізу.
- **Зручні проєкції**: `{audio_features: 1}` повертає всі ознаки одним полем (наприклад, для ML), а `{audio_features: 0}` — прибирає їх, коли потрібні лише метадані.
- **Простоту еволюції**: нові метрики додаються всередину об'єкта, не «засмічуючи» корінь.
- Звернення через dot-notation (`"audio_features.tempo"`) працює у фільтрах, сортуванні та індексах так само, як для плоских полів (див. індекси в Частині 3).

**Коли вигідно**: дані мають зв'язок 1:1 з документом, читаються разом із ним, мають обмежений фіксований розмір (тут — 12 полів).

**Коли створює проблеми**:
- довші шляхи в запитах та агрегаціях (`"$audio_features.tempo"`), легко помилитися;
- оновлення всього об'єкта `$set: {audio_features: {...}}` перезапише його повністю — треба оновлювати конкретні поля через dot-notation;
- порівняння з вкладеним об'єктом цілком (`{audio_features: {...}}`) чутливе до порядку полів;
- глибоке вкладення або необмежено зростаючі масиви всередині роздувають документ (ліміт 16 MB) — тоді краще окрема колекція.

### Питання 2. Чому виконавці — масив, а не рядок?

У сирих даних `artists` — рядок `"Rauw Alejandro;Lyanno;Brray"`. Щоб знайти треки виконавця, довелося б використовувати regex (`/(^|;)Lyanno(;|$)/`), що повільно, не використовує індекс ефективно та легко дає хибні збіги (`"Drake"` знайде і `"Drake Bell"`).

З масивом:
- **точний пошук** `db.tracks.find({artists: "Lyanno"})` — MongoDB сама шукає по елементах масиву;
- **multikey-індекс** `{artists: 1}` робить такий пошук швидким;
- **пошук колаборацій**: `{artists: {$all: ["Bad Bunny", "Rauw Alejandro"]}}`; кількість виконавців: `{artists: {$size: 1}}` (сольні треки);
- **агрегації по виконавцях**: `$unwind: "$artists"` + `$group` — саме так зроблено Завдання 2 Частини 2; з рядком треба було б кожного разу робити `$split` у pipeline.

## Частина 2 — Запити

Файл: [`queries/part2_queries.js`](queries/part2_queries.js).

### Завдання 1. Треки для вечірки

```js
db.tracks.find({
  "audio_features.danceability": { $gt: 0.7 },
  "audio_features.energy": { $gt: 0.7 },
  duration_ms: { $gte: 180000, $lte: 300000 }
}).sort({ popularity: -1 })
```

Знайдено **7 311** треків. Топ: `Calm Down (with Selena Gomez)` — Rema, Selena Gomez (92), `LOKERA` — Rauw Alejandro (91), `Party` — Bad Bunny (90).
Кілька умов у одному об'єкті поєднуються як неявний `AND`; для `duration_ms` два оператори на одному полі задають діапазон. Деякі треки дублюються, бо в датасеті той самий `track_id` присутній у кількох жанрах.

### Завдання 2. Виконавці, у яких усі треки популярні

Pipeline: `$group` по `track_id` (прибираємо дублікати між жанрами, інакше трек рахувався б кілька разів) → `$unwind: "$artists"` (трек з кількома виконавцями зараховується кожному) → `$group` по виконавцю з `$sum`, `$min`, `$avg` → `$match` (`track_count ≥ 3`, `min_popularity ≥ 60`) → `$round` до 1 знака → `$sort` за середньою популярністю → `$limit: 20`.

| # | Виконавець | Треків | Мін. | Сер. |
|---|---|---|---|---|
| 1 | Harry Styles | 3 | 89 | 92 |
| 2 | Olivia Rodrigo | 5 | 86 | 87.4 |
| 3 | IVE | 3 | 79 | 84 |
| 4 | Morgan Wallen | 3 | 81 | 83.3 |
| 5 | One Direction | 5 | 80 | 83 |
| 6 | Lil Nas X | 8 | 77 | 82.8 |
| 7 | Måneskin | 5 | 76 | 82.6 |
| 8 | TV Girl | 3 | 80 | 81.7 |
| 9 | Mora | 6 | 69 | 80.3 |
| 10 | Luke Combs | 3 | 79 | 80.3 |
| 11 | Maroon 5 | 3 | 70 | 79.7 |
| 12 | Mitski | 6 | 75 | 78.3 |
| 13 | Mark Ronson | 3 | 74 | 78.3 |
| 14 | LE SSERAFIM | 4 | 75 | 78 |
| 15 | Beach Bunny | 3 | 73 | 78 |
| 16 | Shubh | 5 | 69 | 77.8 |
| 17 | SZA | 4 | 65 | 77.8 |
| 18 | Jhay Cortez | 3 | 75 | 77.7 |
| 19 | Mother Mother | 3 | 76 | 77.3 |
| 20 | Tiago PZK | 4 | 72 | 77 |

### Завдання 3. Нетипові треки за темпом

Pipeline: `$group` по `track_genre` з `$avg` і `$stdDevPop` по `audio_features.tempo` та `$push` треків → `$addFields` поріг `avg + 2·std` → `$filter` масиву треків за `tempo > outlier_threshold` → `$match` жанрів, де є хоча б один викид.
Результат: **112** жанрів, **3 506** треків-викидів. Приклад (збігається з прикладом у завданні):

```json
{
  "genre": "acoustic",
  "avg_tempo": 119,
  "outlier_threshold": 178.5,
  "outlier_tracks": [
    { "_id": {"$oid": "..."}, "track_name": "Can't Help Falling In Love",
      "popularity": 71, "artists": ["Kina Grannis"], "audio_features": { "tempo": 181.74 } }
  ]
}
```

Використано один прохід (`$push` + `$filter`) замість `$lookup` колекції самої на себе: кожен жанр має ~1000 треків, тож масив комфортно вміщується в ліміт документа.

### Завдання 4. Треки для фонової роботи

```js
db.tracks.find({
  "audio_features.loudness": { $lt: -10 },
  "audio_features.speechiness": { $lt: 0.1 },
  "audio_features.instrumentalness": { $gt: 0.5 },
  explicit: false
})
```

Знайдено **9 324** треки (переважно жанри `ambient`, `classical`, `sleep`, `piano`, `new-age`).
