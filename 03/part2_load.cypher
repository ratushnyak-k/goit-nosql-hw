CREATE CONSTRAINT user_id IF NOT EXISTS
FOR (u:User) REQUIRE u.userId IS UNIQUE;

CREATE CONSTRAINT movie_id IF NOT EXISTS
FOR (m:Movie) REQUIRE m.movieId IS UNIQUE;

CREATE CONSTRAINT genre_name IF NOT EXISTS
FOR (g:Genre) REQUIRE g.name IS UNIQUE;

CREATE INDEX rated_rating IF NOT EXISTS
FOR ()-[r:RATED]-() ON (r.rating);

LOAD CSV WITH HEADERS FROM 'file:///users.csv' AS row
MERGE (u:User {userId: toInteger(row.userId)})
SET u.gender     = row.gender,
    u.age        = toInteger(row.age),
    u.occupation = toInteger(row.occupation);

LOAD CSV WITH HEADERS FROM 'file:///movies.csv' AS row
MERGE (m:Movie {movieId: toInteger(row.movieId)})
SET m.title = row.title,
    m.year  = toInteger(row.year);

LOAD CSV WITH HEADERS FROM 'file:///movies.csv' AS row
MATCH (m:Movie {movieId: toInteger(row.movieId)})
UNWIND split(row.genres, '|') AS genreName
MERGE (g:Genre {name: genreName})
MERGE (m)-[:HAS_GENRE]->(g);

// parallel: false, бо одні й ті самі вузли User/Movie є в різних батчах і паралельний MERGE ребер блокувався б
CALL apoc.periodic.iterate(
  "LOAD CSV WITH HEADERS FROM 'file:///ratings.csv' AS row RETURN row",
  "MATCH (u:User  {userId:  toInteger(row.userId)})
   MATCH (m:Movie {movieId: toInteger(row.movieId)})
   MERGE (u)-[r:RATED]->(m)
   SET r.rating    = toInteger(row.rating),
       r.timestamp = toInteger(row.timestamp)",
  {batchSize: 10000, parallel: false}
)
YIELD batches, total, committedOperations, failedOperations, errorMessages
RETURN batches, total, committedOperations, failedOperations, errorMessages;

MATCH (u:User)  RETURN count(u) AS users;
MATCH (m:Movie) RETURN count(m) AS movies;
MATCH (g:Genre) RETURN count(g) AS genres;
MATCH ()-[r:RATED]->()     RETURN count(r) AS ratings;
MATCH ()-[h:HAS_GENRE]->() RETURN count(h) AS hasGenre;

// дублі оцінок: має повернути 0 рядків
MATCH (u:User)-[r:RATED]->(m:Movie)
WITH u, m, count(r) AS c WHERE c > 1
RETURN u.userId, m.movieId, c LIMIT 10;
