FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system app && adduser --system --group app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

USER app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
