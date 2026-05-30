-- Dish Passport — Service 5 (Recommendation / taste profiles).
-- Apply after 003: psql "$DP_DATABASE_URL" -f migrations/004_taste_profiles.sql
-- Batch-computed (rebuild_taste_profiles); read on the recommend request path.

CREATE TABLE IF NOT EXISTS user_taste_profiles (
    user_id             BIGINT       PRIMARY KEY REFERENCES users(id),
    liked_centroid      vector(1536),                 -- mean embedding of liked/neutral dishes
    disliked_centroid   vector(1536),                 -- disliked + decaying soft-neg impressions
    flavor_factor_pref  vector(4),                    -- mean latent factors over liked dishes
    n_dishes            INTEGER      NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);
