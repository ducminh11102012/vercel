# Dùng Python base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements & install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code
COPY . .

# Expose port cho cloud
EXPOSE 5000

# Set biến môi trường để app.py detect port
ENV PORT=5000

# Chạy app bằng python (bình thường)
CMD ["python", "app.py"]
