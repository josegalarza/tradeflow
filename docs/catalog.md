# tradeflow data catalog

> **Generated file.** Written by `governance/build_catalog.py` from the
> dbt manifest and `governance/policy.yml`. Run `make governance` to
> refresh. Do not edit by hand.

Generated 2026-08-12 16:30 UTC

This catalog is produced from the same classification tags that generate
the masked role views in `warehouse/models/40_secure/`. It therefore
cannot disagree with what the warehouse does -- if a column is listed here
as hashed for analysts, it is hashed because this row and that view come
from one source.

---

## Summary

- **26** models across 3 layers
- **525** columns classified
- **43** columns carrying personal data
- **4** access roles
- **1** documented classification exemptions

### Columns by classification

| Classification | Columns | Share | Meaning |
|---|--:|--:|---|
| `public` | 33 | 6.3% | Non-sensitive reference data. Instrument names, sectors, market prices. Could be published without consequence. |
| `internal` | 422 | 80.4% | Ordinary business data. Order flow, surrogate keys, counts, dates. Restricted to employees, but no individual is identifiable from it alone. |
| `confidential` | 53 | 10.1% | Commercially or personally sensitive. Account balances, positions, risk ratings, names, behavioural timestamps. Real harm from disclosure. |
| `restricted` | 17 | 3.2% | Directly identifying or regulated. Email, phone, date of birth, national ID, street address, raw IP. Disclosure is a reportable incident. |

### Personal data by category

| Category | Columns |
|---|--:|
| `name` | 10 |
| `address` | 9 |
| `pseudonymous_id` | 6 |
| `email` | 4 |
| `date_of_birth` | 4 |
| `phone` | 3 |
| `government_id` | 3 |
| `online_identifier` | 2 |
| `device_fingerprint` | 1 |
| `behavioural` | 1 |

---

## Access roles

| Role | Schema | Clearance | Above clearance | Purpose |
|---|---|---|---|---|
| `analyst` | `secure_analyst` | `internal` | masked | The default role, and the one most queries should run as. Full access to behaviour, balances and order flow; identity is hashed so cohorts and distinct counts still work. |
| `auditor` | `secure_auditor` | `restricted` | masked | Compliance and internal audit. Sees everything unmasked -- this role exists so that a legitimate regulatory request never requires someone to be granted access to `marts` directly, which is how temporary exceptions become permanent. |
| `marketing` | `secure_marketing` | `internal` | withheld entirely | Campaign and lifecycle marketing. Segments, tiers, cohorts and engagement only. Cannot see balances, positions, contact details or compliance state -- and cannot see that it is missing. |
| `support` | `secure_support` | `confidential` | masked | Customer support. Needs to verify who is on the phone and see their account state, and needs neither their national ID nor their full contact details to do it. |

### Masking strategies

| Strategy | Behaviour |
|---|---|
| `generalize` | Reduced in precision until it stops identifying. Date of birth becomes a decade band, postcode drops its last two characters, a precise timestamp becomes a month. Keeps the distribution, loses the individual. |
| `hash` | Salted MD5. Destroys the value, preserves equality -- so distinct counts and joins across systems still work. The right choice for identifiers analysts need to group by but never need to read. |
| `none` | Explicit exemption: the column sits above the role's clearance but is passed through unmasked anyway. Used where the analytical value is high and the re-identification risk is low on its own -- `city`, for example. An exemption, recorded as a decision rather than an omission. |
| `partial` | Reveals enough to confirm, not enough to contact. `j***@example.com`, `+61 *** *** 789`. Exists for support staff verifying a caller's identity. |
| `redact` | Replaced with a typed NULL. For columns with no analytical use below full clearance: national ID, street address, raw IP. |
| `tokenize` | Reversible pseudonym via a lookup table. Declared for completeness and NOT implemented -- a token vault is real infrastructure with its own access controls and key rotation, and a fake one would misrepresent the control. Using it raises an error rather than silently hashing. |

---

## PII register

Every column carrying personal data, with how each role sees it. This is
the table to reach for when answering a subject-access request or
assessing the blast radius of a credential leak.

| Model | Column | Category | Classification | Strategy | Per-role visibility |
|---|---|---|---|---|---|
| `stg_accounts` | `customer_id` | pseudonymous_id | `internal` | `none` | _not exposed to roles_ |
| `stg_app_events` | `customer_id` | pseudonymous_id | `internal` | `none` | _not exposed to roles_ |
| `stg_app_events` | `ip_address` | online_identifier | `restricted` | `redact` | _not exposed to roles_ |
| `stg_app_events` | `ip_address_prefix` | online_identifier | `internal` | `none` | _not exposed to roles_ |
| `stg_app_events` | `user_agent` | device_fingerprint | `confidential` | `hash` | _not exposed to roles_ |
| `stg_customer_extracts` | `city` | address | `confidential` | `none` | _not exposed to roles_ |
| `stg_customer_extracts` | `customer_id` | pseudonymous_id | `internal` | `none` | _not exposed to roles_ |
| `stg_customer_extracts` | `date_of_birth` | date_of_birth | `restricted` | `generalize` | _not exposed to roles_ |
| `stg_customer_extracts` | `email` | email | `restricted` | `hash` | _not exposed to roles_ |
| `stg_customer_extracts` | `first_name` | name | `confidential` | `redact` | _not exposed to roles_ |
| `stg_customer_extracts` | `full_name` | name | `confidential` | `redact` | _not exposed to roles_ |
| `stg_customer_extracts` | `last_name` | name | `confidential` | `redact` | _not exposed to roles_ |
| `stg_customer_extracts` | `national_id` | government_id | `restricted` | `redact` | _not exposed to roles_ |
| `stg_customer_extracts` | `phone_number` | phone | `restricted` | `partial` | _not exposed to roles_ |
| `stg_customer_extracts` | `postcode` | address | `confidential` | `generalize` | _not exposed to roles_ |
| `stg_customer_extracts` | `street_address` | address | `restricted` | `redact` | _not exposed to roles_ |
| `int_customer_versions` | `city` | address | `confidential` | `none` | _not exposed to roles_ |
| `int_customer_versions` | `customer_id` | pseudonymous_id | `internal` | `none` | _not exposed to roles_ |
| `int_customer_versions` | `date_of_birth` | date_of_birth | `restricted` | `generalize` | _not exposed to roles_ |
| `int_customer_versions` | `email` | email | `restricted` | `hash` | _not exposed to roles_ |
| `int_customer_versions` | `first_name` | name | `confidential` | `redact` | _not exposed to roles_ |
| `int_customer_versions` | `full_name` | name | `confidential` | `redact` | _not exposed to roles_ |
| `int_customer_versions` | `last_name` | name | `confidential` | `redact` | _not exposed to roles_ |
| `int_customer_versions` | `national_id` | government_id | `restricted` | `redact` | _not exposed to roles_ |
| `int_customer_versions` | `phone_number` | phone | `restricted` | `partial` | _not exposed to roles_ |
| `int_customer_versions` | `postcode` | address | `confidential` | `generalize` | _not exposed to roles_ |
| `int_customer_versions` | `street_address` | address | `restricted` | `redact` | _not exposed to roles_ |
| `agg_customer_performance` | `customer_id` | pseudonymous_id | `internal` | `none` | analyst: clear<br>auditor: clear<br>marketing: clear<br>support: clear |
| `agg_customer_performance` | `email` | email | `restricted` | `hash` | analyst: hash<br>auditor: clear<br>marketing: withheld<br>support: partial |
| `agg_customer_performance` | `full_name` | name | `confidential` | `redact` | analyst: redact<br>auditor: clear<br>marketing: withheld<br>support: clear |
| `agg_customer_performance` | `last_seen_at` | behavioural | `confidential` | `generalize` | analyst: generalize<br>auditor: clear<br>marketing: withheld<br>support: clear |
| `dim_customer` | `age_years` | date_of_birth | `confidential` | `redact` | analyst: redact<br>auditor: clear<br>marketing: withheld<br>support: clear |
| `dim_customer` | `city` | address | `confidential` | `none` | analyst: clear<br>auditor: clear<br>marketing: withheld<br>support: clear |
| `dim_customer` | `customer_id` | pseudonymous_id | `internal` | `none` | analyst: clear<br>auditor: clear<br>marketing: clear<br>support: clear |
| `dim_customer` | `date_of_birth` | date_of_birth | `restricted` | `generalize` | analyst: generalize<br>auditor: clear<br>marketing: withheld<br>support: generalize |
| `dim_customer` | `email` | email | `restricted` | `hash` | analyst: hash<br>auditor: clear<br>marketing: withheld<br>support: partial |
| `dim_customer` | `first_name` | name | `confidential` | `redact` | analyst: redact<br>auditor: clear<br>marketing: withheld<br>support: clear |
| `dim_customer` | `full_name` | name | `confidential` | `redact` | analyst: redact<br>auditor: clear<br>marketing: withheld<br>support: clear |
| `dim_customer` | `last_name` | name | `confidential` | `redact` | analyst: redact<br>auditor: clear<br>marketing: withheld<br>support: clear |
| `dim_customer` | `national_id` | government_id | `restricted` | `redact` | analyst: redact<br>auditor: clear<br>marketing: withheld<br>support: redact |
| `dim_customer` | `phone_number` | phone | `restricted` | `partial` | analyst: partial<br>auditor: clear<br>marketing: withheld<br>support: partial |
| `dim_customer` | `postcode` | address | `confidential` | `generalize` | analyst: generalize<br>auditor: clear<br>marketing: withheld<br>support: clear |
| `dim_customer` | `street_address` | address | `restricted` | `redact` | analyst: redact<br>auditor: clear<br>marketing: withheld<br>support: redact |

