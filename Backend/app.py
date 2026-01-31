# backend/app.py
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import bcrypt
import os
from dotenv import load_dotenv
from offline.recommender import HybridRecommender
import traceback

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'votre-cle-secrete-tres-longue')

#Flask stocke cette clé dans sa config interne
#Flask-JWT-Extended va automatiquement la lire

app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
jwt = JWTManager(app)

# Connexion MongoDB
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/movie_recommender')
client = MongoClient(MONGO_URI)
db = client.movie_recommender

# Initialiser le recommandeur
recommender = HybridRecommender(db)

def get_user_from_token():
    """Récupérer l'utilisateur à partir du token JWT"""
    try:
        current_user_id = get_jwt_identity()
        if not current_user_id:
            return None
        
        # Convertir en ObjectId
        return db.users.find_one({'_id': ObjectId(current_user_id)})
    except Exception as e:
        print(f"Erreur lors de la récupération de l'utilisateur: {e}")
        return None

def generate_user_id():
    """Générer un nouvel ID utilisateur numérique"""
    last_user = db.users.find_one(sort=[('user_id', -1)])
    if last_user and 'user_id' in last_user:
        return last_user['user_id'] + 1
    return 1

# Routes d'authentification
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        # Vérifier si l'utilisateur existe
        existing_user = db.users.find_one({'email': data.get('email')})
        if existing_user:
            return jsonify({'message': 'Email déjà utilisé'}), 400
        
        # Hasher le mot de passe
        hashed_password = bcrypt.hashpw(
            data['password'].encode('utf-8'), 
            bcrypt.gensalt()
        )
        
        # Générer un nouvel user_id
        user_id = generate_user_id()
        
        # Créer un nouvel utilisateur
        new_user = {
            'user_id': user_id,
            'email': data['email'],
            'password': hashed_password.decode('utf-8'),
            'name': data.get('name', ''),
            'age': int(data.get('age', 25)),
            'gender': data.get('gender', 'M'),
            'occupation': data.get('occupation', 'other'),
            'created_at': datetime.now(),
            'preferences': {
                'genre_weights': {},
                'average_rating': 0,
                'rated_movies': []
            },
            'cluster_id': None
        }
        
        # Insérer dans la base de données
        result = db.users.insert_one(new_user)
        
        # Assigner un cluster
        try:
            recommender.assign_user_cluster(result.inserted_id)
        except Exception as e:
            print(f"Warning: Erreur lors de l'assignation du cluster: {e}")
        
        return jsonify({
            'message': 'Utilisateur créé avec succès',
            'user_id': user_id
        }), 201
    
    except Exception as e:
        print(f"Erreur d'inscription: {e}")
        traceback.print_exc()
        return jsonify({'message': f'Erreur serveur: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        # Trouver l'utilisateur
        user = db.users.find_one({'email': data['email']})
        if not user:
            return jsonify({'message': 'Email ou mot de passe incorrect'}), 401
        
        # Vérifier le mot de passe
        if not bcrypt.checkpw(data['password'].encode('utf-8'), user['password'].encode('utf-8')):
            return jsonify({'message': 'Email ou mot de passe incorrect'}), 401
        
        # Créer le token JWT
        access_token = create_access_token(identity=str(user['_id']))
        
        return jsonify({
            'access_token': access_token,
            'user': {
                'id': str(user['_id']),
                'user_id': user.get('user_id'),
                'email': user['email'],
                'name': user.get('name', ''),
                'age': user.get('age', 25),
                'gender': user.get('gender', 'M'),
                'occupation': user.get('occupation', 'other'),
                'cluster_id': user.get('cluster_id')
            }
        }), 200
    
    except Exception as e:
        print(f"Erreur de connexion: {e}")
        return jsonify({'message': str(e)}), 500

# Routes publiques (pas besoin d'authentification)
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200

@app.route('/api/movies/popular', methods=['GET'])
def get_popular_movies():
    """Films populaires pour la première connexion (sans authentification)"""
    try:
        movies = list(db.movies.find(
            {},
            {'_id': 0, 'movie_id': 1, 'title': 1, 'genres': 1, 'year': 1, 'bayesian_rating': 1}
        ).sort('bayesian_rating', -1)#decroissant 
        .limit(40))
        
        return jsonify(movies), 200
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'message': str(e)}), 500

