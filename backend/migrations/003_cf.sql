-- Dish Passport — Service 4 (Collaborative filtering / ALS).
-- Apply after 002: psql "$DP_DATABASE_URL" -f migrations/003_cf.sql
-- CF factors are plain float arrays (not pgvector): they're read as dot products at
-- inference, never indexed for nearest-neighbor.

CREATE TABLE IF NOT EXISTS cf_user_factors (
    user_id        BIGINT              PRIMARY KEY REFERENCES users(id),
    factors        DOUBLE PRECISION[]  NOT NULL,
    model_version  TEXT                NOT NULL,
    computed_at    TIMESTAMPTZ         NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cf_item_factors (
    dish_id        BIGINT              PRIMARY KEY REFERENCES dishes(id),
    factors        DOUBLE PRECISION[]  NOT NULL,
    model_version  TEXT                NOT NULL,
    computed_at    TIMESTAMPTZ         NOT NULL DEFAULT now()
);
