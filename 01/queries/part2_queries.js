// queries/part2_queries.js
// Запуск: mongosh "ВАШ_URI" --file queries/part2_queries.js
db = db.getSiblingDB("spotify");

// ---------- Завдання 1. Треки для вечірки ----------
const partyFilter = {
  "audio_features.danceability": { $gt: 0.7 },
  "audio_features.energy": { $gt: 0.7 },
  duration_ms: { $gte: 180000, $lte: 300000 }
};
const partyTracks = db.tracks
  .find(partyFilter, {
    _id: 0, track_name: 1, artists: 1, duration_sec: 1, popularity: 1,
    "audio_features.danceability": 1, "audio_features.energy": 1
  })
  .sort({ popularity: -1 })
  .limit(10)
  .toArray();
print("\n=== Завдання 1. Треки для вечірки ===");
print("Всього знайдено: " + db.tracks.countDocuments(partyFilter));
printjson(partyTracks);

// ---------- Завдання 2. Виконавці, у яких усі треки популярні ----------
// Дублікати track_id (один трек у кількох жанрах) прибираємо, щоб не
// рахувати один і той самий трек кілька разів.
const popularArtists = db.tracks.aggregate([
  { $group: { _id: "$track_id", artists: { $first: "$artists" }, popularity: { $first: "$popularity" } } },
  { $unwind: "$artists" },
  {
    $group: {
      _id: "$artists",
      track_count: { $sum: 1 },
      min_popularity: { $min: "$popularity" },
      avg_popularity: { $avg: "$popularity" }
    }
  },
  { $match: { track_count: { $gte: 3 }, min_popularity: { $gte: 60 } } },
  {
    $project: {
      _id: 0,
      artist: "$_id",
      track_count: 1,
      min_popularity: 1,
      avg_popularity: { $round: ["$avg_popularity", 1] }
    }
  },
  { $sort: { avg_popularity: -1, track_count: -1, artist: 1 } },
  { $limit: 20 }
]).toArray();
print("\n=== Завдання 2. Топ-20 популярних виконавців ===");
printjson(popularArtists);

// ---------- Завдання 3. Нетипові треки (tempo > mean + 2*std) ----------
const tempoOutliers = db.tracks.aggregate([
  {
    $group: {
      _id: "$track_genre",
      avg_tempo: { $avg: "$audio_features.tempo" },
      std_tempo: { $stdDevPop: "$audio_features.tempo" },
      tracks: {
        $push: {
          _id: "$_id",
          track_name: "$track_name",
          popularity: "$popularity",
          artists: "$artists",
          audio_features: { tempo: "$audio_features.tempo" }
        }
      }
    }
  },
  { $addFields: { outlier_threshold: { $add: ["$avg_tempo", { $multiply: [2, "$std_tempo"] }] } } },
  {
    $project: {
      _id: 0,
      genre: "$_id",
      avg_tempo: { $round: ["$avg_tempo", 1] },
      outlier_threshold: { $round: ["$outlier_threshold", 1] },
      outlier_tracks: {
        $filter: {
          input: "$tracks",
          as: "t",
          cond: { $gt: ["$$t.audio_features.tempo", "$outlier_threshold"] }
        }
      }
    }
  },
  { $match: { "outlier_tracks.0": { $exists: true } } },
  { $sort: { genre: 1 } }
]).toArray();
print("\n=== Завдання 3. Нетипові треки ===");
print("Жанрів з викидами: " + tempoOutliers.length);
print("Всього треків-викидів: " + tempoOutliers.reduce((s, g) => s + g.outlier_tracks.length, 0));
printjson(tempoOutliers.slice(0, 2));

// ---------- Завдання 4. Треки для фонової роботи ----------
const workFilter = {
  "audio_features.loudness": { $lt: -10 },
  "audio_features.speechiness": { $lt: 0.1 },
  "audio_features.instrumentalness": { $gt: 0.5 },
  explicit: false
};
const workTracks = db.tracks
  .find(workFilter, {
    _id: 0, track_name: 1, artists: 1, track_genre: 1, explicit: 1,
    "audio_features.loudness": 1, "audio_features.speechiness": 1,
    "audio_features.instrumentalness": 1
  })
  .sort({ popularity: -1 })
  .limit(10)
  .toArray();
print("\n=== Завдання 4. Треки для фонової роботи ===");
print("Всього знайдено: " + db.tracks.countDocuments(workFilter));
printjson(workTracks);
