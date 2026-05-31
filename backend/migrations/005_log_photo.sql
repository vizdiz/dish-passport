-- Dish Passport — photo support. A photo is a user's shot of THEIR dish (per-log), uploaded
-- to S3 via a presigned PUT; only the resulting URL is stored here (never the bytes).
-- Apply after 004: psql "$DP_DATABASE_URL" -f migrations/005_log_photo.sql

ALTER TABLE logs ADD COLUMN IF NOT EXISTS photo_url TEXT;
