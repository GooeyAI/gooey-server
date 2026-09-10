FROM python:3.12-slim

WORKDIR /srv/comfy

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8501

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8501"]
