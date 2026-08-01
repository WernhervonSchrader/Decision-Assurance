# Event versioning and migration

The v1 event envelope contains `event_type`, `schema_version`, `event_id`, `timestamp`, `tenant_id`,
`actor_id`, `correlation_id`, `source_component` and `payload`. `EventRegistry` accepts only exact
registered versions. Unknown versions are not interpreted heuristically.

Migration is explicit, lossless and produces a new envelope plus source/target versions and the
SHA-256 hash of the untouched original. The original event/export remains retained. Adding or
changing an event version requires a parser registration, an explicit migration, round-trip/data-loss
tests and an update to export stream recognition. Silent field dropping is prohibited.
