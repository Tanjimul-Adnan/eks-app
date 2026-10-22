FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SERVICE_NAME=cart
WORKDIR /app
COPY services/api_service.py /app/api_service.py
EXPOSE 8000
USER 10001
CMD ["python","/app/api_service.py"]
