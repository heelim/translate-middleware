# Korean Translation Middleware Deployment Guide

This guide covers production deployment for the ko-translate-middleware service.

## Prerequisites

- Python 3.10+
- Docker (for containerized deployment)
- systemd (for Linux service management)
- Nginx (for reverse proxy)
- LM Studio or OpenAI API (for translation engine)

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KO_TRANSLATE_ENGINE` | Yes | `local` | Translation engine: `local` or `openai` |
| `KO_TRANSLATE_LOCAL_MODEL_URL` | No | `http://localhost:1234` | Local model server URL (LM Studio) |
| `KO_TRANSLATE_LOCAL_MODEL_NAME` | No | `gemma-4-e4b-uncensored-hauhaucs-aggressive` | Model name for local engine |
| `KO_TRANSLATE_FAIL_MODE` | No | `open` | Failure behavior: `open`, `closed`, or `configurable` |
| `KO_TRANSLATE_LOG_LEVEL` | No | `info` | Log level: `debug`, `info`, `warning`, `error` |
| `KO_TRANSLATE_TARGET_URL` | No | `https://api.openai.com/v1/chat/completions` | Upstream API endpoint |
| `KO_TRANSLATE_OPENAI_API_KEY` | If using OpenAI | - | OpenAI API key for cloud translation |
| `KO_TRANSLATE_OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | OpenAI base URL |

### Fail Mode Behavior

- **`open`**: Pass through untranslated text when translation fails
- **`closed`**: Return an error response on translation failure
- **`configurable`**: Use fallback engine when primary fails

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
EXPOSE 8080
CMD ["ko-proxy", "--host", "0.0.0.0", "--port", "8080"]
```

### Build and Run

```bash
# Build the image
docker build -t ko-translate-proxy:latest .

# Run the container
docker run -d \
  --name ko-translate-proxy \
  -p 8080:8080 \
  -e KO_TRANSLATE_ENGINE=local \
  -e KO_TRANSLATE_LOCAL_MODEL_URL=http://host.docker.internal:1234 \
  -e KO_TRANSLATE_LOG_LEVEL=info \
  --restart unless-stopped \
  ko-translate-proxy:latest
```

### Docker Compose Example

```yaml
version: '3.8'

services:
  ko-translate-proxy:
    build: .
    container_name: ko-translate-proxy
    ports:
      - "8080:8080"
    environment:
      - KO_TRANSLATE_ENGINE=local
      - KO_TRANSLATE_LOCAL_MODEL_URL=http://lm-studio:1234
      - KO_TRANSLATE_LOCAL_MODEL_NAME=gemma-4-e4b-uncensored-hauhaucs-aggressive
      - KO_TRANSLATE_FAIL_MODE=open
      - KO_TRANSLATE_LOG_LEVEL=info
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  lm-studio:
    image: lmstudio/local
    container_name: lm-studio
    ports:
      - "1234:1234"
    volumes:
      - ./models:/root/.cache/lm-studio
    restart: unless-stopped
```

## Systemd Service Deployment

### Service File

Save as `/etc/systemd/system/ko-translate-proxy.service`:

```ini
[Unit]
Description=Korean Translation Proxy
After=network.target

[Service]
Type=simple
User=ko-translate
Group=ko-translate
WorkingDirectory=/opt/ko-translate
ExecStart=/usr/local/bin/ko-proxy --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ko-translate-proxy

# Environment variables
Environment="KO_TRANSLATE_ENGINE=local"
Environment="KO_TRANSLATE_LOCAL_MODEL_URL=http://127.0.0.1:1234"
Environment="KO_TRANSLATE_LOG_LEVEL=info"

[Install]
WantedBy=multi-user.target
```

### Installation Steps

```bash
# Create service user
sudo useradd -r -s /bin/false ko-translate

# Install the package
cd /opt/ko-translate
pip install -e .

# Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl enable ko-translate-proxy
sudo systemctl start ko-translate-proxy

# Check status
sudo systemctl status ko-translate-proxy
```

### Service Management

```bash
# View logs
sudo journalctl -u ko-translate-proxy -f

# Restart service
sudo systemctl restart ko-translate-proxy

# Stop service
sudo systemctl stop ko-translate-proxy
```

## Nginx Reverse Proxy Configuration

### Configuration File

Save as `/etc/nginx/sites-available/ko-translate-proxy`:

```nginx
upstream ko_translate_backend {
    server 127.0.0.1:8080;
    keepalive 32;
}

# Rate limiting zone
limit_req_zone $binary_remote_addr zone=translate_limit:10m rate=30r/s;

server {
    listen 80;
    server_name translate.example.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name translate.example.com;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/translate.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/translate.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Proxy settings
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";

    # Timeout settings
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;

    # Buffer settings
    proxy_buffering on;
    proxy_buffer_size 4k;
    proxy_buffers 8 4k;

    # Health check endpoint (no rate limiting)
    location /health {
        proxy_pass http://ko_translate_backend;
        proxy_set_header Host $host;
        access_log off;
    }

    # Metrics endpoint (no rate limiting)
    location /metrics {
        proxy_pass http://ko_translate_backend;
        proxy_set_header Host $host;
        access_log off;
    }

    # Main translation API with rate limiting
    location /v1/chat/completions {
        limit_req zone=translate_limit burst=50 nodelay;

        proxy_pass http://ko_translate_backend;
        proxy_set_header Host $host;

        # For streaming responses
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
    }

    # Root endpoint
    location / {
        proxy_pass http://ko_translate_backend;
        proxy_set_header Host $host;
    }
}
```

