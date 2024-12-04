echo "installing libpq-dev"
apt-get install libpq-dev
echo "installing packages..."
python3 -m  pip install -r requirements.txt
echo "Collectiong static files..."
python3 manage.py collectstatic --noinput