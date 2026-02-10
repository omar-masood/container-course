# Lab 2: Network Debugging — Solution Notes

## Bug 1: Frontend and API on Different Networks

**Symptom:** `curl localhost:8080/api/items` returns 502 Bad Gateway.

**Root cause:** The `frontend` service is only on `frontend-net`, while the `api` service is only on `backend-net`. Services on different networks cannot communicate—Docker's bridge networks are isolated from each other.

**Fix:** Add `backend-net` to the frontend's `networks:` list. The frontend needs to be on both networks: `frontend-net` for external access and `backend-net` to reach the API.

**How to find it:**
```bash
docker compose exec frontend sh -c "getent hosts api"
# Returns nothing — can't resolve "api"

docker network inspect starter_frontend-net
# Only shows frontend container

docker network inspect starter_backend-net
# Only shows api and db containers
```

## Bug 2: Wrong Database Hostname

**Symptom:** The API container logs show `Could not connect to database` errors pointing to hostname `database`.

**Root cause:** The `DB_HOST` environment variable is set to `database`, but the MySQL service is named `db` in the Compose file. Docker DNS registers service names, so only `db` resolves.

**Fix:** Change `DB_HOST: database` to `DB_HOST: db`.

**How to find it:**
```bash
docker compose logs api
# Shows connection errors referencing "database"

docker compose exec api sh -c "getent hosts database"
# Returns nothing

docker compose exec api sh -c "getent hosts db"
# Returns the MySQL container's IP
```

## Bug 3: Wrong Proxy Port in nginx

**Symptom:** Even after fixing bugs 1 and 2, `curl localhost:8080/api/items` returns 502 Bad Gateway.

**Root cause:** The nginx config proxies to `api:5050` but the API listens on port `5000` (see the Dockerfile's `EXPOSE 5000` and `app.run(port=5000)`).

**Fix:** Change `proxy_pass http://api:5050/` to `proxy_pass http://api:5000/` in both `location` blocks in `frontend/nginx.conf`.

**How to find it:**
```bash
docker compose exec frontend sh -c "wget -qO- http://api:5050/health"
# Connection refused

docker compose exec frontend sh -c "wget -qO- http://api:5000/health"
# Returns {"status": "healthy"}
```

## Key Takeaways

1. Services can only communicate if they share a network
2. Service names in environment variables must match the service names in the Compose file exactly
3. Proxy ports must match the port the upstream service is actually listening on
4. `getent hosts`, `nc -zv`, and `wget`/`curl` are essential debugging tools inside containers