---

## Documented exemptions

Columns classified below the level their name would imply. Each one
requires a written rationale to pass CI -- exceptions are permitted,
undocumented exceptions are not.

### `stg_app_events.ip_address_prefix`

Classified `internal`.

> Deliberately truncated to a /24 so that it is the safe alternative to ip_address rather than a second copy of it. The last octet is what identifies a subscriber line; a /24 spans up to 254 addresses and is widely treated as aggregated network data. Classifying it confidential would put it out of reach of the analysts it was created for, leaving them to reach for the raw address instead -- a strictly worse outcome. The raw ip_address remains restricted and redacted.


---

## Models

### Layer `10_staging`

#### `stg_accounts`

**Grain:** one row per account_id  
**Materialization:** `view`

One row per brokerage account. Accounts belong to a customer; a small share close during the window.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `account_id` | `VARCHAR` | `internal` | - | `-` | Primary key. |
| `customer_id` | `VARCHAR` | `internal` | yes (pseudonymous_id) | `none` | Owning customer. Foreign key to stg_customer_extracts. |
| `account_type` | `VARCHAR` | `internal` | - | `-` | cash, margin or retirement. Governs fees and leverage. |
| `base_currency` | `VARCHAR` | `internal` | - | `-` | Currency the account is denominated in. |
| `opened_at` | `TIMESTAMP` | `internal` | - | `-` | Timestamp the account was opened. |
| `closed_at` | `TIMESTAMP` | `internal` | - | `-` | Timestamp the account was closed. NULL while open. |
| `opened_date` | `DATE` | `internal` | - | `-` | Date part of opened_at, for joining to dim_date. |
| `closed_date` | `DATE` | `internal` | - | `-` | Date part of closed_at. |
| `account_status` | `VARCHAR` | `internal` | - | `-` | Derived from closed_at rather than trusted from the source. |
| `margin_limit` | `DECIMAL(18,2)` | `confidential` | - | `-` | Approved margin borrowing limit in the base currency. |

#### `stg_app_events` **contains PII**

**Grain:** one row per event_id  
**Materialization:** `view`

Clickstream events grouped into sessions. Highest-volume model in the warehouse, and the one that proves the classification framework looks at more than column names -- see `ip_address` and `user_agent`.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `event_id` | `VARCHAR` | `internal` | - | `-` | Primary key. |
| `session_id` | `VARCHAR` | `internal` | - | `-` | Groups events belonging to one app session. |
| `customer_id` | `VARCHAR` | `internal` | yes (pseudonymous_id) | `none` | Customer who generated the event. |
| `event_type` | `VARCHAR` | `internal` | - | `-` | What the customer did. |
| `device_family` | `VARCHAR` | `internal` | - | `-` | Device or browser family, derived from the user agent. |
| `app_version` | `VARCHAR` | `internal` | - | `-` | Client build that emitted the event. |
| `user_agent` | `VARCHAR` | `confidential` | yes (device_fingerprint) | `hash` | Raw client user-agent string. Personal data: high-entropy enough to contribute to device fingerprinting, so it is confidential and hashed for everyone below auditor clearance. |
| `ip_address` | `VARCHAR` | `restricted` | yes (online_identifier) | `redact` | Full client IP. Personal data under GDPR Recital 30 -- it identifies a subscriber line, not just a machine. Analysts should use ip_address_prefix instead. |
| `ip_address_prefix` | `VARCHAR` | `internal` | yes (online_identifier) | `none` | The /24 prefix of the client IP. Retains geography and network signal, drops the ability to single out a household. |
| `occurred_at` | `TIMESTAMP` | `internal` | - | `-` | When the event fired on the client. |
| `event_date` | `DATE` | `internal` | - | `-` | Date part of occurred_at. The partition key in the source. |

#### `stg_cash_movements`

**Grain:** one row per movement_id  
**Materialization:** `view`

