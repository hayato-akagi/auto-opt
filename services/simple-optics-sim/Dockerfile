FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://localhost:8000/health || exit 1

# Set environment variables (defaults, can be overridden)
ENV CAMERA_WIDTH_PX=640
ENV CAMERA_HEIGHT_PX=480
ENV CAMERA_FOV_WIDTH_MM=1.0
ENV CAMERA_FOV_HEIGHT_MM=1.0
ENV MAGNIFICATION=50.0
ENV DEFOCUS_COEFFICIENT=10.0
ENV TILT_SENSITIVITY_X=0.1
ENV TILT_SENSITIVITY_Y=0.1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
