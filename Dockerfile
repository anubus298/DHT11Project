
FROM --platform=$BUILDPLATFORM python:3.10 AS builder
WORKDIR /app 
COPY requirements.txt /app
RUN apt-get update && apt-get install -y libpq-dev
RUN pip3 install -r requirements.txt --no-cache-dir
COPY . /app 
EXPOSE 80
ENTRYPOINT ["sh", "entrypoint.sh"]


