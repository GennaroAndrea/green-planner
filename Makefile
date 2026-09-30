.PHONY: demo demo-local cert snapshot docker-build docker-run

# HTTPS=1 serves the backend over HTTPS with tls/ (make cert first), e.g. `make demo HTTPS=1`
DEMO_FLAGS := $(if $(HTTPS),--https)

# Full demo: frontend build, backend on :8080, public URL via ngrok (scripts/demo.sh)
demo:
	scripts/demo.sh $(DEMO_FLAGS)

# The same app on http://localhost:8080 (https with HTTPS=1), without ngrok
demo-local:
	scripts/demo.sh --local $(DEMO_FLAGS)

# Self-signed TLS certificate in tls/ (gitignored); extra names/IPs: make cert NAMES="192.168.1.50"
cert:
	scripts/make_cert.sh $(NAMES)

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
