# Localization Model

Interface language is selected from `Accept-Language`; supported values are
German (`de`) and English (`en`), with English fallback. Tenant default locale
and explicit user locale are future authenticated-profile attributes. Machine
contracts, audit codes, timestamps and reason codes are locale-neutral.

Localized display messages live in translation catalogs, never domain logic.
RFC 3339 UTC is used over the API; clients localize dates, numbers and currency.
Content language is independent of interface locale. The model does not prevent
future right-to-left presentation.

Research keeps interface language (`Accept-Language`), query locale, preferred source languages,
detected content language and any future tenant default separate. DE/EN messages are localized;
stored reason codes, provider classifications, audit data and evidence statuses remain neutral.

The v0.5 pilot verifies German quote Intake, an English Research source, German error output and
English fallback for unsupported interface languages. PostgreSQL, jobs and release evidence retain
locale-neutral codes and RFC 3339 UTC timestamps. There is no browser UI in this milestone.

Operating mode, country codes, provider hosts and startup failure codes are deployment configuration,
not user-facing localized content. `local`, `eu-managed`, ISO country codes and machine-readable
reason codes remain stable English identifiers for audit and automation. Operator runbooks may have
localized explanatory text, but must preserve the original code and configuration hash. Neither
interface language, explicit user locale, tenant default locale nor content language can select or
alter residency, provider egress or tenant context. Both profiles run the same DE/EN catalogs and
English fallback tests.

