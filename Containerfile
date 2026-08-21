FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -f /etc/ImageMagick-6/policy.xml ]; then \
        sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml && \
        sed -i 's/none/read,write/g' /etc/ImageMagick-6/policy.xml; \
    elif [ -f /etc/ImageMagick-7/policy.xml ]; then \
        sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-7/policy.xml && \
        sed -i 's/none/read,write/g' /etc/ImageMagick-7/policy.xml; \
    fi

RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="/usr/local/bin" sh

WORKDIR /app
COPY . .

RUN uv pip install --system librosa moviepy pillow numpy jsonschema

ENTRYPOINT ["python", "main.py"]
CMD ["--project", "projects/testudo-launch"]
