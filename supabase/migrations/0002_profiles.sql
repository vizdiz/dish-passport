-- Dish Passport — Supabase migration 0002: profiles + auth trigger.
--
-- Supabase Auth (auth.users, UUID ids) owns identity and credentials. The old app-level
-- `users` table is gone; its non-credential columns (log_count, created_at, username) move
-- to public.profiles, keyed 1:1 to auth.users.

create table if not exists public.profiles (
    id          uuid        primary key references auth.users(id) on delete cascade,
    username    text        unique not null,
    created_at  timestamptz not null default now(),
    log_count   integer     not null default 0   -- denormalized for cheap cold-start gating
);

-- On sign-up, mirror the new auth.users row into public.profiles, taking username from the
-- signup metadata (raw_user_meta_data->>'username'). SECURITY DEFINER so the trigger can
-- write to public.profiles regardless of the caller's role (the auth admin inserts the user).
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, username)
    values (
        new.id,
        -- username comes from signup metadata; fall back to the email local-part
        -- (username@users.dishport.app pseudo-emails) so the NOT NULL constraint holds.
        coalesce(new.raw_user_meta_data->>'username', split_part(new.email, '@', 1))
    );
    return new;
end;
$$;

-- Own the function by the postgres role so SECURITY DEFINER runs with the right privileges.
alter function public.handle_new_user() owner to postgres;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();