Cash in and out of an account. Amounts keep the source sign convention so SUM is net flow; `direction` is derived for one-sided aggregation.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `movement_id` | `VARCHAR` | `internal` | - | `-` | Primary key. |
| `account_id` | `VARCHAR` | `internal` | - | `-` | Account the cash moved through. |
| `movement_type` | `VARCHAR` | `internal` | - | `-` | deposit, withdrawal, fee, dividend or interest. |
| `payment_method` | `VARCHAR` | `confidential` | - | `-` | How the money moved. NULL for internal accruals. |
| `amount` | `DECIMAL(18,2)` | `confidential` | - | `-` | Signed amount. Negative for withdrawals and fees. |
| `absolute_amount` | `DECIMAL(18,2)` | `confidential` | - | `-` | Unsigned magnitude, for inflow/outflow aggregation. |
| `direction` | `VARCHAR` | `internal` | - | `-` | inflow or outflow, derived from the sign of amount. |
| `movement_currency` | `VARCHAR` | `internal` | - | `-` | Currency of the movement, matching the account base currency. |
| `occurred_at` | `TIMESTAMP` | `internal` | - | `-` | When the movement settled. |
| `occurred_date` | `DATE` | `internal` | - | `-` | Date part of occurred_at. |

#### `stg_customer_extracts` **contains PII**

**Grain:** one row per customer_id per extract_date  
**Materialization:** `view`

Month-end extracts of the mutable customer record: one row per customer per extract date, holding that customer's state as at that date. Source for dim_customer's SCD2 history. The most heavily classified model in the warehouse. Nothing is masked here by design -- see the model's header comment.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `customer_id` | `VARCHAR` | `internal` | yes (pseudonymous_id) | `none` | Primary key of the customer, stable across extracts. |
| `extract_date` | `DATE` | `internal` | - | `-` | Date this snapshot of the customer record was taken. |
| `first_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Given name. |
| `last_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Family name. |
| `full_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Concatenation of given and family name, for display. |
| `email` | `VARCHAR` | `restricted` | yes (email) | `hash` | Primary contact email, lowercased and trimmed. |
| `phone_number` | `VARCHAR` | `restricted` | yes (phone) | `partial` | Contact number in E.164-ish format with country prefix. |
| `date_of_birth` | `DATE` | `restricted` | yes (date_of_birth) | `generalize` | Date of birth. Drives suitability and age-bracket analysis. |
| `national_id` | `VARCHAR` | `restricted` | yes (government_id) | `redact` | Government identifier (SSN, TFN, NINO, ...). The highest-risk column in the warehouse. |
| `street_address` | `VARCHAR` | `restricted` | yes (address) | `redact` | Residential street address. |
| `city` | `VARCHAR` | `confidential` | yes (address) | `none` | Residential city. |
| `postcode` | `VARCHAR` | `confidential` | yes (address) | `generalize` | Residential postcode. |
| `country_code` | `VARCHAR` | `internal` | - | `-` | ISO 3166-1 alpha-2 country of residence. |
| `kyc_status` | `VARCHAR` | `confidential` | - | `-` | Know-your-customer state as at the extract date. Changes over time, which is the primary reason dim_customer is SCD2. |
| `risk_rating` | `VARCHAR` | `confidential` | - | `-` | Internal risk band assigned by compliance. |
| `customer_tier` | `VARCHAR` | `internal` | - | `-` | Commercial tier, driving fee schedule and support routing. |
| `marketing_opt_in` | `BOOLEAN` | `confidential` | - | `-` | Consent flag for marketing contact. Consent state is itself regulated -- acting on a stale value is the compliance failure. |
| `created_at` | `TIMESTAMP` | `internal` | - | `-` | When the customer record was first created. |
| `updated_at` | `TIMESTAMP` | `internal` | - | `-` | Most recent change to the record as at the extract date. |

#### `stg_executions`

**Grain:** one row per execution_id  
**Materialization:** `view`

One row per fill. Faithful to the source -- duplicates are defects, not noise, and are quarantined in `int_executions_screened`.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `execution_id` | `VARCHAR` | `internal` | - | `-` | Primary key. Duplicated under --inject-anomalies. |
| `order_id` | `VARCHAR` | `internal` | - | `-` | Parent order. |
| `venue` | `VARCHAR` | `internal` | - | `-` | Execution venue the fill was routed to. |
| `execution_quantity` | `DECIMAL(28,8)` | `internal` | - | `-` | Units filled by this execution. |
| `execution_price` | `DECIMAL(18,4)` | `internal` | - | `-` | Price per unit, in the instrument's listing currency. |
| `execution_currency` | `VARCHAR` | `internal` | - | `-` | Currency of execution_price and commission. |
| `commission` | `DECIMAL(18,4)` | `internal` | - | `-` | Brokerage charged on the fill, in the execution currency. Zero for commission-free US equities. |
| `gross_notional` | `DECIMAL(38,12)` | `internal` | - | `-` | quantity x price, before commission, in the listing currency. |
| `executed_at` | `TIMESTAMP` | `internal` | - | `-` | When the fill occurred. |
| `executed_date` | `DATE` | `internal` | - | `-` | Date part of executed_at. The partition key in the source. |

#### `stg_fx_rates`

**Grain:** one row per base_currency, quote_currency, rate_date  
**Materialization:** `view`

Daily rate per currency pair against the reporting currency, including the USD -> USD identity row. Quoted every calendar day so a fill can always be converted without gap-filling.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `base_currency` | `VARCHAR` | `public` | - | `-` | Currency being converted from. |
| `quote_currency` | `VARCHAR` | `public` | - | `-` | Currency being converted to. Always USD in this warehouse. |
| `rate_date` | `DATE` | `public` | - | `-` | Date the rate applies to. |
| `rate` | `DECIMAL(18,8)` | `public` | - | `-` | Units of quote currency per one unit of base currency. |

#### `stg_instruments`

**Grain:** one row per instrument_id  
**Materialization:** `view`

One row per tradeable instrument. Conformed dimension source -- the same instrument key is used by orders, executions, prices and positions.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `instrument_id` | `VARCHAR` | `public` | - | `-` | Primary key. Surrogate key from the source system. |
| `symbol` | `VARCHAR` | `public` | - | `-` | Exchange ticker, e.g. AAPL or CBA.AX. |
| `instrument_name` | `VARCHAR` | `public` | - | `-` | Full legal name of the security. |
| `asset_class` | `VARCHAR` | `public` | - | `-` | equity, etf or crypto. Governs trading calendar and fees. |
| `exchange` | `VARCHAR` | `public` | - | `-` | Listing venue code. |
| `sector` | `VARCHAR` | `public` | - | `-` | GICS-style sector, or a thematic label for funds. |
| `listing_currency` | `VARCHAR` | `public` | - | `-` | Currency the instrument is quoted in. |
| `dividend_yield` | `DECIMAL(9,6)` | `public` | - | `-` | Annual dividend yield as a decimal fraction. |
| `is_active` | `BOOLEAN` | `public` | - | `-` | False for delisted instruments that still carry history. |
| `listed_date` | `DATE` | `public` | - | `-` | Date the instrument became tradeable on the platform. |

#### `stg_market_prices`

**Grain:** one row per instrument_id per price_date  
**Materialization:** `view`

Daily OHLCV per instrument. Equity rows exist only on trading days; crypto trades every calendar day. Simulated, not market data.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `instrument_id` | `VARCHAR` | `public` | - | `-` | Foreign key to stg_instruments. |
| `symbol` | `VARCHAR` | `public` | - | `-` | Denormalised ticker, carried for query convenience. |
| `price_date` | `DATE` | `public` | - | `-` | Trading session date. |
| `open_price` | `DECIMAL(18,4)` | `public` | - | `-` | First traded price of the session. |
| `high_price` | `DECIMAL(18,4)` | `public` | - | `-` | Highest traded price of the session. |
| `low_price` | `DECIMAL(18,4)` | `public` | - | `-` | Lowest traded price of the session. |
| `close_price` | `DECIMAL(18,4)` | `public` | - | `-` | Last traded price of the session. The mark-to-market price. |
| `previous_close_price` | `DECIMAL(18,4)` | `public` | - | `-` | Close of the prior session, for return calculations. |
| `volume` | `BIGINT` | `public` | - | `-` | Shares or units traded during the session. |
| `price_currency` | `VARCHAR` | `public` | - | `-` | Currency the price is quoted in. |

#### `stg_orders`

**Grain:** one row per order_id  
**Materialization:** `view`

One row per order at its terminal state. Faithful to the source: not deduplicated, not filtered. `int_orders_screened` quarantines defects with a recorded reason.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `order_id` | `VARCHAR` | `internal` | - | `-` | Primary key. |
| `account_id` | `VARCHAR` | `internal` | - | `-` | Placing account. |
| `instrument_id` | `VARCHAR` | `internal` | - | `-` | Instrument being traded. |
| `side` | `VARCHAR` | `internal` | - | `-` | buy or sell. |
| `order_type` | `VARCHAR` | `internal` | - | `-` | market, limit, stop or stop_limit. |
| `time_in_force` | `VARCHAR` | `internal` | - | `-` | day, gtc or ioc. |
| `order_status` | `VARCHAR` | `internal` | - | `-` | Terminal state of the order. |
| `channel` | `VARCHAR` | `internal` | - | `-` | Client the order arrived through -- ios, android, web, api. |
| `order_quantity` | `DECIMAL(28,8)` | `internal` | - | `-` | Units requested. Fractional for crypto, whole units otherwise. Must be positive; negative values indicate an upstream defect. |
| `limit_price` | `DECIMAL(18,4)` | `internal` | - | `-` | Trigger price for non-market orders. NULL for market orders. |
| `placed_at` | `TIMESTAMP` | `internal` | - | `-` | When the customer submitted the order. |
| `resolved_at` | `TIMESTAMP` | `internal` | - | `-` | When the order reached its terminal state. |
| `placed_date` | `DATE` | `internal` | - | `-` | Session date the order belongs to. Orders placed while the market was shut carry the date of the session they rolled into. |

### Layer `20_intermediate`

#### `int_customer_versions` **contains PII**

**Grain:** one row per customer_id per version  
**Materialization:** `table`

Type 2 history reconstructed from the periodic customer extracts. Hashes the tracked attributes, keeps only the extracts where the hash changed, and closes each version the day before the next opens. Grain: one row per customer per version. Carries the complete PII surface, which is why every column here is classified even though the intermediate layer is otherwise summarised.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `customer_id` | `VARCHAR` | `internal` | yes (pseudonymous_id) | `none` | Natural key, stable across versions. |
| `version_number` | `BIGINT` | `internal` | - | `-` | 1-based version sequence within the customer. |
| `valid_from` | `DATE` | `internal` | - | `-` | First date this version applied. Inclusive. |
| `valid_to` | `TIMESTAMP` | `internal` | - | `-` | Last date this version applied. Inclusive. |
| `is_current` | `BOOLEAN` | `internal` | - | `-` | True for the version in force now. |
| `observed_at_extract_date` | `DATE` | `internal` | - | `-` | Extract this version was first observed in. Provenance. |
| `attribute_hash` | `VARCHAR` | `internal` | - | `-` | Hash of the tracked attributes. The change-detection mechanism -- adding a tracked attribute is a one-line change here rather than a fourteen clause boolean. |
| `first_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Given name as at this version. |
| `last_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Family name as at this version. |
| `full_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Display name as at this version. |
| `email` | `VARCHAR` | `restricted` | yes (email) | `hash` | Contact email as at this version. |
| `phone_number` | `VARCHAR` | `restricted` | yes (phone) | `partial` | Contact number as at this version. |
| `date_of_birth` | `DATE` | `restricted` | yes (date_of_birth) | `generalize` | Date of birth. |
| `national_id` | `VARCHAR` | `restricted` | yes (government_id) | `redact` | Government identifier. |
| `street_address` | `VARCHAR` | `restricted` | yes (address) | `redact` | Residential street address as at this version. |
| `city` | `VARCHAR` | `confidential` | yes (address) | `none` | Residential city. |
| `postcode` | `VARCHAR` | `confidential` | yes (address) | `generalize` | Residential postcode. |
| `country_code` | `VARCHAR` | `internal` | - | `-` | ISO 3166-1 alpha-2 country of residence. |
| `kyc_status` | `VARCHAR` | `confidential` | - | `-` | KYC state as at this version. |
| `risk_rating` | `VARCHAR` | `confidential` | - | `-` | Compliance risk band as at this version. |
| `customer_tier` | `VARCHAR` | `internal` | - | `-` | Commercial tier as at this version. |
| `marketing_opt_in` | `BOOLEAN` | `confidential` | - | `-` | Marketing consent as at this version. |
| `created_at` | `TIMESTAMP` | `internal` | - | `-` | Customer record creation timestamp. |
| `updated_at` | `TIMESTAMP` | `internal` | - | `-` | Most recent source change as at this version. |

