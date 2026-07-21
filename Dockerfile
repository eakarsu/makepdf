FROM python:3.13-slim AS build
WORKDIR /src
RUN pip install --no-cache-dir uv==0.8.22
COPY pyproject.toml uv.lock ./
COPY makepdf ./makepdf
RUN uv build --wheel

FROM python:3.13-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends clamav-daemon poppler-utils tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 makepdf \
    && useradd --system --uid 10001 --gid makepdf --home-dir /nonexistent makepdf \
    && mkdir -p /data /tmp/makepdf \
    && chown -R makepdf:makepdf /data /tmp/makepdf
COPY --from=build /src/dist/*.whl /tmp/package.whl
RUN pip install --no-cache-dir /tmp/package.whl 'makepdf[ocr]' \
    && rm /tmp/package.whl
COPY start.sh /app/start.sh
RUN chmod 0555 /app/start.sh
USER 10001:10001
WORKDIR /app
ENV MAKEPDF_ENV=production MAKEPDF_DATA_DIR=/data MAKEPDF_TEMP_DIR=/tmp PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
ENTRYPOINT ["/app/start.sh"]
CMD ["api"]
