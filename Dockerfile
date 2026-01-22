FROM python:3.10-slim

# ---- System setup ----
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ---- Install dependencies ----
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- Copy bot code ----
COPY app.py .

# ---- Expose port for Koyeb ----
EXPOSE 8000

# ---- Start bot ----
CMD ["python", "app.py"]
