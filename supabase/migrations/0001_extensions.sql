-- Dish Passport — Supabase migration 0001: extensions.
-- pgvector is provided by Supabase; enable it before any vector() column is created.
-- Supabase installs extensions into the dedicated "extensions" schema by convention,
-- but "create extension if not exists vector" (schema-less) is what the original schema
-- used and is fully supported here.

create extension if not exists vector;
