FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NUMBA_CACHE_DIR=/tmp/pathsnap-numba \
    PATHSNAP_JOBS_DIR=/app/data/jobs

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 pathsnap \
    && useradd -u 10001 -g pathsnap --create-home pathsnap
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY artifacts ./artifacts
COPY data/demo ./data/demo
RUN mkdir -p /app/data/jobs /tmp/pathsnap-numba \
    && chown pathsnap:pathsnap /app/data/jobs /tmp/pathsnap-numba

USER pathsnap
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
