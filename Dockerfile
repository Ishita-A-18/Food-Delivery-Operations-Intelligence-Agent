FROM node:20-slim AS frontend
WORKDIR /ui
COPY dashboard/package*.json ./
RUN npm install
COPY dashboard/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend /ui/dist ./static
ENV PORT=8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
