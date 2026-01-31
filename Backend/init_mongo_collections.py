"""
Script pour créer les collections et index MongoDB optimisés
"""
from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime
import os

def init_mongo_collections():
    """Initialiser les collections MongoDB avec les index optimisés"""
    
        # Connexion MongoDB
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://aichasaaydi_db_user:W4hass6DEv1AfHe9@cluster0.vifo278.mongodb.net/movie_recommender?retryWrites=true&w=majority&appName=Cluster0')
    client = MongoClient(MONGO_URI) 
    db = client.movie_recommender
        
    print("🔧 Initialisation des collections MongoDB...")
    
    # 1. Collection cluster_popular_movies (NOUVELLE collection optimisée)
    print("📊 Création de la collection cluster_popular_movies...")
    
    # Créer la collection si elle n'existe pas
    if 'cluster_popular_movies' not in db.list_collection_names():
        db.create_collection('cluster_popular_movies')
    
    # Créer les index pour des requêtes rapides
    db.cluster_popular_movies.create_index([
        ('cluster_id', ASCENDING),
        ('bayesian_score', DESCENDING)
    ], name='cluster_popularity_idx')
    
    db.cluster_popular_movies.create_index([
        ('cluster_id', ASCENDING),
        ('movie_id', ASCENDING)
    ], name='cluster_movie_idx', unique=True)
    
    db.cluster_popular_movies.create_index([
        ('calculated_at', DESCENDING)
    ], name='calculation_time_idx')
    
    print("✅ Collection cluster_popular_movies initialisée")
    
    # 2. Collection system_metadata
    print("📋 Création de la collection system_metadata...")
    
    if 'system_metadata' not in db.list_collection_names():
        db.create_collection('system_metadata')
    
    # Index pour les métadonnées
    db.system_metadata.create_index([
        ('name', ASCENDING)
    ], name='metadata_name_idx', unique=True)
    
    # Insérer les métadonnées initiales
    db.system_metadata.update_one(
        {'name': 'clustering_status'},
        {'$set': {
            'last_clustering_update': None,
            'last_popularity_calculation': None,
            'n_users_clustered': 0,
            'n_clusters': 5,
            'needs_popularity_recalculation': True,
            'created_at': datetime.now()
        }},
        upsert=True
    )
    
    print("✅ Collection system_metadata initialisée")
    
    # 3. Index pour les autres collections existantes
    print("🔍 Création des index pour les collections existantes...")
    
    # Collection users
    db.users.create_index([('cluster_id', ASCENDING)], name='user_cluster_idx')
    db.users.create_index([('user_id', ASCENDING)], name='user_id_idx', unique=True)
    
    # Collection movies
    db.movies.create_index([('movie_id', ASCENDING)], name='movie_id_idx', unique=True)
    db.movies.create_index([('bayesian_rating', DESCENDING)], name='movie_popularity_idx')
    db.movies.create_index([('genres', ASCENDING)], name='movie_genres_idx')
    
    # Collection ratings
    db.ratings.create_index([
        ('user_id', ASCENDING),
        ('movie_id', ASCENDING)
    ], name='user_movie_rating_idx', unique=True)
    
    db.ratings.create_index([('user_id', ASCENDING)], name='rating_user_idx')
    db.ratings.create_index([('movie_id', ASCENDING)], name='rating_movie_idx')
    
    print("🎉 Toutes les collections et index ont été initialisés avec succès!")
    
    # Afficher les statistiques
    print("\n📈 Statistiques des collections:")
    collections = ['users', 'movies', 'ratings', 'cluster_popular_movies', 'system_metadata']
    
    for collection_name in collections:
        if collection_name in db.list_collection_names():
            count = db[collection_name].count_documents({})
            print(f"   {collection_name}: {count} documents")
    
    client.close()

if __name__ == '__main__':
    init_mongo_collections()