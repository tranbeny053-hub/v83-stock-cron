# Reproducible build inputs (governing plan §11.1, B3):
# - the base image is pinned by its index digest (python:3.11-slim = Python 3.11.16 when pinned, 2026-10-01);
# - the dependencies are pinned by version and sha256 (requirements.txt, generated from requirements.in);
# - SOURCE_DATE_EPOCH, when given, makes pip's compiled bytecode hash-based instead of timestamped;
# - PYTHONHASHSEED=0 on the install step alone (never at runtime) fixes pip's hash seed for that bytecode.
# The governed proof that two clean builds of one commit are identical: .github/workflows/reproducible-build.yml.
FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e

ARG SOURCE_DATE_EPOCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=7860 \
    XDG_CACHE_HOME=/tmp/.cache \
    TMPDIR=/tmp

WORKDIR /app

COPY requirements.txt .
RUN PYTHONHASHSEED=0 pip install --no-cache-dir --disable-pip-version-check --require-hashes -r requirements.txt

COPY . .

# The runtime user (uid 1000), written directly: the stock user tools would stamp the build date into
# /etc/shadow.
RUN printf 'appuser:x:1000:1000::/home/appuser:/usr/sbin/nologin\n' >> /etc/passwd \
    && printf 'appuser:x:1000:\n' >> /etc/group \
    && mkdir -p /home/appuser \
    && chown 1000:1000 /home/appuser
USER 1000

EXPOSE 7860

CMD ["uvicorn", "crypto_probability_engine.api.app:app", "--host", "0.0.0.0", "--port", "7860"]