#### `int_executions_priced`

**Grain:** one row per valid execution_id  
**Materialization:** `table`

Valid fills, converted to the reporting currency and joined to their trading context. The single place FX conversion and the buy/sell sign convention are applied -- every downstream model consumes the converted, signed measures rather than deriving its own. Grain: one row per valid execution_id.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `execution_id` | `VARCHAR` | `internal` | - | `-` | Primary key. Unique here, unlike upstream. |
| `fx_rate_to_reporting` | `DECIMAL(18,8)` | `internal` | - | `-` | Rate used for conversion. Joined INNER, so a missing rate fails the build rather than silently becoming a NULL that SUMs to zero. |
| `signed_quantity` | `DECIMAL(28,8)` | `internal` | - | `-` | Positive for buys, negative for sells. |
| `signed_cash_flow_reporting` | `DECIMAL(18,4)` | `internal` | - | `-` | Cash effect in the reporting currency, commission included. Negative for buys, positive for sells. |

<details><summary>19 derived columns inheriting the layer default (`internal`)</summary>

`order_id`, `account_id`, `customer_id`, `instrument_id`, `side`, `order_type`, `channel`, `account_type`, `venue`, `executed_at`, `executed_date`, `order_placed_at`, `execution_quantity`, `execution_price`, `execution_currency`, `commission`, `gross_notional`, `gross_notional_reporting`, `commission_reporting`

