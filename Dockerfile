FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_COMPILE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем минимальные системные зависимости для headless matplotlib/Pillow
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    fontconfig \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements-docker.txt requirements-torch-cpu.txt ./

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --no-compile -r requirements-docker.txt
RUN pip install --no-cache-dir --no-compile -r requirements-torch-cpu.txt

# Копируем весь проект
COPY . .

