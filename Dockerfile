FROM python:3.13.1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gnupg \
    curl \
    apt-transport-https \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive ACCEPT_EULA=Y apt-get install -y unixodbc unixodbc-dev msodbcsql17 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["waitress-serve", "--host=0.0.0.0", "--port=8000", "DjangoBackend.wsgi:application"]