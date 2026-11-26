// Запит 1
MATCH (n)
WITH labels(n)[0] AS label, COUNT { (n)--() } AS degree
RETURN label,
       count(*)                          AS nodes,
       min(degree)                       AS minDegree,
       round(avg(degree), 1)             AS avgDegree,
       percentileDisc(degree, 0.5)       AS medianDegree,
       percentileDisc(degree, 0.99)      AS p99Degree,
       max(degree)                       AS maxDegree
ORDER BY maxDegree DESC;

// Запит 2
MATCH (n)
WITH n, COUNT { (n)--() } AS degree
ORDER BY degree DESC
LIMIT 10
RETURN labels(n)[0] AS label,
       coalesce(n.name, n.title, 'User ' + toString(n.userId)) AS node,
       degree;

// Запит 3
MATCH (g:Genre)
OPTIONAL MATCH (g)<-[:HAS_GENRE]-(m:Movie)
WITH g, count(m) AS movies, sum(COUNT { (m)<-[:RATED]-() }) AS ratingsThroughGenre
RETURN g.name AS genre, movies, ratingsThroughGenre,
       round(100.0 * movies / 3883, 1) AS pctOfAllMovies
ORDER BY movies DESC;

// Запит 4
MATCH (m:Movie)
WITH m, COUNT { (m)<-[:RATED]-() } AS ratings
ORDER BY ratings DESC
LIMIT 10
RETURN m.title AS movie, ratings, round(100.0 * ratings / 6040, 1) AS pctOfUsers;

// Запит 5
MATCH (u:User)
WITH u, COUNT { (u)-[:RATED]->() } AS ratings
ORDER BY ratings DESC
LIMIT 10
RETURN u.userId AS userId, ratings, round(100.0 * ratings / 3883, 1) AS pctOfMovies;

// Запит 6
MATCH (m:Movie {movieId: 1598})<-[:RATED]-(u:User)-[:RATED]->(other:Movie)
RETURN 'Desperate Measures (звичайний, 111 оцінок = медіана)' AS start, count(*) AS rowsExpanded;

MATCH (m:Movie {movieId: 2858})<-[:RATED]-(u:User)-[:RATED]->(other:Movie)
RETURN 'American Beauty (супервузол)' AS start, count(*) AS rowsExpanded;

MATCH (g:Genre {name: 'Drama'})<-[:HAS_GENRE]-(m:Movie)<-[:RATED]-(u:User)
RETURN 'Genre Drama' AS start, count(*) AS rowsExpanded;