# Routes protégées
@app.route('/api/movies', methods=['GET'])
@jwt_required()
def get_movies():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        movies = list(db.movies.find(
            {},
            {'_id': 0, 'movie_id': 1, 'title': 1, 'genres': 1, 'year': 1, 'bayesian_rating': 1}
        ).skip(skip).limit(limit))
        
        return jsonify(movies), 200
    
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'message': str(e)}), 500

@app.route('/api/movies/search', methods=['GET'])
@jwt_required()
def search_movies():
    try:
        query = request.args.get('q', '')
        
        movies = list(db.movies.find(
            {'title': {'$regex': query, '$options': 'i'}},
            {'_id': 0, 'movie_id': 1, 'title': 1, 'genres': 1, 'year': 1}
        ).limit(20))
        
        return jsonify(movies), 200
    
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'message': str(e)}), 500

# Routes de recommandation
@app.route('/api/recommendations/first-time', methods=['GET'])
@jwt_required()
def get_first_time_recommendations():
    """Recommandations pour la première connexion"""
    try:
        user = get_user_from_token()
        if not user:
            return jsonify({'message': 'Utilisateur non trouvé'}), 404
        
        print(f"Génération de recommandations pour utilisateur: {user.get('user_id')}")
        
        # Vérifier si l'utilisateur a des évaluations
        user_ratings = list(db.ratings.find({'user_id': user.get('user_id')}))
        
        if not user_ratings:
            # Nouvel utilisateur - utiliser la méthode new-user
            recommendations = recommender.recommend_for_new_user(user['_id'], top_n=30)
        else:
            # Utilisateur existant - utiliser la méthode personnalisée
            recommendations = recommender.recommend_for_existing_user(user['_id'], top_n=30)
        
        print(f"Nombre de recommandations générées: {len(recommendations)}")
        
        return jsonify({
            'recommendations': recommendations,
            'user_type': 'new' if not user_ratings else 'existing',
            'ratings_count': len(user_ratings)
        }), 200
    
    except Exception as e:
        print(f"Erreur lors de la génération des recommandations: {e}")
        traceback.print_exc()
        
        # Fallback: retourner des films populaires
        movies = list(db.movies.find(
            {},
            {'_id': 0, 'movie_id': 1, 'title': 1, 'genres': 1, 'year': 1, 'bayesian_rating': 1}
        ).sort('bayesian_rating', -1).limit(20))
        
        return jsonify({
            'recommendations': [{
                'movie_id': m['movie_id'],
                'title': m['title'],
                'genres': m.get('genres', []),
                'year': m.get('year'),
                'score': m.get('bayesian_rating', 3.0),
                'explanation': 'Film populaire (fallback)'
            } for m in movies],
            'user_type': 'fallback',
            'ratings_count': 0
        }), 200

@app.route('/api/recommendations/personalized', methods=['GET'])
@jwt_required()
def get_personalized_recommendations():
    try:
        user = get_user_from_token()
        if not user:
            return jsonify({'message': 'Utilisateur non trouvé'}), 404
        
        # Obtenir les recommandations personnalisées
        recommendations = recommender.recommend_for_existing_user(user['_id'], top_n=20)
        
        return jsonify({
            'recommendations': recommendations,
            'user_id': user.get('user_id')
        }), 200
    
    except Exception as e:
        print(f"Erreur: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

@app.route('/api/rate', methods=['POST'])
@jwt_required()
def rate_movie():
    try:
        user = get_user_from_token()
        if not user:
            return jsonify({'message': 'Utilisateur non trouvé'}), 404
        
        data = request.get_json()
        movie_id = int(data['movie_id'])
        rating = float(data['rating'])
        
        # Vérifier la validité de la note
        if rating < 1 or rating > 5:
            return jsonify({'message': 'La note doit être entre 1 et 5'}), 400
        
        # Créer ou mettre à jour l'évaluation
        rating_record = {
            'user_id': user['user_id'],
            'movie_id': movie_id,
            'rating': rating,
            'timestamp': datetime.now()
        }
        
        # Utiliser upsert pour éviter les doublons
        db.ratings.update_one(
            {'user_id': user['user_id'], 'movie_id': movie_id},
            {'$set': rating_record},
            upsert=True
        )
        
        # Mettre à jour les statistiques du film
        movie_ratings = list(db.ratings.find({'movie_id': movie_id}))
        if movie_ratings:
            avg_rating = sum(r['rating'] for r in movie_ratings) / len(movie_ratings)
            db.movies.update_one(
                {'movie_id': movie_id},
                {
                    '$set': {
                        'average_rating': avg_rating,
                        'ratings_count': len(movie_ratings),
                        'bayesian_rating': (len(movie_ratings) * avg_rating + 10 * 3.0) / (len(movie_ratings) + 10)
                    }
                }
            )
        
        # Mettre à jour les préférences de l'utilisateur
        try:
            recommender.update_user_preferences(user['_id'])
        except Exception as e:
            print(f"Warning: Erreur lors de la mise à jour des préférences: {e}")
        
        return jsonify({
            'message': 'Évaluation enregistrée',
            'movie_id': movie_id,
            'rating': rating
        }), 200
    
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'message': str(e)}), 500

