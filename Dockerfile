FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 vault && useradd --uid 10001 --gid vault --create-home vault && mkdir /data && chown vault:vault /data
COPY --chown=vault:vault promptvault ./promptvault
COPY --chown=vault:vault tests ./tests
USER vault
EXPOSE 8782
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8782/health', timeout=2)"
CMD ["python", "-m", "promptvault", "--host", "0.0.0.0", "--port", "8782", "--db", "/data/promptvault.db"]
