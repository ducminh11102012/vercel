# Dùng Python base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Cài tzdata để set timezone
RUN apt-get update && apt-get install -y tzdata \
    && ln -fs /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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
