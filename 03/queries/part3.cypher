// Запит 1
MATCH (g:Genre {name: 'Thriller'})<-[:HAS_GENRE]-(m:Movie)<-[r:RATED]-(:User)
WITH m, avg(r.rating) AS avgRating, count(r) AS numRatings
WHERE avgRating > 4.0 AND numRatings >= 50
RETURN m.title AS title, round(avgRating, 3) AS avgRating, numRatings
ORDER BY avgRating DESC, numRatings DESC;

// Запит 2
MATCH (u:User)-[r:RATED]->(:Movie)
WHERE r.rating = 5
WITH u, count(r) AS fives
WHERE fives > 50
RETURN u.userId AS userId, u.gender AS gender, u.age AS age, fives
ORDER BY fives DESC
LIMIT 25;

// Запит 2, загальна кількість
MATCH (u:User)-[r:RATED]->(:Movie)
WHERE r.rating = 5
WITH u, count(r) AS fives
WHERE fives > 50
RETURN count(u) AS usersWithMoreThan50Fives;

// Запит 3
MATCH (u1:User {userId: 1})-[r1:RATED]->(m:Movie)<-[r2:RATED]-(u2:User {userId: 2})
WHERE r1.rating >= 4 AND r2.rating >= 4
RETURN m.title AS title, r1.rating AS user1Rating, r2.rating AS user2Rating
ORDER BY user1Rating + user2Rating DESC, title;

// Запит 4
MATCH (g:Genre)<-[:HAS_GENRE]-(:Movie)<-[r:RATED]-(:User)
WITH g,
     avg(r.rating)  AS avgRating,
     count(r)       AS numRatings,
     sum(CASE WHEN r.rating >= 4 THEN 1 ELSE 0 END) AS high
RETURN g.name AS genre,
       round(avgRating, 3) AS avgRating,
       numRatings,
       round(100.0 * high / numRatings, 1) AS share45
ORDER BY avgRating DESC;

// Запит 5
MATCH (target:User {userId: 1})-[r1:RATED]->(m:Movie)<-[r2:RATED]-(other:User)
WHERE r1.rating >= 4 AND r2.rating >= 4 AND other <> target
WITH target, other, count(m) AS overlap
WHERE overlap >= 10
ORDER BY overlap DESC
LIMIT 25
MATCH (other)-[r:RATED]->(rec:Movie)
WHERE r.rating >= 4 AND NOT (target)-[:RATED]->(rec)
WITH rec, count(DISTINCT other) AS recommenders, avg(r.rating) AS avgBySimilar
RETURN rec.title AS recommendation, recommenders, round(avgBySimilar, 2) AS avgBySimilar
ORDER BY recommenders DESC, avgBySimilar DESC
LIMIT 10;

// Запит 6
MATCH (a:User {userId: 1}), (b:User {userId: 2})
MATCH p = shortestPath((a)-[:RATED*..10]-(b))
RETURN length(p) AS pathLength,
       [n IN nodes(p) | CASE WHEN n:User THEN 'User ' + n.userId ELSE n.title END] AS chain;

// Запит 6, пара без спільних фільмів (довший шлях)
MATCH (a:User {userId: 3273}), (b:User {userId: 4068})
MATCH p = shortestPath((a)-[:RATED*..10]-(b))
RETURN length(p) AS pathLength,
       [n IN nodes(p) | CASE WHEN n:User THEN 'User ' + n.userId ELSE n.title END] AS chain;
