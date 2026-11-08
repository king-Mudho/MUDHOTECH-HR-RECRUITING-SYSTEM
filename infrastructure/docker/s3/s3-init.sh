#!/bin/sh
# Create private MHRS buckets on the dev S3 server (SeaweedFS). Idempotent.
set -eu
EP="--endpoint-url http://s3:9000"
for bucket in mhrs-uploads-quarantine mhrs-documents mhrs-exports mhrs-public; do
  aws $EP s3api head-bucket --bucket "$bucket" 2>/dev/null || aws $EP s3api create-bucket --bucket "$bucket"
done
cat > /tmp/cors.json <<'JSON'
{"CORSRules":[{"AllowedOrigins":["http://localhost:3000"],"AllowedMethods":["PUT","GET","HEAD"],"AllowedHeaders":["*"],"ExposeHeaders":["ETag"],"MaxAgeSeconds":3000}]}
JSON
aws $EP s3api put-bucket-cors --bucket mhrs-uploads-quarantine --cors-configuration file:///tmp/cors.json || echo "CORS not applied (server may not support it)"
echo "S3 buckets ready."
