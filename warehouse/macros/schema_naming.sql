{#
  Use the layer schema verbatim instead of dbt's default
  `<target_schema>_<custom_schema>` concatenation.

  The default exists to stop developers colliding in a shared cloud warehouse.
  Here every developer has their own DuckDB file, so the concatenation buys
  nothing and costs a great deal of legibility: `marts.fct_executions` reads
  like a warehouse, `dev_marts.fct_executions` reads like a workaround. The
  dashboard and the generated catalog both address tables by these names.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- else -%}
    {{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
