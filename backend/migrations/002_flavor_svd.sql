-- Dish Passport — Service 3 (Flavor + SVD).
-- Apply after 001: psql "$DP_DATABASE_URL" -f migrations/002_flavor_svd.sql

CREATE TABLE IF NOT EXISTS flavor_svd_model (
    version          TEXT        PRIMARY KEY,
    components       JSONB       NOT NULL,     -- n_factors x 10 loadings
    singular_values  JSONB       NOT NULL,     -- n_factors
    mean             JSONB       NOT NULL,     -- 10, the centering mean
    factor_labels    JSONB       NOT NULL,     -- n_factors, derived from loadings
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dish_flavor_factors (
    dish_id            BIGINT      PRIMARY KEY REFERENCES dishes(id),
    factors            vector(4)   NOT NULL,
    svd_model_version  TEXT        NOT NULL REFERENCES flavor_svd_model(version),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
