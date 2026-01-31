# backend/offline/recommender.py (optimisé)
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime
from bson import ObjectId
import traceback

class HybridRecommender:
    def __init__(self, db, n_clusters=5):
        self.db = db
        self.n_clusters = n_clusters
        self.user_cluster_model = None
        self.item_similarity_matrix = None
        self.user_similarity_matrix = None
        
    def run_offline_computations(self):
        """Exécuter tous les calculs offline"""
        print("🚀 Début des calculs offline...")
        
        try:
            # 1. Clustering des utilisateurs
            print("📊 Étape 1/4: Clustering des utilisateurs...")
            self.cluster_users()
            
            # 2. Calcul de la popularité bayésienne par cluster (OPTIMISÉ)
            print("🏆 Étape 2/4: Calcul de la popularité bayésienne (offline)...")
            self.calculate_cluster_popularity_offline()
            
            # 3. Calcul des similarités item-item
            print("🔗 Étape 3/4: Calcul des similarités item-item...")
            self.calculate_item_similarities()
            
            # 4. Calcul des similarités user-user
            print("👥 Étape 4/4: Calcul des similarités user-user...")
            self.calculate_user_similarities()
            
            print("✅ Calculs offline terminés avec succès!")
            
        except Exception as e:
            print(f"❌ Erreur lors des calculs offline: {e}")
            traceback.print_exc()
            raise
    
    def cluster_users(self):
        """Clustering K-Means des utilisateurs"""
        # Récupérer les données utilisateurs
        users = list(self.db.users.find({}, {
            '_id': 1, 'user_id': 1, 'age': 1, 'gender': 1, 'occupation': 1
        }))
        
        if not users or len(users) < self.n_clusters:
            print("⚠️ Pas assez d'utilisateurs pour le clustering")
            return
        
        print(f"📊 Clustering de {len(users)} utilisateurs...")
        
        # Préparer les données pour le clustering
        user_data = []
        user_ids = []
        
        for user in users:
            try:
                # Valeurs par défaut
                age = user.get('age', 25)
                gender = user.get('gender', 'M')
                occupation = user.get('occupation', 'other')
                
                # Normaliser l'âge
                age_norm = age / 100.0
                
                # Encoder le genre
                gender_enc = 1 if gender == 'M' else 0
                
                # Encoder l'occupation (liste simplifiée)
                occupations_list = [
                    'administrator', 'artist', 'doctor', 'educator', 'engineer',
                    'entertainment', 'executive', 'healthcare', 'homemaker', 'lawyer',
                    'librarian', 'marketing', 'none', 'other', 'programmer',
                    'retired', 'salesman', 'scientist', 'student', 'technician', 'writer'
                ]
                
                occupation_enc = [0] * len(occupations_list)
                if occupation in occupations_list:
                    occupation_enc[occupations_list.index(occupation)] = 1
                else:
                    # Si l'occupation n'est pas dans la liste, utiliser 'other'
                    occupation_enc[occupations_list.index('other')] = 1
                
                # Combiner les features
                features = [age_norm, gender_enc] + occupation_enc
                user_data.append(features)
                user_ids.append(str(user['_id']))
                
            except Exception as e:
                print(f"⚠️ Erreur avec l'utilisateur {user.get('user_id')}: {e}")
                continue
        
        if not user_data:
            print("❌ Aucune donnée valide pour le clustering")
            return
        
        # Appliquer K-Means
        try:
            user_data_array = np.array(user_data)
            print(f"📐 Taille des données: {user_data_array.shape}")
            
            kmeans = KMeans(
                n_clusters=self.n_clusters, 
                random_state=42, 
                n_init=10,
                max_iter=300
            )
            clusters = kmeans.fit_predict(user_data_array)
            
            # Sauvegarder le modèle
            self.user_cluster_model = kmeans
            
            # Mettre à jour les clusters dans la base de données
            updated_count = 0
            for user_objid_str, cluster_id in zip(user_ids, clusters):
                try:
                    result = self.db.users.update_one(
                        {'_id': ObjectId(user_objid_str)},
                        {'$set': {'cluster_id': int(cluster_id)}}
                    )
                    if result.modified_count > 0:
                        updated_count += 1
                except Exception as e:
                    print(f"⚠️ Erreur mise à jour cluster pour {user_objid_str}: {e}")
            
            print(f"✅ {updated_count} utilisateurs clusterisés dans {self.n_clusters} groupes")
            
            # Marquer que le clustering a été mis à jour
            self.db.system_metadata.update_one(
                {'name': 'clustering_status'},
                {'$set': {
                    'last_clustering_update': datetime.now(),
                    'n_users_clustered': updated_count,
                    'n_clusters': self.n_clusters,
                    'needs_popularity_recalculation': True
                }},
                upsert=True
            )
            
        except Exception as e:
            print(f"❌ Erreur K-Means: {e}")
            traceback.print_exc()
    
    def calculate_cluster_popularity_offline(self):
        """Calculer EN OFFLINE la popularité bayésienne par cluster et stocker dans collection dédiée"""
        print(f"📈 Calcul OFFLINE de la popularité pour {self.n_clusters} clusters...")
        
        # Vérifier si le recalcul est nécessaire
        metadata = self.db.system_metadata.find_one({'name': 'clustering_status'})
        if metadata and not metadata.get('needs_popularity_recalculation', True):
            print("⚠️ Popularité déjà calculée, saut de cette étape")
            return
        
        # Nettoyer l'ancienne collection
        self.db.cluster_popular_movies.delete_many({})
        print("🧹 Anciennes données de popularité nettoyées")
        
        # Pour chaque cluster, calculer les films populaires
        for cluster_id in range(self.n_clusters):
            try:
                print(f"\n📊 Traitement du cluster {cluster_id}...")
                
                # Récupérer les utilisateurs du cluster
                users_in_cluster = list(self.db.users.find(
                    {'cluster_id': cluster_id},
                    {'user_id': 1}
                ))
                
                if not users_in_cluster:
                    print(f"   Cluster {cluster_id}: Aucun utilisateur, passage au suivant")
                    continue
                
                user_ids = [u['user_id'] for u in users_in_cluster]
                print(f"   Cluster {cluster_id}: {len(user_ids)} utilisateurs")
                
                # Récupérer TOUTES les évaluations de ces utilisateurs
                ratings = list(self.db.ratings.find({
                    'user_id': {'$in': user_ids}
                }))
                
                if not ratings:
                    print(f"   Cluster {cluster_id}: Aucune évaluation")
                    continue
                
                print(f"   Cluster {cluster_id}: {len(ratings)} évaluations à analyser")
                
                # Calculer la popularité bayésienne pour chaque film
                df_ratings = pd.DataFrame(ratings)
                
                # Agrégation par film
                movie_stats = df_ratings.groupby('movie_id').agg({
                    'rating': ['mean', 'count']
                }).reset_index()
                
                movie_stats.columns = ['movie_id', 'avg_rating', 'rating_count']
                
                # Paramètres bayésiens
                C = 3.0  # Note moyenne attendue
                m = 10   # Nombre minimum de votes (plus élevé pour plus de stabilité)
                
                # Calculer le score bayésien pour chaque film
                cluster_popular_movies = []
                
                for _, row in movie_stats.iterrows():
                    try:
                        movie_id = int(row['movie_id'])
                        avg_rating = float(row['avg_rating'])
                        rating_count = int(row['rating_count'])
                        
                        # Calcul du score bayésien
                        bayesian_score = (rating_count * avg_rating + m * C) / (rating_count + m)
                        
                        # Récupérer les infos du film
                        movie = self.db.movies.find_one(
                            {'movie_id': movie_id},
                            {'title': 1, 'genres': 1, 'year': 1}
                        )
                        
                        if movie:
                            cluster_popular_movies.append({
                                'movie_id': movie_id,
                                'title': movie.get('title', ''),
                                'genres': movie.get('genres', []),
                                'year': movie.get('year'),
                                'bayesian_score': float(bayesian_score),
                                'avg_rating': avg_rating,
                                'rating_count': rating_count,
                                'cluster_id': cluster_id,
                                'calculated_at': datetime.now()
                            })
                            
                    except Exception as e:
                        print(f"⚠️ Erreur traitement film {row.get('movie_id')}: {e}")
                        continue
                
                # Trier par score bayésien (du plus élevé au plus bas)
                cluster_popular_movies.sort(key=lambda x: x['bayesian_score'], reverse=True)
                
                # Garder les TOP 100 films par cluster
                top_movies = cluster_popular_movies[:100]
                
                if top_movies:
                    # Insérer dans la collection dédiée
                    self.db.cluster_popular_movies.insert_many(top_movies)
                    print(f"   Cluster {cluster_id}: {len(top_movies)} films populaires sauvegardés")
                    
                    # Mettre à jour également dans la collection movies pour compatibilité
                    for movie_data in top_movies[:20]:  # Garder les 20 meilleurs dans movies
                        self.db.movies.update_one(
                            {'movie_id': movie_data['movie_id']},
                            {
                                '$set': {
                                    f'cluster_popularity.{cluster_id}': {
                                        'score': movie_data['bayesian_score'],
                                        'count': movie_data['rating_count'],
                                        'rank': cluster_popular_movies.index(movie_data) + 1
                                    }
                                }
                            }
                        )
                
                print(f"✅ Cluster {cluster_id}: Popularité calculée et sauvegardée")
                
            except Exception as e:
                print(f"❌ Erreur cluster {cluster_id}: {e}")
                traceback.print_exc()
                continue
        
        # Marquer que la popularité a été calculée
        self.db.system_metadata.update_one(
            {'name': 'clustering_status'},
            {'$set': {
                'last_popularity_calculation': datetime.now(),
                'needs_popularity_recalculation': False,
                'n_clusters_processed': self.n_clusters
            }}
        )
        
        print("🎉 Popularité bayésienne OFFLINE calculée pour tous les clusters!")
    
    def get_popular_movies_for_cluster(self, cluster_id, top_n=30):
        """
        Récupérer les films populaires pour un cluster (TRÈS RAPIDE - pré-calculé)
        
        Args:
            cluster_id: ID du cluster
            top_n: Nombre de films à retourner
        
        Returns:
            list: Liste des films populaires pour ce cluster
        """
        try:
            # Récupérer depuis la collection pré-calculée (TRÈS RAPIDE)
            popular_movies = list(self.db.cluster_popular_movies.find(
                {'cluster_id': cluster_id},
                {'_id': 0, 'movie_id': 1, 'title': 1, 'genres': 1, 'year': 1, 'bayesian_score': 1}
            ).sort('bayesian_score', -1).limit(top_n))
            
            if popular_movies:
                # Format de retour standardisé
                return [{
                    'movie_id': movie['movie_id'],
                    'title': movie['title'],
                    'genres': movie.get('genres', []),
                    'year': movie.get('year'),
                    'score': movie.get('bayesian_score', 3.0),
                    'explanation': f'Populaire dans votre groupe démographique (score: {movie.get("bayesian_score", 3.0):.2f})'
                } for movie in popular_movies]
            
            # Fallback: vérifier si on a des données dans la collection movies
            fallback_movies = list(self.db.movies.find({
                f'cluster_popularity.{cluster_id}': {'$exists': True}
            }, {
                '_id': 0, 'movie_id': 1, 'title': 1, 'genres': 1, 'year': 1,
                f'cluster_popularity.{cluster_id}.score': 1
            }).sort(f'cluster_popularity.{cluster_id}.score', -1).limit(top_n))
            
            if fallback_movies:
                return [{
                    'movie_id': movie['movie_id'],
                    'title': movie['title'],
                    'genres': movie.get('genres', []),
                    'year': movie.get('year'),
                    'score': movie.get('cluster_popularity', {}).get(str(cluster_id), {}).get('score', 3.0),
                    'explanation': f'Populaire dans votre groupe (score: {movie.get("cluster_popularity", {}).get(str(cluster_id), {}).get("score", 3.0):.2f})'
                } for movie in fallback_movies]
            
            # Dernier recours: films populaires globaux
            return self._get_global_popular_movies(top_n)
            
        except Exception as e:
            print(f"⚠️ Erreur récupération films populaires cluster {cluster_id}: {e}")
            return self._get_global_popular_movies(top_n)
    
    def _get_global_popular_movies(self, top_n):
        """Obtenir les films populaires globaux (fallback)"""
        movies = list(self.db.movies.find(
            {},
            {'_id': 0, 'movie_id': 1, 'title': 1, 'genres': 1, 'year': 1, 'bayesian_rating': 1}
        ).sort('bayesian_rating', -1).limit(top_n))
        
        return [{
            'movie_id': m['movie_id'],
            'title': m['title'],
            'genres': m.get('genres', []),
            'year': m.get('year'),
            'score': m.get('bayesian_rating', 3.0),
            'explanation': 'Film populaire (recommandation générale)'
        } for m in movies]
    
    def calculate_item_similarities(self):
        """Calculer les similarités item-item"""
        print("🔗 Calcul des similarités item-item...")
        
        # Récupérer tous les films
        movies = list(self.db.movies.find({}, {
            'movie_id': 1, 'genres': 1
        }))
        
        if not movies:
            print("❌ Aucun film trouvé")
            return
        
        print(f"🎬 Traitement de {len(movies)} films...")
        
        # Créer une matrice films x genres
        movie_ids = []
        genre_matrix = []
        
        # Liste complète des genres
        all_genres = [
            'Action', 'Adventure', 'Animation', 'Children', 'Comedy',
            'Crime', 'Documentary', 'Drama', 'Fantasy', 'Film-Noir',
            'Horror', 'Musical', 'Mystery', 'Romance', 'Sci-Fi',
            'Thriller', 'War', 'Western'
        ]
        
        for movie in movies:
            try:
                movie_id = movie['movie_id']
                movie_ids.append(movie_id)
                
                genres = movie.get('genres', [])
                # Créer un vecteur one-hot pour les genres
                genre_vector = [1 if genre in genres else 0 for genre in all_genres]
                genre_matrix.append(genre_vector)
                
            except Exception as e:
                print(f"⚠️ Erreur film {movie.get('movie_id')}: {e}")
                continue
        
        if not genre_matrix:
            print("❌ Aucune donnée de genre")
            return
        
        # Calculer la similarité cosinus
        try:
            genre_matrix_array = np.array(genre_matrix)
            print(f"📐 Matrice: {genre_matrix_array.shape}")
            
            similarities = cosine_similarity(genre_matrix_array)
            
            # Sauvegarder les similarités
            updated_count = 0
            for i, movie_id in enumerate(movie_ids):
                try:
                    similar_items = {}
                    for j, other_id in enumerate(movie_ids):
                        if i != j and similarities[i, j] > 0.3:  # Seuil
                            similar_items[str(other_id)] = float(similarities[i, j])
                    
                    # Garder les 20 plus similaires
                    top_similar = dict(sorted(similar_items.items(), 
                                             key=lambda x: x[1], 
                                             reverse=True)[:20])
                    
                    # Mettre à jour dans MongoDB
                    result = self.db.movies.update_one(
                        {'movie_id': movie_id},
                        {
                            '$set': {
                                'item_similarities': top_similar,
                                'similarity_updated_at': datetime.now()
                            }
                        }
                    )
                    
                    if result.modified_count > 0:
                        updated_count += 1
                        
                except Exception as e:
                    print(f"⚠️ Erreur sauvegarde film {movie_id}: {e}")
                    continue
            
            print(f"✅ Similarités item-item sauvegardées pour {updated_count} films")
            
        except Exception as e:
            print(f"❌ Erreur calcul similarités: {e}")
            traceback.print_exc()
    
    def calculate_user_similarities(self):
        """Calculer les similarités user-user"""
        print("👥 Calcul des similarités user-user...")
        
        # Récupérer toutes les évaluations
        ratings = list(self.db.ratings.find({}, {
            'user_id': 1, 'movie_id': 1, 'rating': 1
        }))
        
        if not ratings:
            print("❌ Aucune évaluation trouvée")
            return
        
        print(f"⭐ Traitement de {len(ratings)} évaluations...")
        
        try:
            # Créer un DataFrame
            df_ratings = pd.DataFrame(ratings)
            
            # Créer une matrice utilisateur-film
            user_movie_matrix = df_ratings.pivot_table(
                index='user_id', 
                columns='movie_id', 
                values='rating',
                fill_value=0
            )
            
            print(f"📐 Matrice: {user_movie_matrix.shape}")
            
            # Calculer la similarité cosinus
            user_matrix = user_movie_matrix.values
            similarities = cosine_similarity(user_matrix)
            
            # Sauvegarder les similarités
            user_ids = user_movie_matrix.index.tolist()
            updated_count = 0
            
            for i, user_id in enumerate(user_ids):
                try:
                    similar_users = {}
                    for j, other_id in enumerate(user_ids):
                        if i != j and similarities[i, j] > 0.2:  # Seuil
                            similar_users[str(other_id)] = float(similarities[i, j])
                    
                    # Garder les 30 plus similaires
                    top_similar = dict(sorted(similar_users.items(), 
                                             key=lambda x: x[1], 
                                             reverse=True)[:30])
                    
                    # Mettre à jour dans MongoDB
                    result = self.db.users.update_one(
                        {'user_id': user_id},
                        {
                            '$set': {
                                'similar_users': top_similar,
                                'similarity_updated_at': datetime.now()
                            }
                        }
                    )
                    
                    if result.modified_count > 0:
                        updated_count += 1
                        
                except Exception as e:
                    print(f"⚠️ Erreur sauvegarde utilisateur {user_id}: {e}")
                    continue
            
            print(f"✅ Similarités user-user sauvegardées pour {updated_count} utilisateurs")
            
        except Exception as e:
            print(f"❌ Erreur calcul similarités user-user: {e}")
            traceback.print_exc()
    
    def assign_user_cluster(self, user_object_id):
        """Assigner un cluster à un nouvel utilisateur"""
        try:
            user = self.db.users.find_one({'_id': ObjectId(user_object_id)})
            if not user:
                return
            
            # Si pas de modèle de clustering, assigner aléatoirement
            if self.user_cluster_model is None:
                import random
                cluster_id = random.randint(0, self.n_clusters - 1)
                self.db.users.update_one(
                    {'_id': ObjectId(user_object_id)},
                    {'$set': {'cluster_id': cluster_id}}
                )
                return
            
            # Préparer les caractéristiques
            age = user.get('age', 25)
            gender = user.get('gender', 'M')
            occupation = user.get('occupation', 'other')
            
            # Normaliser l'âge
            age_norm = age / 100.0
            
            # Encoder le genre
            gender_enc = 1 if gender == 'M' else 0
            
            # Encoder l'occupation
            occupations_list = [
                'administrator', 'artist', 'doctor', 'educator', 'engineer',
                'entertainment', 'executive', 'healthcare', 'homemaker', 'lawyer',
                'librarian', 'marketing', 'none', 'other', 'programmer',
                'retired', 'salesman', 'scientist', 'student', 'technician', 'writer'
            ]
            
            occupation_enc = [0] * len(occupations_list)
            if occupation in occupations_list:
                occupation_enc[occupations_list.index(occupation)] = 1
            else:
                occupation_enc[occupations_list.index('other')] = 1
            
            features = np.array([[age_norm, gender_enc] + occupation_enc])
            
            # Prédire le cluster
            cluster_id = self.user_cluster_model.predict(features)[0]
            
            # Mettre à jour
            self.db.users.update_one(
                {'_id': ObjectId(user_object_id)},
                {'$set': {'cluster_id': int(cluster_id)}}
            )
            
        except Exception as e:
            print(f"⚠️ Erreur assignation cluster: {e}")
            # Assigner aléatoirement en cas d'erreur
            import random
            cluster_id = random.randint(0, self.n_clusters - 1)
            self.db.users.update_one(
                {'_id': ObjectId(user_object_id)},
                {'$set': {'cluster_id': cluster_id}}
            )
    
    def recommend_for_new_user(self, user_object_id, top_n=30):
        """Recommandations pour nouvel utilisateur - OPTIMISÉ avec données pré-calculées"""
        try:
            user = self.db.users.find_one({'_id': ObjectId(user_object_id)})
            if not user:
                print(f"❌ Utilisateur {user_object_id} non trouvé")
                return self._get_global_popular_movies(top_n)
            
            cluster_id = user.get('cluster_id')
            
            # Si pas de cluster, retourner les films populaires globaux
            if cluster_id is None:
                print(f"⚠️ Utilisateur sans cluster, retour films populaires globaux")
                return self._get_global_popular_movies(top_n)
            
            print(f"🎯 Utilisateur dans le cluster {cluster_id}, récupération films populaires pré-calculés...")
            
            # Récupérer les films populaires PRÉ-CALCULÉS pour ce cluster (TRÈS RAPIDE)
            recommendations = self.get_popular_movies_for_cluster(cluster_id, top_n)
            
            if not recommendations:
                print(f"⚠️ Aucun film populaire trouvé pour le cluster {cluster_id}, fallback global")
                return self._get_global_popular_movies(top_n)
            
            print(f"✅ {len(recommendations)} recommandations récupérées pour cluster {cluster_id}")
            return recommendations
            
        except Exception as e:
            print(f"❌ Erreur recommandations new-user: {e}")
            traceback.print_exc()
            return self._get_global_popular_movies(top_n)
    
    def recommend_for_existing_user(self, user_object_id, top_n=20):
        """Recommandations pour utilisateur existant"""
        try:
            user = self.db.users.find_one({'_id': ObjectId(user_object_id)})
            if not user:
                return []
            
            user_id = user.get('user_id')
            if not user_id:
                return self.recommend_for_new_user(user_object_id, top_n)
            
            # Récupérer les films évalués
            rated_movies = list(self.db.ratings.find(
                {'user_id': user_id},
                {'movie_id': 1}
            ))
            rated_movie_ids = [r['movie_id'] for r in rated_movies]
            
            if not rated_movie_ids:
                return self.recommend_for_new_user(user_object_id, top_n)
            
            # Récupérer les films non évalués
            all_movies = list(self.db.movies.find({
                'movie_id': {'$nin': rated_movie_ids}
            }, {
                '_id': 0, 'movie_id': 1, 'title': 1, 'genres': 1, 'year': 1,
                'bayesian_rating': 1, 'item_similarities': 1, 'cluster_popularity': 1
            }))
            
            recommendations = []
            for movie in all_movies:
                scores = {
                    'item_based': 0,
                    'user_based': 0,
                    'content_based': 0,
                    'cluster': 0
                }
                
                # 1. Score Item-Based
                scores['item_based'] = self._calculate_item_based_score(user_id, movie, rated_movie_ids)
                
                # 2. Score User-Based
                scores['user_based'] = self._calculate_user_based_score(user_id, movie)
                
                # 3. Score Content-Based
                scores['content_based'] = self._calculate_content_similarity(user, movie)
                
                # 4. Score Cluster (utilisation des données pré-calculées si disponible)
                cluster_id = user.get('cluster_id')
                cluster_score = movie.get('bayesian_rating', 3.0)
                
                if cluster_id is not None:
                    # Essayer d'abord avec les données pré-calculées
                    cluster_movie = self.db.cluster_popular_movies.find_one({
                        'cluster_id': cluster_id,
                        'movie_id': movie['movie_id']
                    })
                    
                    if cluster_movie:
                        cluster_score = cluster_movie.get('bayesian_score', cluster_score)
                    else:
                        # Fallback: vérifier dans la collection movies
                        cluster_pop = movie.get('cluster_popularity', {})
                        if isinstance(cluster_pop, dict) and str(cluster_id) in cluster_pop:
                            cluster_data = cluster_pop[str(cluster_id)]
                            if isinstance(cluster_data, dict):
                                cluster_score = cluster_data.get('score', cluster_score)
                
                scores['cluster'] = cluster_score
                
                # Score final pondéré
                final_score = (
                    0.35 * scores['item_based'] +
                    0.25 * scores['user_based'] +
                    0.25 * scores['content_based'] +
                    0.15 * scores['cluster']
                )
                
                if final_score > 2.0:  # Seuil plus bas pour plus de recommandations
                    recommendations.append({
                        'movie_id': movie['movie_id'],
                        'title': movie['title'],
                        'genres': movie.get('genres', []),
                        'year': movie.get('year'),
                        'score': final_score,
                        'score_details': scores,
                        'explanation': self._generate_explanation(scores)
                    })
            
            # Trier et limiter
            recommendations.sort(key=lambda x: x['score'], reverse=True)
            return recommendations[:top_n]
            
        except Exception as e:
            print(f"❌ Erreur recommandations existing-user: {e}")
            traceback.print_exc()
            return self.recommend_for_new_user(user_object_id, top_n)
    
    def _calculate_item_based_score(self, user_id, movie, rated_movie_ids):
        """Calculer le score item-based"""
        item_similarities = movie.get('item_similarities', {})
        
        if not item_similarities or not rated_movie_ids:
            return 3.0  # Retourner une note moyenne
        
        # Récupérer les évaluations de l'utilisateur
        user_ratings = list(self.db.ratings.find({
            'user_id': user_id,
            'movie_id': {'$in': rated_movie_ids}
        }))
        
        if not user_ratings:
            return 3.0
        
        # Créer un dictionnaire film->note
        user_ratings_dict = {str(r['movie_id']): r['rating'] for r in user_ratings}
        
        # Calculer le score prédit
        numerator = 0
        denominator = 0
        
        for similar_movie_str, similarity in item_similarities.items():
            if similar_movie_str in user_ratings_dict:
                rating = user_ratings_dict[similar_movie_str]
                numerator += similarity * rating
                denominator += abs(similarity)
        
        if denominator == 0:
            return 3.0
        
        return numerator / denominator
    
    def _calculate_user_based_score(self, user_id, movie):
        """Calculer le score user-based"""
        # Récupérer les utilisateurs similaires
        user = self.db.users.find_one({'user_id': user_id})
        if not user:
            return 3.0
        
        similar_users = user.get('similar_users', {})
        
        if not similar_users:
            return 3.0
        
        # Récupérer les évaluations pour ce film
        similar_user_ids = [int(uid) for uid in similar_users.keys()]
        
        ratings = list(self.db.ratings.find({
            'user_id': {'$in': similar_user_ids},
            'movie_id': movie['movie_id']
        }))
        
        if not ratings:
            return 3.0
        
        # Moyenne pondérée
        numerator = 0
        denominator = 0
        
        for rating in ratings:
            similarity = similar_users.get(str(rating['user_id']), 0)
            numerator += similarity * rating['rating']
            denominator += abs(similarity)
        
        if denominator == 0:
            return 3.0
        
        return numerator / denominator
    
    def _calculate_content_similarity(self, user, movie):
        """Calculer la similarité content-based"""
        # Score basé sur les préférences de genre
        user_prefs = user.get('preferences', {})
        genre_weights = user_prefs.get('genre_weights', {})
        
        movie_genres = movie.get('genres', [])
        
        if not genre_weights or not movie_genres:
            return 0.5  # Score neutre
        
        # Calculer le score moyen pour les genres
        scores = []
        for genre in movie_genres:
            score = genre_weights.get(genre, 2.5)  # 2.5 par défaut
            scores.append(score)
        
        avg_score = sum(scores) / len(scores)
        
        # Normaliser entre 0 et 1
        normalized = (avg_score - 1) / 4
        return max(0, min(1, normalized))
    
    def _generate_explanation(self, scores):
        """Générer une explication"""
        explanations = []
        
        if scores.get('item_based', 0) > 3.5:
            explanations.append("Similaire à vos films favoris")
        
        if scores.get('user_based', 0) > 3.5:
            explanations.append("Aimé par des gens comme vous")
        
        if scores.get('content_based', 0) > 0.6:
            explanations.append("Correspond à vos goûts")
        
        if scores.get('cluster', 0) > 3.5:
            explanations.append("Populaire dans votre groupe")
        
        return " | ".join(explanations) if explanations else "Recommandation personnalisée"
    
    def update_user_preferences(self, user_object_id):
        """Mettre à jour les préférences de l'utilisateur"""
        try:
            user = self.db.users.find_one({'_id': ObjectId(user_object_id)})
            if not user:
                return
            
            user_id = user.get('user_id')
            if not user_id:
                return
            
            # Recalculer les préférences de genre
            pipeline = [
                {'$match': {'user_id': user_id}},
                {'$lookup': {
                    'from': 'movies',
                    'localField': 'movie_id',
                    'foreignField': 'movie_id',
                    'as': 'movie_info'
                }},
                {'$unwind': '$movie_info'},
                {'$unwind': '$movie_info.genres'},
                {'$group': {
                    '_id': '$movie_info.genres',
                    'avg_rating': {'$avg': '$rating'},
                    'count': {'$sum': 1}
                }}
            ]
            
            genre_prefs = list(self.db.ratings.aggregate(pipeline))
            
            genre_weights = {}
            for pref in genre_prefs:
                genre = pref['_id']
                avg_rating = pref['avg_rating']
                genre_weights[genre] = float(avg_rating)
            
            # Mettre à jour
            self.db.users.update_one(
                {'_id': ObjectId(user_object_id)},
                {'$set': {'preferences.genre_weights': genre_weights}}
            )
            
        except Exception as e:
            print(f"⚠️ Erreur mise à jour préférences: {e}")