@app.route('/api/user/stats', methods=['GET'])
@jwt_required()
def get_user_stats():
    try:
        user = get_user_from_token()
        if not user:
            return jsonify({'message': 'Utilisateur non trouvé'}), 404
        
        # Récupérer les statistiques de l'utilisateur
        ratings_count = db.ratings.count_documents({'user_id': user['user_id']})
        
        return jsonify({
            'user_id': user['user_id'],
            'name': user.get('name', ''),
            'email': user['email'],
            'cluster_id': user.get('cluster_id'),
            'ratings_count': ratings_count,
            'preferences': user.get('preferences', {})
        }), 200
    
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'message': str(e)}), 500

# Routes d'administration
@app.route('/admin/run-offline', methods=['POST'])
def run_offline_calculations():
    """Exécuter les calculs offline (pour les tests)"""
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'message': 'Token manquant'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Vérifier un token admin simple (pour les tests)
        if token != os.getenv('ADMIN_TOKEN', 'admin-secret-token'):
            return jsonify({'message': 'Accès non autorisé'}), 403
        
        # Exécuter tous les calculs offline
        recommender.run_offline_computations()
        
        return jsonify({'message': 'Calculs offline terminés'}), 200
    
    except Exception as e:
        print(f"Erreur: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

@app.route('/admin/init-db', methods=['POST'])
def init_database():
    """Initialiser la base de données avec des données de test"""
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'message': 'Token manquant'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Vérifier un token admin simple
        if token != os.getenv('ADMIN_TOKEN', 'admin-secret-token'):
            return jsonify({'message': 'Accès non autorisé'}), 403
        
        # Créer quelques films de test
        test_movies = [
            {
                'movie_id': 1,
                'title': 'The Shawshank Redemption',
                'year': 1994,
                'genres': ['Drama'],
                'bayesian_rating': 4.8,
                'ratings_count': 1000
            },
            {
                'movie_id': 2,
                'title': 'The Godfather',
                'year': 1972,
                'genres': ['Crime', 'Drama'],
                'bayesian_rating': 4.7,
                'ratings_count': 900
            },
            {
                'movie_id': 3,
                'title': 'The Dark Knight',
                'year': 2008,
                'genres': ['Action', 'Crime', 'Drama'],
                'bayesian_rating': 4.6,
                'ratings_count': 950
            },
            {
                'movie_id': 4,
                'title': 'Pulp Fiction',
                'year': 1994,
                'genres': ['Crime', 'Drama'],
                'bayesian_rating': 4.5,
                'ratings_count': 850
            },
            {
                'movie_id': 5,
                'title': 'Forrest Gump',
                'year': 1994,
                'genres': ['Drama', 'Romance'],
                'bayesian_rating': 4.4,
                'ratings_count': 800
            }
        ]
        
        # Insérer les films
        for movie in test_movies:
            db.movies.update_one(
                {'movie_id': movie['movie_id']},
                {'$set': movie},
                upsert=True
            )
        
        return jsonify({
            'message': 'Base de données initialisée avec des données de test',
            'movies_count': len(test_movies)
        }), 200
    
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')