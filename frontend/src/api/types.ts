/** Wire types mirroring the backend response models (app/schemas.py). */

export type Sentiment = 'liked' | 'neutral' | 'disliked';
export type ImpressionContext = 'feed' | 'recs' | 'similar';

export interface FactorScore {
  label: string;
  value: number;
}

export interface Dish {
  id: number;
  name: string;
  description: string;
  ingredients: string[];
  prep_method: string | null;
  flavor: Record<string, number>; // dim -> 0..1
  embedding_model_version: string;
  created_at: string;
  factors?: FactorScore[] | null; // 4-factor projection (Service 3), when an SVD model exists
  svd_model_version?: string | null;
}

export interface LogResponse {
  dish: Dish;
  is_new: boolean;
  log_id: number;
}

export interface SimilarNeighbor {
  dish: Dish;
  cosine: number;
}

export interface SimilarResponse {
  dish_id: number;
  n: number;
  neighbors: SimilarNeighbor[];
}

export interface RecommendationItem {
  dish: Dish;
  score: number;
  explanation: string;
  components: Record<string, number>;
}

export interface RecommendationsResponse {
  user_id: number;
  n: number;
  cold_start: boolean;
  recommendations: RecommendationItem[];
}

export interface TasteProfile {
  user_id: number;
  n_dishes: number;
  flavor_factor_pref: FactorScore[] | null;
  representative_dishes: Dish[];
  has_liked_centroid: boolean;
  has_disliked_centroid: boolean;
}

export interface ImpressionEvent {
  user_id: number;
  dish_id: number;
  shown_at: string; // ISO 8601
  context: ImpressionContext;
  converted: boolean;
}

export interface LogRequest {
  user_id: number;
  text?: string;
  dish_id?: number;
  sentiment?: Sentiment;
  rating?: number;
  notes?: string;
  photo_url?: string;
}
