# Pulled from AWS's mirror of the official images rather than Docker Hub.
# Railway's builders share an egress address, so anonymous Docker Hub pulls
# get throttled and the build dies on a TLS handshake timeout before it has
# read a line of this project. Same image, same tag, a registry that does not
# rate-limit anonymous pulls.
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

EXPOSE 8000

CMD ["python", "backend/main.py"]
