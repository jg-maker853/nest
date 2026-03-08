FROM python:3.11-slim
WORKDIR /app
COPY server.py .
COPY zillow-dashboard.html .
CMD ["python3", "server.py"]
