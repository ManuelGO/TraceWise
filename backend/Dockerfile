FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 && rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --group app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app entrypoint.sh .
RUN chmod +x entrypoint.sh

COPY --chown=app:app app/ app/

EXPOSE 8000

USER app
CMD ["bash", "./entrypoint.sh"]
