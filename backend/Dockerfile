FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system app && adduser --system --group app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app entrypoint.sh .
RUN chmod +x entrypoint.sh

COPY --chown=app:app app/ app/

EXPOSE 8000

USER app
CMD ["bash", "./entrypoint.sh"]
