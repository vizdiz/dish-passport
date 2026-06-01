-- Dish Passport — real auth. users gains login credentials. Columns are nullable so the
-- log/impression user-upsert safety net still works for ids created outside registration.
-- Apply after 005: psql "$DP_DATABASE_URL" -f migrations/006_auth.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS username      TEXT UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
