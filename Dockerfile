##Produccion

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN adduser --disabled-password --no-create-home --gecos "" appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "vuzco.asgi:application"]

#Desarrollo

#FROM python:3.10
#ENV PYTHONUNBUFFERED 1
#WORKDIR /app
#COPY requirements.txt /app/requirements.txt
#RUN pip install -r requirements.txt
#COPY . /app/
#
#CMD daphne -b 0.0.0.0 -p 8000 vuzco.asgi:application