</details>

#### `int_executions_screened`

**Grain:** one row per stg_executions row  
**Materialization:** `table`

Every fill with a data quality verdict, including a cumulative fill quantity used to detect over-fills one fill at a time rather than condemning the whole order. Grain: one row per row in stg_executions.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `execution_id` | `VARCHAR` | `internal` | - | `-` | Fill identifier. NOT unique here -- duplicate fills are a detected defect, not noise to be silently collapsed. |
| `cumulative_filled_quantity` | `DECIMAL(38,8)` | `internal` | - | `-` | Running total of filled quantity for the parent order, ordered by execution time. Compared against the order quantity to flag only the fills that push it over. |
| `dq_reject_reasons` | `VARCHAR[]` | `internal` | - | `-` | Every failed check for this fill. |
| `is_valid` | `BOOLEAN` | `internal` | - | `-` | True when the fill passed every screen. |

<details><summary>13 derived columns inheriting the layer default (`internal`)</summary>

`order_id`, `venue`, `execution_quantity`, `execution_price`, `execution_currency`, `commission`, `gross_notional`, `executed_at`, `executed_date`, `order_quantity`, `order_status`, `order_placed_at`, `dq_reject_reason`

</details>

#### `int_order_fills`

**Grain:** one row per order_id with at least one valid fill  
**Materialization:** `view`

Fill summary per order: quantity delivered, volume-weighted average price, and milestone timestamps. Volume-weighted rather than a mean of prices -- averaging the price column weights a one-share fill equally with a thousand-share fill. Grain: one row per order that has at least one valid fill.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `order_id` | `VARCHAR` | `internal` | - | `-` | Primary key. |
| `primary_venue` | `VARCHAR` | `internal` | - | `-` | Venue that took the largest share of the order by quantity. |
| `average_fill_price` | `DECIMAL(18,4)` | `internal` | - | `-` | Volume-weighted average price across the order's fills. |

<details><summary>10 derived columns inheriting the layer default (`internal`)</summary>

`fill_count`, `venue_count`, `filled_quantity`, `filled_notional`, `filled_notional_reporting`, `commission_reporting`, `volume_weighted_price`, `first_filled_at`, `last_filled_at`, `first_filled_date`

</details>

#### `int_orders_screened`

**Grain:** one row per stg_orders row  
**Materialization:** `table`

Every order with a data quality verdict attached: `is_valid`, plus the full list of reasons it failed. The quarantine boundary -- nothing is deleted, so a drop in row counts is always explainable. Grain: one row per row in stg_orders (not deduplicated by design).

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `order_id` | `VARCHAR` | `internal` | - | `-` | Order identifier. NOT unique here: a duplicated order is one of the defects this model exists to detect, so deduplicating would defeat it. |
| `dq_reject_reasons` | `VARCHAR[]` | `internal` | - | `-` | List of every failed check. A list rather than a single value because an order can be both an orphan and negative, and a triage queue that shows one defect per pass costs a day per defect. |
| `is_valid` | `BOOLEAN` | `internal` | - | `-` | True when the order passed every screen. |
| `dq_reject_reason` | `VARCHAR` | `internal` | - | `-` | First reason, for grouping in charts where a list column is awkward. NULL for valid rows. |

<details><summary>12 derived columns inheriting the layer default (`internal`)</summary>

`account_id`, `instrument_id`, `side`, `order_type`, `time_in_force`, `order_status`, `channel`, `order_quantity`, `limit_price`, `placed_at`, `resolved_at`, `placed_date`

</details>

#### `int_position_movements`

**Grain:** one row per account_id, instrument_id, activity_date  
**Materialization:** `view`

Net daily change in holdings and cash per account and instrument. Collapsing fills to one row per day before the running balance is what makes fct_positions_daily affordable. Grain: one row per account, instrument and activity date.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `net_quantity_change` | `DECIMAL(38,8)` | `internal` | - | `-` | Signed change in units held on this day. |

<details><summary>10 derived columns inheriting the layer default (`internal`)</summary>

`account_id`, `instrument_id`, `activity_date`, `net_trade_cash_flow_reporting`, `commission_reporting`, `bought_quantity`, `sold_quantity`, `bought_cost_reporting`, `sold_proceeds_reporting`, `fill_count`

</details>

### Layer `30_marts`

#### `agg_customer_performance` **contains PII**

**Grain:** one row per customer_id  
**Type:** `aggregate`  
**Materialization:** `table`

