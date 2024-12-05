#!/bin/sh
# entrypoint.sh
python3 manage.py collectstatic --noinput
gunicorn projet.wsgi:application --bind 0.0.0.0:8000