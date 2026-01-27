# backend/wsgi.py
from app import app
from config import get_config

# Charger la configuration pour la production
config = get_config('production')
app.config.from_object(config)

if __name__ == "__main__":
    app.run()