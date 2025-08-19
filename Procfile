release: python3 manage.py makemigrations && python3 manage.py migrate && python3 manage.py collectstatic --noinput
web: gunicorn quote_backend.wsgi --log-file - --timeout 120
