-- Dish Passport — Supabase migration 0004: Row Level Security.
--
-- The Python worker connects with the service_role key, which BYPASSES RLS entirely,
-- so these policies are NOT on the hot path. They exist to make future direct-from-client
-- (anon/authenticated key) access correct and safe.
--
-- Model:
--   * Owned rows  (profiles, logs, impressions, cf_user_factors, user_taste_profiles):
--       a user may only touch rows they own (user_id = auth.uid(); profiles: id = auth.uid()).
--   * Global rows (dishes, flavor_svd_model, dish_flavor_factors, cf_item_factors):
--       readable by any authenticated user; writable only by service_role.
--
-- Explicit service_role write policies are included for clarity even though service_role
-- bypasses RLS; a service_role client will succeed either way.

-- ---------------------------------------------------------------------------
-- Enable RLS on every public table
-- ---------------------------------------------------------------------------
alter table public.profiles            enable row level security;
alter table public.dishes              enable row level security;
alter table public.logs                enable row level security;
alter table public.impressions         enable row level security;
alter table public.flavor_svd_model    enable row level security;
alter table public.dish_flavor_factors enable row level security;
alter table public.cf_user_factors     enable row level security;
alter table public.cf_item_factors     enable row level security;
alter table public.user_taste_profiles enable row level security;

-- ---------------------------------------------------------------------------
-- profiles — owner is keyed by id (= auth.users id)
-- ---------------------------------------------------------------------------
create policy profiles_select_own on public.profiles
    for select to authenticated using (id = auth.uid());
create policy profiles_insert_own on public.profiles
    for insert to authenticated with check (id = auth.uid());
create policy profiles_update_own on public.profiles
    for update to authenticated using (id = auth.uid()) with check (id = auth.uid());
create policy profiles_delete_own on public.profiles
    for delete to authenticated using (id = auth.uid());

-- ---------------------------------------------------------------------------
-- Owned data tables — keyed by user_id = auth.uid()
-- ---------------------------------------------------------------------------
create policy logs_select_own on public.logs
    for select to authenticated using (user_id = auth.uid());
create policy logs_insert_own on public.logs
    for insert to authenticated with check (user_id = auth.uid());
create policy logs_update_own on public.logs
    for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy logs_delete_own on public.logs
    for delete to authenticated using (user_id = auth.uid());

create policy impressions_select_own on public.impressions
    for select to authenticated using (user_id = auth.uid());
create policy impressions_insert_own on public.impressions
    for insert to authenticated with check (user_id = auth.uid());
create policy impressions_update_own on public.impressions
    for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy impressions_delete_own on public.impressions
    for delete to authenticated using (user_id = auth.uid());

create policy cf_user_factors_select_own on public.cf_user_factors
    for select to authenticated using (user_id = auth.uid());
create policy cf_user_factors_insert_own on public.cf_user_factors
    for insert to authenticated with check (user_id = auth.uid());
create policy cf_user_factors_update_own on public.cf_user_factors
    for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy cf_user_factors_delete_own on public.cf_user_factors
    for delete to authenticated using (user_id = auth.uid());

create policy user_taste_profiles_select_own on public.user_taste_profiles
    for select to authenticated using (user_id = auth.uid());
create policy user_taste_profiles_insert_own on public.user_taste_profiles
    for insert to authenticated with check (user_id = auth.uid());
create policy user_taste_profiles_update_own on public.user_taste_profiles
    for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy user_taste_profiles_delete_own on public.user_taste_profiles
    for delete to authenticated using (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- Global tables — read by any authenticated user, write only by service_role
-- ---------------------------------------------------------------------------
create policy dishes_select_authenticated on public.dishes
    for select to authenticated using (true);
create policy dishes_write_service_role on public.dishes
    for all to service_role using (true) with check (true);

create policy flavor_svd_model_select_authenticated on public.flavor_svd_model
    for select to authenticated using (true);
create policy flavor_svd_model_write_service_role on public.flavor_svd_model
    for all to service_role using (true) with check (true);

create policy dish_flavor_factors_select_authenticated on public.dish_flavor_factors
    for select to authenticated using (true);
create policy dish_flavor_factors_write_service_role on public.dish_flavor_factors
    for all to service_role using (true) with check (true);

create policy cf_item_factors_select_authenticated on public.cf_item_factors
    for select to authenticated using (true);
create policy cf_item_factors_write_service_role on public.cf_item_factors
    for all to service_role using (true) with check (true);
