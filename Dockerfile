# StoryForge — small image for Hugging Face Spaces / any container host.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=7860
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY storyforge ./storyforge
COPY web ./web
COPY examples ./examples
EXPOSE 7860
CMD ["sh", "-c", "uvicorn storyforge.api:app --host 0.0.0.0 --port ${PORT}"]
