# Retaking the screenshots

The images in `screenshots/` were taken on a fresh dev database (migrated and seeded), 1440 px wide, saved as JPEG (quality 82). Log in as `rin.park@hartwood.test` (manager); `/it` needs the admin `aria.voss@hartwood.test`. Password for every seeded user: `hartwood-dev`.

Most images need only the normal stack (`make up`, `make migrate`, `make seed`). **The two search images** (`search-results`, `search-typeahead`) also need Meilisearch with the seed indexed, or the page says "Search is temporarily unavailable":

1. Run Meilisearch v1.54.0 (the version in `docker-compose.yml`). Without Docker, download the `meilisearch-linux-amd64` binary from the project's GitHub release `v1.54.0` and start it with `MEILI_MASTER_KEY=<key> MEILI_ENV=development ./meilisearch`.
2. Point the API at it: `MEILI_URL=http://localhost:7700` and `MEILI_API_KEY=<key>` (the compose file calls the key `MEILI_MASTER_KEY`).
3. Build the index: `python -m app.search.reindex` (or `make reindex`). The seed gives 89 documents; the query `ALF` then returns 41 hits.
4. Shoot `/search?q=ALF` for the results page; for the type-ahead, open any page, press `/`, type `ALF`, wait about 2 s.

If search is down when you retake, keep the existing search images rather than replacing them with the "unavailable" page.
