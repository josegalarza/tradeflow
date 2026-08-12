{#
  Masking primitives, referenced by the generated 40_secure views.

  The transformation lives here rather than being inlined by the generator so
  that it is defined once, can be unit-tested (see tests/unit/), and can be
  changed without regenerating every view. The generator decides *which* mask a
  column gets; these macros decide what each mask does.
#}


{% macro mask_hash(column_name) -%}
  {#-
    Salted MD5. Preserves equality -- distinct counts and cross-system joins keep
    working -- while destroying the value.

    The salt is not decoration. An unsalted hash of an email address is
    reversible by anyone with a wordlist, which is every attacker; the hash would
    provide the appearance of protection and none of the substance. It comes from
    the environment so it is not in version control, and it must be stable, or
    every hashed identifier changes on the next run and every cohort breaks.
  -#}
  MD5(CAST({{ column_name }} AS VARCHAR) || '{{ masking_salt() }}')
{%- endmacro %}


{% macro masking_salt() -%}
  {#-
    Fails loudly in production and falls back to a documented placeholder in dev.
    A silent default in production would make every hash across the warehouse
    trivially reversible while looking exactly like a working one.
  -#}
  {%- if target.name in ['prod', 'production'] -%}
    {{ env_var('TRADEFLOW_MASKING_SALT') }}
  {%- else -%}
    {{ env_var('TRADEFLOW_MASKING_SALT', 'tradeflow-dev-salt-not-for-production') }}
  {%- endif -%}
{%- endmacro %}


{% macro mask_partial_email(column_name) -%}
  {#- j***@example.com: enough to confirm an address, not enough to use it. -#}
  CASE
    WHEN {{ column_name }} IS NULL THEN NULL
    WHEN POSITION('@' IN {{ column_name }}) < 2 THEN '***'
    ELSE LEFT({{ column_name }}, 1) || '***'
      || SUBSTRING({{ column_name }} FROM POSITION('@' IN {{ column_name }}))
  END
{%- endmacro %}


{% macro mask_partial_phone(column_name) -%}
  {#- Last three digits only. Standard practice for verifying a caller. -#}
  CASE
    WHEN {{ column_name }} IS NULL THEN NULL
    WHEN LENGTH({{ column_name }}) <= 3 THEN '***'
    ELSE '*** *** ' || RIGHT({{ column_name }}, 3)
  END
{%- endmacro %}


{% macro mask_partial_generic(column_name) -%}
  {#- First character, then stars. The conservative fallback. -#}
  CASE
    WHEN {{ column_name }} IS NULL THEN NULL
    WHEN LENGTH(CAST({{ column_name }} AS VARCHAR)) <= 1 THEN '*'
    ELSE LEFT(CAST({{ column_name }} AS VARCHAR), 1)
      || REPEAT('*', LENGTH(CAST({{ column_name }} AS VARCHAR)) - 1)
  END
{%- endmacro %}


{% macro mask_redact(column_name, data_type) -%}
  {#-
    A typed NULL, not a '[REDACTED]' string.

    The type matters: replacing a DATE with a string changes the view's schema,
    and anything downstream that expected a date now fails at query time instead
    of at build time. A typed NULL keeps the contract intact and makes the
    absence unambiguous.
  -#}
  CAST(NULL AS {{ data_type }})
{%- endmacro %}


{% macro mask_generalize_date(column_name) -%}
  {#-
    Date of birth to a decade band. A full date of birth combined with a
    postcode is close to a unique identifier for a person; the decade keeps every
    demographic cut anyone actually runs.
  -#}
  CASE
    WHEN {{ column_name }} IS NULL THEN NULL
    -- Integer division (//), not /. DuckDB's / is float division, so 1985 / 10
    -- is 198.5 and the band renders as '1985.0s' rather than '1980s'.
    ELSE CAST((YEAR({{ column_name }}) // 10) * 10 AS VARCHAR) || 's'
  END
{%- endmacro %}


{% macro mask_generalize_timestamp(column_name) -%}
  {#-
    Timestamp to month. A precise last-seen timestamp reveals daily routine --
    when someone wakes up, when they are at work -- which is behavioural profiling
    rather than analytics. Month preserves recency and cohort analysis.
  -#}
  CASE
    WHEN {{ column_name }} IS NULL THEN NULL
    ELSE STRFTIME({{ column_name }}, '%Y-%m')
  END
{%- endmacro %}


{% macro mask_generalize_postcode(column_name) -%}
  {#- Drop the last two characters: region survives, household does not. -#}
  CASE
    WHEN {{ column_name }} IS NULL THEN NULL
    WHEN LENGTH({{ column_name }}) <= 2 THEN '**'
    ELSE LEFT({{ column_name }}, LENGTH({{ column_name }}) - 2) || '**'
  END
{%- endmacro %}


{% macro mask_generalize_numeric(column_name) -%}
  {#-
    Order-of-magnitude bucket for numeric values. Keeps the shape of a
    distribution while removing the ability to single out an individual by an
    unusual exact figure.
  -#}
  CASE
    WHEN {{ column_name }} IS NULL THEN NULL
    WHEN {{ column_name }} = 0 THEN '0'
    ELSE '1e' || CAST(
      FLOOR(LOG10(ABS(CAST({{ column_name }} AS DOUBLE)))) AS VARCHAR
    )
  END
{%- endmacro %}
