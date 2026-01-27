# backend/run.py
from app import app
from config import get_config
import os

if __name__ == '__main__':
    # Charger la configuration
    config = get_config()
    app.config.from_object(config)
    
    # Démarrer l'application
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '127.0.0.1')
    
    print(f"🚀 Démarrage de l'application sur {host}:{port}")
    print(f"📊 Environnement: {os.getenv('FLASK_ENV', 'development')}")
    print(f"🔗 MongoDB URI: {config.MONGO_URI[:30]}...")
    
    app.run(host=host, port=port, debug=config.DEBUG)