### Enable and Test Configuration

```bash
# Test configuration
sudo nginx -t

# Enable site
sudo ln -s /etc/nginx/sites-available/ko-translate-proxy /etc/nginx/sites-enabled/

# Reload Nginx
sudo systemctl reload nginx
```

## Health Check Verification

After deployment, verify the service is running correctly:

```bash
# Basic health check
curl http://localhost:8080/health

# Expected response:
# {"status": "ok", "lm_studio_connected": true, "uptime_seconds": 123.45}

# Check metrics
curl http://localhost:8080/metrics

# Expected output includes:
# request_count_total <count>
# translation_latency_ms p50=<value> p95=<value> p99=<value>

# Test translation via CLI
ko-translate "안녕하세요" --direction ko-en

# Test via proxy endpoint (with a chat completion request)
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: test-session-123" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "안녕하세요, 오늘 날씨가怎么样?"}]
  }'
```

## Rollback Procedures

### Docker Rollback

```bash
# List container images
docker images ko-translate-proxy

# Tag current version as backup
docker tag ko-translate-proxy:latest ko-translate-proxy:rollback

# Pull previous version (or use specific tag)
docker pull ko-translate-proxy:previous-version

# Stop current container
docker stop ko-translate-proxy

# Remove old container
docker rm ko-translate-proxy

# Start with previous version
docker run -d \
  --name ko-translate-proxy \
  -p 8080:8080 \
  -e KO_TRANSLATE_ENGINE=local \
  --restart unless-stopped \
  ko-translate-proxy:previous-version
```

### Systemd Rollback

```bash
# Check available versions
pip index versions ko-translate-middleware

# Rollback to previous version
pip install ko-translate-middleware==1.0.x

# Restart service
sudo systemctl restart ko-translate-proxy
```

### Kubernetes Rollback

```bash
# Rollback deployment
kubectl rollout undo deployment/ko-translate-proxy

# Check rollout status
kubectl rollout status deployment/ko-translate-proxy

# Rollback to specific revision
kubectl rollout undo deployment/ko-translate-proxy --to-revision=2
```

## Failure Scenarios

### Scenario 1: Local Model Server Unavailable

**Symptoms**:
- Health check shows `lm_studio_connected: false`
- Translation requests fail or timeout

**Resolution**:
```bash
# Check if LM Studio is running
curl http://localhost:1234/v1/models

# If using OpenAI fallback, set environment
export KO_TRANSLATE_ENGINE=openai
export KO_TRANSLATE_OPENAI_API_KEY=sk-...

# Restart service
sudo systemctl restart ko-translate-proxy
```

### Scenario 2: High Latency or Timeouts

**Symptoms**:
- `translation_latency_ms` p95/p99 values are very high
- Clients report timeouts

**Resolution**:
```bash
# Check current latency metrics
curl http://localhost:8080/metrics | grep latency

# Increase timeout in config
# Edit /opt/ko-translate/config.toml:
# [proxy]
# timeout = 120.0

# Or via environment
export KO_TRANSLATE_PROXY_TIMEOUT=120

# Restart service
sudo systemctl restart ko-translate-proxy
```

### Scenario 3: Memory Issues

**Symptoms**:
- Service crashes with OOM
- `journalctl` shows memory-related errors

**Resolution**:
```bash
# Check memory usage
free -h

# Add memory limits for Docker
docker update --memory=2g --memory-swap=2g ko-translate-proxy

# For systemd, edit service file
# MemoryMax=2G
# MemorySwapMax=2G

sudo systemctl daemon-reload
sudo systemctl restart ko-translate-proxy
```

### Scenario 4: SSL Certificate Expiration

**Symptoms**:
- HTTPS requests fail
- Nginx error logs show certificate expired

**Resolution**:
```bash
# Check certificate expiration
sudo certbot certificates

# Renew certificates
sudo certbot renew --force-renewal

# Reload Nginx
sudo systemctl reload nginx
```

### Scenario 5: Disk Space Exhaustion

**Symptoms**:
- Service cannot write logs
- Database or cache operations fail

**Resolution**:
```bash
# Check disk usage
df -h

# Clean old logs
sudo journalctl --vacuum-time=7d

# Remove old Docker images
docker image prune -a

# Verify log rotation is configured
sudo cat /etc/logrotate.d/ko-translate-proxy
```

## Monitoring Recommendations

### Key Metrics to Track

1. **Health Status**: `GET /health` should return `status: ok`
2. **Request Count**: `request_count_total` counter
3. **Latency Percentiles**: p50, p95, p99 for translation latency
4. **Error Rate**: Monitor `errors` in metrics output
5. **Uptime**: `uptime_seconds` in health response

### Alerting Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Health check failure | - | 1 consecutive failure |
| Error rate | > 1% | > 5% |
| p99 latency | > 5000ms | > 10000ms |
| Memory usage | > 80% | > 95% |

### Log Aggregation

Configure structured logging to ship to your log aggregation system:

```bash
# Example: Ship logs to Loki
export KO_TRANSLATE_LOG_FORMAT=json
export KO_TRANSLATE_LOG_OUTPUT=stdout
```

The service outputs JSON-formatted logs when running in production, making it compatible with most log aggregation tools.
