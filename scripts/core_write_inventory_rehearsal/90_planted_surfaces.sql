-- The core-write inventory's rehearsal fixture: one planted write surface of each kind that D6's
-- revoke set does NOT cover, on a scratch database built from the real migrations. The rehearsal
-- passes only if the inventory reports every planted surface as omitted and nothing else, so the
-- route proves, in its exact runtime and before it receives the database secret, that it catches
-- an omission. Every planted object's name carries the marker inventory_probe.
--
-- Applied by postgres after migrations 0001-0015, under the Supabase-like default privileges
-- (service_role holds ALL on new tables and functions). Scratch only: never applied anywhere else.

-- F: a SECURITY DEFINER function in an exposed schema, executable by service_role, whose owner can
-- write core evidence.
CREATE FUNCTION public.inventory_probe_definer() RETURNS integer
LANGUAGE sql SECURITY DEFINER AS 'SELECT 1';

-- V: a view over a core table that service_role can write and that runs as its owner.
CREATE VIEW public.inventory_probe_view AS SELECT * FROM public.predictions;

-- R: a rule on a table service_role can write, whose action reaches a core table.
CREATE TABLE public.inventory_probe_rule_table (x integer);
CREATE RULE inventory_probe_rule AS ON INSERT TO public.inventory_probe_rule_table
DO ALSO DELETE FROM public.prediction_outcomes WHERE false;

-- G: a trigger on a table service_role can write, whose function is SECURITY DEFINER and owned by a
-- role that can write core evidence (the function is also an F surface).
CREATE TABLE public.inventory_probe_trigger_table (x integer);
CREATE FUNCTION public.inventory_probe_trigger() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER AS 'BEGIN RETURN NEW; END';
CREATE TRIGGER inventory_probe_trigger BEFORE INSERT ON public.inventory_probe_trigger_table
FOR EACH ROW EXECUTE FUNCTION public.inventory_probe_trigger();

-- K: a cascading foreign key from a core table to a table service_role can delete from.
CREATE TABLE public.inventory_probe_parent (id integer PRIMARY KEY);
ALTER TABLE public.analysis_run_details
ADD COLUMN inventory_probe integer REFERENCES public.inventory_probe_parent (id) ON DELETE CASCADE;
