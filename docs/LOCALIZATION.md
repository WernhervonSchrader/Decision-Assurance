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

