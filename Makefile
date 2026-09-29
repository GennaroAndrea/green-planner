.PHONY: demo demo-local snapshot docker-build docker-run

# Full demo: frontend build, backend on :8080, public URL via ngrok (scripts/demo.sh)
demo:
	scripts/demo.sh

# The same app on http://localhost:8080, without ngrok
demo-local:
	scripts/demo.sh --local

# Copy the artefacts the backend loads into deploy/data/ (committed; used by the Render
# deploy and as the data fallback of scripts/demo.sh). Run after every `pipeline build`.
snapshot:
	@test -f data/processed/metadata.json || { echo "run 'uv run python -m pipeline build' first"; exit 1; }
	rm -rf deploy/data && mkdir -p deploy/data
	cp data/processed/metadata.json data/processed/zones.parquet data/processed/cells_*.parquet \
	   data/processed/layer_*.geojson deploy/data/
	@du -sh deploy/data

# The Render image, built and run locally (http://localhost:8080)
docker-build:
	docker build -t green-planner .

docker-run:
	docker run --rm -p 8080:8080 green-planner
