{#
  Print a one-screen summary at the end of every run.

  Machine-readable reporting is left to `target/run_results.json`, which the
  Slack notifier parses -- re-implementing that in Jinja would be a worse
  version of a file dbt already writes. This macro exists for the human staring
  at a terminal, and for the CI log where scrolling back through 60 model lines
  to find the one failure is the actual problem.
#}
{% macro log_run_summary(results) -%}
  {%- if not execute or results is none -%}
    {{ return('') }}
  {%- endif -%}

  {%- set models = results | selectattr("node.resource_type", "equalto", "model") | list -%}
  {%- set tests = results | selectattr("node.resource_type", "equalto", "test") | list -%}
  {%- set failed = results | selectattr("status", "in", ["error", "fail"]) | list -%}
  {%- set warned = results | selectattr("status", "equalto", "warn") | list -%}

  {{ log("", info=True) }}
  {{ log("tradeflow run summary -- target=" ~ target.name ~ " threads=" ~ target.threads, info=True) }}
  {{ log("  models       " ~ models | length, info=True) }}
  {{ log("  tests        " ~ tests | length, info=True) }}
  {{ log("  warnings     " ~ warned | length, info=True) }}
  {{ log("  failures     " ~ failed | length, info=True) }}

  {%- if warned | length > 0 %}
  {{ log("", info=True) }}
  {{ log("  warned:", info=True) }}
    {%- for result in warned %}
  {{ log("    ! " ~ result.node.name, info=True) }}
    {%- endfor %}
  {%- endif %}

  {%- if failed | length > 0 %}
  {{ log("", info=True) }}
  {{ log("  failed:", info=True) }}
    {%- for result in failed %}
  {{ log("    x " ~ result.node.name ~ "  (" ~ result.status ~ ")", info=True) }}
    {%- endfor %}
  {%- endif %}
  {{ log("", info=True) }}
{%- endmacro %}
