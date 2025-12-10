FROM python:3.11

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ARG PIP_NO_CACHE_DIR=1

# Chrome/Chromium environment variables for Docker
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_PATH=/usr/bin/chromium
ENV DISPLAY=:99
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Install Chromium (works natively on ARM64 and AMD64)
RUN apt-get -y update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/chromium /usr/bin/google-chrome || true \
    && ln -s /usr/bin/chromedriver /usr/local/bin/chromedriver || true

# Upgrade pip
RUN pip install --upgrade pip

WORKDIR /usr/src/app

# Copy and install dependencies from requirements.txt
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy all other files, including source files
COPY . .

# Run flathunt.py with automatic restart on crash
CMD ["sh", "-c", "while true; do python flathunt.py; echo 'Process crashed, restarting in 5 seconds...'; sleep 5; done"]