One row per customer: lifetime trading behaviour, engagement and current portfolio state. Joined to the current version of dim_customer, which is the one legitimate use of `is_current`. Grain: one row per customer_id.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `customer_key` | `VARCHAR` | `internal` | - | `-` | Current customer dimension version. |
| `customer_id` | `VARCHAR` | `internal` | yes (pseudonymous_id) | `none` | Natural key. |
| `full_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Display name, current version. |
| `email` | `VARCHAR` | `restricted` | yes (email) | `hash` | Contact email, current version. |
| `country_code` | `VARCHAR` | `internal` | - | `-` | Country of residence. |
| `customer_tier` | `VARCHAR` | `internal` | - | `-` | Current commercial tier. |
| `risk_rating` | `VARCHAR` | `confidential` | - | `-` | Current compliance risk band. |
| `kyc_status` | `VARCHAR` | `confidential` | - | `-` | Current KYC state. |
| `age_band` | `VARCHAR` | `internal` | - | `-` | Bucketed age. Use instead of date_of_birth. |
| `marketing_opt_in` | `BOOLEAN` | `confidential` | - | `-` | Current marketing consent. |
| `signup_date` | `DATE` | `internal` | - | `-` | Date the customer joined. |
| `signup_month` | `DATE` | `internal` | - | `-` | Signup cohort. |
| `tenure_days` | `BIGINT` | `internal` | - | `-` | Days since signup. |
| `account_count` | `BIGINT` | `internal` | - | `-` | Accounts held at the latest snapshot date. |
| `account_equity_reporting` | `DECIMAL(38,4)` | `confidential` | - | `-` | Total equity across the customer's accounts. |
| `cash_balance_reporting` | `DECIMAL(38,4)` | `confidential` | - | `-` | Total cash across the customer's accounts. |
| `holdings_value_reporting` | `DECIMAL(38,4)` | `confidential` | - | `-` | Market value of all holdings. |
| `net_funded_reporting` | `DECIMAL(38,4)` | `confidential` | - | `-` | Deposits less withdrawals, lifetime. |
| `unrealised_gain_reporting` | `DECIMAL(38,4)` | `confidential` | - | `-` | Mark-to-market gain on open positions. |
| `realised_gain_reporting` | `DECIMAL(38,4)` | `confidential` | - | `-` | Profit or loss on closed positions. |
| `total_gain_reporting` | `DECIMAL(38,4)` | `confidential` | - | `-` | Realised plus unrealised. |
| `open_position_count` | `HUGEINT` | `internal` | - | `-` | Open positions at the latest snapshot date. |
| `lifetime_fill_count` | `BIGINT` | `internal` | - | `-` | Fills, lifetime. |
| `lifetime_order_count` | `HUGEINT` | `internal` | - | `-` | Orders placed, lifetime. |
| `lifetime_cancelled_count` | `HUGEINT` | `internal` | - | `-` | Orders cancelled, lifetime. |
| `lifetime_traded_notional_reporting` | `DECIMAL(38,4)` | `confidential` | - | `-` | Gross traded value, lifetime. |
| `lifetime_commission_reporting` | `DECIMAL(38,4)` | `confidential` | - | `-` | Commission paid, lifetime. The customer's revenue to us. |
| `mean_fill_notional_reporting` | `DOUBLE` | `confidential` | - | `-` | Average size of a fill. |
| `trading_days` | `BIGINT` | `internal` | - | `-` | Distinct days on which the customer traded. |
| `distinct_instruments_traded` | `BIGINT` | `internal` | - | `-` | Breadth of the customer's trading. |
| `distinct_sectors_traded` | `BIGINT` | `internal` | - | `-` | Sector breadth, a crude diversification proxy. |
| `first_trade_date` | `DATE` | `internal` | - | `-` | Date of first fill. |
| `last_trade_date` | `DATE` | `internal` | - | `-` | Date of most recent fill. |
| `largest_trade_symbol` | `VARCHAR` | `internal` | - | `-` | Instrument the customer has committed the most value to. |
| `primary_channel` | `VARCHAR` | `internal` | - | `-` | Most-used order channel. |
| `lifetime_event_count` | `BIGINT` | `internal` | - | `-` | App events, lifetime. |
| `lifetime_session_count` | `BIGINT` | `internal` | - | `-` | App sessions, lifetime. |
| `app_active_days` | `BIGINT` | `internal` | - | `-` | Distinct days with app activity. |
| `last_seen_at` | `TIMESTAMP` | `confidential` | yes (behavioural) | `generalize` | Most recent app event. Behavioural, and precise enough to reveal daily routine, so it is classified confidential rather than internal. |
| `primary_device_family` | `VARCHAR` | `internal` | - | `-` | Most-used device family. |
| `return_on_funded` | `DECIMAL(12,6)` | `confidential` | - | `-` | Total gain / net funded. NULL rather than zero for customers who have funded nothing -- an undefined return, not a flat one. |
| `cancellation_rate` | `DECIMAL(9,6)` | `internal` | - | `-` | Cancelled / placed, lifetime. |
| `has_ever_traded` | `BOOLEAN` | `internal` | - | `-` | True if the customer has any fill. |

#### `agg_daily_trading_activity`

**Grain:** one row per date_day, channel, asset_class  
**Type:** `aggregate`  
**Materialization:** `table`

Daily trading activity by channel and asset class. Serves the dashboard's landing page so it never scans the atomic facts. Grain: one row per date_day, channel, asset_class.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `date_day` | `DATE` | `internal` | - | `-` | Activity date. |
| `cancellation_rate` | `DECIMAL(9,6)` | `internal` | - | `-` | Cancelled orders / total orders. NULL on zero-order days. |

<details><summary>22 derived columns inheriting the layer default (`internal`)</summary>

`channel`, `asset_class`, `order_count`, `filled_order_count`, `cancelled_order_count`, `rejected_order_count`, `trading_accounts`, `trading_customers`, `ordered_quantity`, `mean_seconds_to_first_fill`, `median_seconds_to_first_fill`, `fill_count`, `traded_notional_reporting`, `buy_notional_reporting`, `sell_notional_reporting`, `net_flow_reporting`, `commission_reporting`, `mean_slippage_vs_close`, `venues_used`, `instruments_traded`, `fill_rate`, `fills_per_filled_order`

</details>

#### `agg_data_quality`

**Grain:** one row per model_name, activity_date, reject_reason  
**Type:** `aggregate`  
**Materialization:** `table`

Quarantine summary: what the screening layer rejected, when, why, and at what rate. Turns "we drop bad rows" from a claim into an observable, and feeds both the dashboard's data quality page and the Slack notifier. Grain: one row per model, activity date and reject reason.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `model_name` | `VARCHAR` | `internal` | - | `-` | Which screened model the rejection came from. |
| `activity_date` | `DATE` | `internal` | - | `-` | Business date of the rejected rows. |
| `reject_reason` | `VARCHAR` | `internal` | - | `-` | The specific check that failed, or 'none' for the clean-row rows that provide the denominator. |
| `overall_reject_rate` | `DECIMAL(9,6)` | `internal` | - | `-` | Rejected rows / total rows for that model and day. The measure the quality gate is threshold-tested against. |

<details><summary>5 derived columns inheriting the layer default (`internal`)</summary>

`total_rows`, `total_rejected_rows`, `rejected_rows`, `affected_quantity`, `reject_rate`

</details>

#### `dim_account`

**Grain:** one row per account_id  
**Type:** `dimension`  
**Materialization:** `table`

Account dimension, Type 1 -- nothing on an account changes in a way that needs history. Carries lifecycle attributes and lifetime activity summary. Grain: one row per account_id.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `account_key` | `VARCHAR` | `internal` | - | `-` | Surrogate primary key. |
| `account_id` | `VARCHAR` | `internal` | - | `-` | Natural key. |
| `customer_id` | `VARCHAR` | `internal` | - | `-` | Owning customer, as a natural key rather than a customer_key: the owner does not change, so pinning it to one SCD2 version would be arbitrary. |
| `account_type` | `VARCHAR` | `internal` | - | `-` | cash, margin or retirement. |
| `account_status` | `VARCHAR` | `internal` | - | `-` | open or closed, derived from closed_at. |
| `has_ever_traded` | `BOOLEAN` | `internal` | - | `-` | True if any valid fill exists for the account. |
| `days_to_first_trade` | `BIGINT` | `internal` | - | `-` | Days from opening to first fill. NULL if never traded, which is the honest answer -- zero would imply they traded on day one. |

<details><summary>13 derived columns inheriting the layer default (`internal`)</summary>

`base_currency`, `margin_limit`, `opened_at`, `opened_date`, `closed_at`, `closed_date`, `is_open`, `is_margin_enabled`, `opened_month`, `account_age_days`, `first_trade_date`, `latest_trade_date`, `lifetime_fill_count`

</details>

#### `dim_customer` **contains PII**

**Grain:** one row per customer_id per valid_from  
**Type:** `dimension_scd2`  
**Materialization:** `table`

Customer dimension, Type 2. One row per customer per version of their attributes; facts resolve to the version current when the event happened. Grain: one row per customer_id per valid_from. The most sensitive model in the warehouse. Read alongside governance/policy.yml and the generated 40_secure views -- nothing here is masked, and direct access to this model is what the secure layer exists to avoid.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `customer_key` | `VARCHAR` | `internal` | - | `-` | Surrogate primary key. Hash of (customer_id, valid_from). This is what facts carry. |
| `customer_id` | `VARCHAR` | `internal` | yes (pseudonymous_id) | `none` | Natural key of the customer, stable across all versions. |
| `version_number` | `BIGINT` | `internal` | - | `-` | 1-based sequence of this version within the customer. |
| `valid_from` | `DATE` | `internal` | - | `-` | First date this version applied. Inclusive. |
| `valid_to` | `TIMESTAMP` | `internal` | - | `-` | Last date this version applied. Inclusive -- 9999-12-31 while current. Inclusive because BETWEEN is what analysts write. |
| `is_current` | `BOOLEAN` | `internal` | - | `-` | True for the version in force now. Exactly one per customer. |
| `first_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Given name. |
| `last_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Family name. |
| `full_name` | `VARCHAR` | `confidential` | yes (name) | `redact` | Display name. |
| `email` | `VARCHAR` | `restricted` | yes (email) | `hash` | Contact email as at this version. |
| `phone_number` | `VARCHAR` | `restricted` | yes (phone) | `partial` | Contact number as at this version. |
| `national_id` | `VARCHAR` | `restricted` | yes (government_id) | `redact` | Government identifier. Highest-risk column in the warehouse. |
| `date_of_birth` | `DATE` | `restricted` | yes (date_of_birth) | `generalize` | Date of birth. |
| `street_address` | `VARCHAR` | `restricted` | yes (address) | `redact` | Residential street address as at this version. |
| `city` | `VARCHAR` | `confidential` | yes (address) | `none` | Residential city. |
| `postcode` | `VARCHAR` | `confidential` | yes (address) | `generalize` | Residential postcode. |
| `country_code` | `VARCHAR` | `internal` | - | `-` | ISO 3166-1 alpha-2 country of residence. |
| `kyc_status` | `VARCHAR` | `confidential` | - | `-` | KYC state as at this version. |
| `risk_rating` | `VARCHAR` | `confidential` | - | `-` | Compliance risk band as at this version. |
| `customer_tier` | `VARCHAR` | `internal` | - | `-` | Commercial tier as at this version. |
| `marketing_opt_in` | `BOOLEAN` | `confidential` | - | `-` | Marketing consent as at this version. |
| `age_years` | `BIGINT` | `confidential` | yes (date_of_birth) | `redact` | Exact age at valid_from, not today -- see the model header. Prefer age_band: an exact age combined with a postcode narrows a population fast. |
| `age_band` | `VARCHAR` | `internal` | - | `-` | Bucketed age at valid_from. The column analysts should use: it carries the demographic signal without the identifier. |
| `tenure_days_at_version` | `BIGINT` | `internal` | - | `-` | Days between signup and this version opening. |
| `observed_at_extract_date` | `DATE` | `internal` | - | `-` | The extract this version was first seen in. Provenance, for tracing a version back to the file it came from. |
| `attribute_hash` | `VARCHAR` | `internal` | - | `-` | Hash of the tracked attributes. The change-detection mechanism; kept for debugging why a version boundary exists. |
| `signup_date` | `DATE` | `internal` | - | `-` | Date the customer record was created. |
| `signup_month` | `DATE` | `internal` | - | `-` | Month the customer signed up, for cohort analysis. |
| `is_kyc_verified` | `BOOLEAN` | `internal` | - | `-` | Convenience flag for kyc_status = 'verified'. |
| `created_at` | `TIMESTAMP` | `internal` | - | `-` | Customer record creation timestamp. |
| `updated_at` | `TIMESTAMP` | `internal` | - | `-` | Most recent source change as at this version. |

#### `dim_date`

**Grain:** one row per date_day  
**Type:** `dimension`  
**Materialization:** `table`

Calendar dimension spanning every date observed anywhere in the warehouse. The trading-day flag is derived from the price feed rather than a hardcoded holiday list. Grain: one row per calendar date.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `date_day` | `DATE` | `public` | - | `-` | Primary key. The calendar date. |
| `date_key` | `INTEGER` | `public` | - | `-` | Integer YYYYMMDD form, provided for convention. The facts join on date_day -- see the model header for why. |
| `is_trading_day` | `BOOLEAN` | `public` | - | `-` | True if any non-crypto instrument was priced on this date. |
| `fiscal_year` | `BIGINT` | `public` | - | `-` | Australian fiscal year (July to June) this date falls in. |

<details><summary>16 derived columns inheriting the layer default (`public`)</summary>

`day_of_week`, `day_name`, `day_of_year`, `is_weekday`, `week_start_date`, `week_of_year`, `month_start_date`, `month_number`, `month_name`, `year_month`, `is_month_end`, `is_month_start`, `quarter_number`, `quarter_name`, `calendar_year`, `days_ago`

</details>

#### `dim_instrument`

**Grain:** one row per instrument_id  
**Type:** `dimension_conformed`  
**Materialization:** `table`

Instrument dimension, Type 1. The conformed dimension of this warehouse. Latest price attributes are denormalised on for convenience. Grain: one row per instrument_id.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `instrument_key` | `VARCHAR` | `public` | - | `-` | Surrogate primary key. |
| `instrument_id` | `VARCHAR` | `public` | - | `-` | Natural key. |
| `symbol` | `VARCHAR` | `public` | - | `-` | Exchange ticker. |
| `asset_class` | `VARCHAR` | `public` | - | `-` | equity, etf or crypto. |
| `latest_close_price` | `DECIMAL(18,4)` | `public` | - | `-` | Most recent close. Denormalised for the dashboard. |

<details><summary>16 derived columns inheriting the layer default (`public`)</summary>

`instrument_name`, `exchange`, `sector`, `listing_currency`, `dividend_yield`, `is_active`, `listed_date`, `trades_every_day`, `is_reporting_currency`, `pays_dividend`, `latest_price_date`, `latest_daily_return`, `first_price_date`, `all_time_low_price`, `all_time_high_price`, `average_daily_volume`

</details>

#### `fct_account_daily`

**Grain:** one row per account_id, snapshot_date  
**Type:** `fact_periodic_snapshot`  
**Materialization:** `table`

Periodic snapshot fact. One row per account per day it was open, within the same trailing window as fct_positions_daily. Carries the account's cash, holdings, equity and P&L decomposition. Grain: one row per account_id, snapshot_date.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `snapshot_date` | `DATE` | `internal` | - | `-` | Day being observed. |
| `cash_balance_reporting` | `DECIMAL(18,4)` | `confidential` | - | `-` | Cash at end of day, accumulated from account inception. May be negative on margin accounts by design. |
| `account_equity_reporting` | `DECIMAL(18,4)` | `confidential` | - | `-` | Cash plus market value of holdings. |
| `unrealised_gain_reporting` | `DECIMAL(18,4)` | `confidential` | - | `-` | Mark-to-market gain on positions still held. |
| `realised_gain_reporting` | `DECIMAL(18,4)` | `confidential` | - | `-` | Profit or loss on positions that have been closed out. Derived as capital deployed into holdings that is no longer represented by an open position. |

<details><summary>25 derived columns inheriting the layer default (`confidential`)</summary>

`account_id`, `account_key`, `customer_id`, `account_type`, `base_currency`, `account_status`, `holdings_value_reporting`, `net_invested_reporting`, `net_funded_reporting`, `cumulative_deposits_reporting`, `cumulative_withdrawals_reporting`, `cumulative_fees_reporting`, `cumulative_income_reporting`, `cumulative_commission_reporting`, `net_cash_change`, `deposits_reporting`, `withdrawals_reporting`, `fees_reporting`, `income_reporting`, `commission_reporting`, `fill_count`, `traded_notional_reporting`, `open_position_count`, `distinct_instruments_held`, `traded_today`

</details>

#### `fct_executions`

**Grain:** one row per execution_id  
**Type:** `fact_transaction`  
**Materialization:** `table`

Transaction fact. One row per fill -- the atomic grain of the warehouse. Every measure is fully additive. Resolves the customer key as-of the execution date via ASOF JOIN. Grain: one row per execution_id.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `execution_id` | `VARCHAR` | `internal` | - | `-` | Degenerate dimension. Primary key, for traceability. |
| `account_key` | `VARCHAR` | `internal` | - | `-` | Account dimension key. |
| `customer_key` | `VARCHAR` | `internal` | - | `-` | Customer dimension version current at the execution date. Not the customer's current version. |
| `instrument_key` | `VARCHAR` | `internal` | - | `-` | Instrument dimension key. |
| `date_day` | `DATE` | `internal` | - | `-` | Date the fill occurred. Joins to dim_date. |
| `execution_quantity` | `DECIMAL(28,8)` | `internal` | - | `-` | Units filled. Additive. |
| `signed_quantity` | `DECIMAL(28,8)` | `internal` | - | `-` | Quantity signed by side -- positive for buys, negative for sells. What makes the position snapshot a running SUM. |
| `gross_notional_reporting` | `DECIMAL(18,4)` | `internal` | - | `-` | quantity x price in the reporting currency, before commission. |
| `signed_cash_flow_reporting` | `DECIMAL(18,4)` | `internal` | - | `-` | Cash effect of the fill in the reporting currency: negative for buys (including commission), positive for sells (net of it). |
| `fx_rate_to_reporting` | `DECIMAL(18,8)` | `internal` | - | `-` | Rate applied to convert to the reporting currency. |
| `slippage_vs_close` | `DECIMAL(18,4)` | `internal` | - | `-` | Execution price versus the session close, signed so negative is favourable to the customer. NULL when the instrument had no price that day. |

<details><summary>22 derived columns inheriting the layer default (`internal`)</summary>

`order_id`, `account_id`, `customer_id`, `instrument_id`, `symbol`, `side`, `order_type`, `channel`, `account_type`, `venue`, `asset_class`, `sector`, `execution_currency`, `execution_price`, `gross_notional`, `commission`, `commission_reporting`, `commission_rate`, `order_placed_at`, `executed_at`, `seconds_from_order_to_fill`, `execution_hour`

</details>

#### `fct_orders`

**Grain:** one row per order_id  
**Type:** `fact_accumulating_snapshot`  
**Materialization:** `table`

Accumulating snapshot fact. One row per order, carrying lifecycle milestones and the lags between them. Cancelled and rejected orders are retained with zero fills. Grain: one row per order_id.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `order_id` | `VARCHAR` | `internal` | - | `-` | Degenerate dimension. Primary key. |
| `customer_key` | `VARCHAR` | `internal` | - | `-` | Customer version current when the order was placed. |
| `date_day` | `DATE` | `internal` | - | `-` | Session date the order belongs to. |
| `order_status` | `VARCHAR` | `internal` | - | `-` | Terminal state. |
| `seconds_to_first_fill` | `BIGINT` | `internal` | - | `-` | Milestone lag: order placed to first fill. NULL for orders that never filled -- the reason this grain is an accumulating snapshot. |
| `fill_rate` | `DECIMAL(9,6)` | `internal` | - | `-` | filled_quantity / order_quantity. NULL rather than zero when the order quantity is zero, which cannot happen but should not silently become a number if it did. |

<details><summary>35 derived columns inheriting the layer default (`internal`)</summary>

`account_key`, `instrument_key`, `account_id`, `customer_id`, `instrument_id`, `symbol`, `side`, `order_type`, `time_in_force`, `channel`, `account_type`, `asset_class`, `sector`, `placed_at`, `first_filled_at`, `last_filled_at`, `resolved_at`, `order_quantity`, `filled_quantity`, `unfilled_quantity`, `fill_count`, `venue_count`, `filled_notional_reporting`, `commission_reporting`, `average_fill_price`, `primary_venue`, `limit_price`, `seconds_to_last_fill`, `seconds_to_resolution`, `is_filled_any`, `is_fully_filled`, `is_cancelled`, `is_rejected`, `placed_hour`, `price_improvement_vs_limit`

</details>

#### `fct_positions_daily`

**Grain:** one row per account_id, instrument_id, snapshot_date  
**Type:** `fact_periodic_snapshot`  
**Materialization:** `incremental`

Periodic snapshot fact. One row per account, instrument and day on which a position was held, within a trailing window. Incremental. Grain: one row per account_id, instrument_id, snapshot_date. Only non-zero holdings exist as rows -- see the model header for why the naive accounts x instruments x days spine is not viable.

| Column | Type | Classification | PII | Masking | Description |
|---|---|---|---|---|---|
| `snapshot_date` | `DATE` | `internal` | - | `-` | The day this position is being observed on. |
| `position_quantity` | `DECIMAL(38,8)` | `internal` | - | `-` | Units held at end of day. Semi-additive -- never sum over dates. |
| `is_stale_price` | `BOOLEAN` | `internal` | - | `-` | True when the mark price comes from an earlier session -- weekends, holidays, and suspended instruments. Roughly 28% of rows, and the reason the price join is an ASOF JOIN. |
| `market_value_reporting` | `DECIMAL(18,4)` | `confidential` | - | `-` | Position marked to market in the reporting currency. Semi-additive: additive across accounts and instruments, meaningless summed over dates. |
| `net_invested_reporting` | `DECIMAL(18,4)` | `confidential` | - | `-` | Cumulative purchase cost less sale proceeds for this position. Net capital deployed, deliberately NOT a weighted-average cost basis -- see the model header. |
| `unrealised_gain_reporting` | `DECIMAL(18,4)` | `confidential` | - | `-` | Market value less net invested capital. |

<details><summary>13 derived columns inheriting the layer default (`confidential`)</summary>

`account_id`, `instrument_id`, `account_key`, `instrument_key`, `customer_id`, `symbol`, `asset_class`, `sector`, `mark_price`, `mark_price_date`, `fx_rate_to_reporting`, `cumulative_commission_reporting`, `days_since_last_trade`

</details>

