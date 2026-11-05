"""
ClientPulse Compute Engine
==========================
Deterministic report maths. Claude describes a dataset (a "recipe": date column,
metrics and how to aggregate them, which charts to show); this module filters the
raw rows by period and computes every number itself, so each figure on a report
can be traced to a formula and the source rows. No AI is involved here.
"""

import io
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

AGGS = ("sum", "mean", "weighted_mean", "ratio", "count", "min", "max", "last")
FORMATS = ("number", "currency", "percent", "decimal")
GRANULARITIES = ("day", "week", "month")
CORE_FIELDS = ("impressions", "clicks", "leads", "spend")
MAX_CSV_BYTES = 5 * 1024 * 1024


class RecipeError(ValueError):
    """The recipe does not fit the dataset (unknown column, bad aggregation, empty period...)."""


# ------------------------------------------------------------------------------
# Loading and profiling
# ------------------------------------------------------------------------------
def load_csv(csv_text: str) -> pd.DataFrame:
    if len(csv_text.encode("utf-8")) > MAX_CSV_BYTES:
        raise RecipeError("CSV is larger than 5 MB.")
    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as e:
        raise RecipeError(f"Could not read CSV: {e}")
    if df.empty or len(df.columns) < 2:
        raise RecipeError("CSV needs a header row, at least two columns, and at least one data row.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _looks_like_date(series: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(series):
        return False
    parsed = pd.to_datetime(series.dropna().astype(str).head(50), errors="coerce", format="mixed")
    return len(parsed) > 0 and parsed.notna().mean() > 0.9


def profile(df: pd.DataFrame) -> Dict[str, Any]:
    """Column-by-column description Claude uses to write a recipe (types, ranges, top values, samples)."""
    columns = []
    for name in df.columns:
        s = df[name]
        info: Dict[str, Any] = {"name": name, "non_null": int(s.notna().sum())}
        if pd.api.types.is_numeric_dtype(s):
            info.update(type="numeric", min=float(s.min()), max=float(s.max()), sum=float(s.sum()))
        elif _looks_like_date(s):
            parsed = pd.to_datetime(s, errors="coerce", format="mixed")
            info.update(type="date", min=str(parsed.min().date()), max=str(parsed.max().date()),
                        distinct=int(parsed.nunique()))
        else:
            counts = s.astype(str).value_counts()
            info.update(type="text", distinct=int(counts.size), top_values=counts.head(12).index.tolist())
        columns.append(info)
    return {"rows": int(len(df)), "columns": columns,
            "sample_rows": df.head(5).astype(object).where(df.head(5).notna(), None).to_dict("records")}


# ------------------------------------------------------------------------------
# Recipe validation
# ------------------------------------------------------------------------------
def _require_column(df: pd.DataFrame, column: Any, where: str) -> str:
    if not column or column not in df.columns:
        raise RecipeError(f"{where}: column '{column}' is not in the dataset. Columns: {', '.join(df.columns)}.")
    return column


def _numeric(df: pd.DataFrame, column: str, where: str) -> pd.Series:
    values = pd.to_numeric(df[column], errors="coerce")
    if values.notna().sum() == 0 and len(df):
        raise RecipeError(f"{where}: column '{column}' has no numeric values.")
    return values


def validate_recipe(df: pd.DataFrame, recipe: Dict[str, Any]) -> Dict[str, Any]:
    r = dict(recipe)
    r["date_column"] = _require_column(df, r.get("date_column"), "date_column")
    for key in ("period", "compare_period"):
        p = r.get(key)
        if key == "period" and not p:
            raise RecipeError("period {start, end} is required.")
        if p:
            try:
                start, end = pd.Timestamp(p["start"]), pd.Timestamp(p["end"])
            except Exception:
                raise RecipeError(f"{key} needs start and end dates (YYYY-MM-DD).")
            if end < start:
                raise RecipeError(f"{key}: end is before start.")

    metrics = r.get("metrics") or []
    if not metrics:
        raise RecipeError("Define at least one metric.")
    keys = set()
    for m in metrics:
        key = str(m.get("key") or "").strip()
        if not key or key in keys:
            raise RecipeError(f"Metric keys must be unique and non-empty (problem with '{key}').")
        keys.add(key)
        agg = m.get("agg", "sum")
        if agg not in AGGS:
            raise RecipeError(f"Metric '{key}': agg must be one of {', '.join(AGGS)}.")
        if m.get("format", "number") not in FORMATS:
            raise RecipeError(f"Metric '{key}': format must be one of {', '.join(FORMATS)}.")
        if agg in ("sum", "mean", "weighted_mean", "min", "max", "last"):
            _numeric(df, _require_column(df, m.get("column"), f"Metric '{key}'"), f"Metric '{key}'")
        if agg == "weighted_mean":
            _numeric(df, _require_column(df, m.get("weight"), f"Metric '{key}' weight"), f"Metric '{key}' weight")
    for m in metrics:
        if m.get("agg") == "ratio":
            for part in ("numerator", "denominator"):
                if m.get(part) not in keys or m.get(part) == m["key"]:
                    raise RecipeError(f"Metric '{m['key']}': {part} must be the key of another metric.")

    def check_metric(key, where):
        if key not in keys:
            raise RecipeError(f"{where}: '{key}' is not a defined metric key.")

    for k in r.get("kpis") or []:
        check_metric(k, "kpis")
    if r.get("trend"):
        if r["trend"].get("granularity", "week") not in GRANULARITIES:
            raise RecipeError(f"trend.granularity must be one of {', '.join(GRANULARITIES)}.")
        if not r["trend"].get("metrics"):
            raise RecipeError("trend.metrics needs 1-3 metric keys.")
        for k in r["trend"]["metrics"][:3]:
            check_metric(k, "trend")
    if r.get("split"):
        _require_column(df, r["split"].get("dimension"), "split.dimension")
        check_metric(r["split"].get("metric"), "split")
    for i, rk in enumerate(r.get("rankings") or []):
        _require_column(df, rk.get("dimension"), f"rankings[{i}].dimension")
        check_metric(rk.get("metric"), f"rankings[{i}]")
    if r.get("table"):
        _require_column(df, r["table"].get("dimension"), "table.dimension")
        for k in r["table"].get("metrics") or []:
            check_metric(k, "table")
    return r


# ------------------------------------------------------------------------------
# Aggregation
# ------------------------------------------------------------------------------
def _ordered(metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Base metrics first, ratios after (ratios depend on base values)."""
    return [m for m in metrics if m.get("agg") != "ratio"] + [m for m in metrics if m.get("agg") == "ratio"]


def compute_metrics(rows: pd.DataFrame, metrics: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for m in _ordered(metrics):
        agg, key = m.get("agg", "sum"), m["key"]
        if agg == "ratio":
            num, den = out.get(m["numerator"]), out.get(m["denominator"])
            out[key] = (num / den * float(m.get("scale", 1))) if num is not None and den else None
            continue
        if agg == "count":
            out[key] = float(len(rows))
            continue
        values = pd.to_numeric(rows[m["column"]], errors="coerce")
        if values.notna().sum() == 0:
            out[key] = None
        elif agg == "sum":
            out[key] = float(values.sum())
        elif agg == "mean":
            out[key] = float(values.mean())
        elif agg == "min":
            out[key] = float(values.min())
        elif agg == "max":
            out[key] = float(values.max())
        elif agg == "last":
            out[key] = float(values.dropna().iloc[-1])
        elif agg == "weighted_mean":
            weights = pd.to_numeric(rows[m["weight"]], errors="coerce")
            mask = values.notna() & weights.notna()
            total_w = float(weights[mask].sum())
            out[key] = float((values[mask] * weights[mask]).sum() / total_w) if total_w else None
    return out


def formula(m: Dict[str, Any], labels: Dict[str, str]) -> str:
    agg = m.get("agg", "sum")
    if agg == "ratio":
        scale = float(m.get("scale", 1))
        tail = f" × {scale:g}" if scale != 1 else ""
        return f"{labels.get(m['numerator'], m['numerator'])} ÷ {labels.get(m['denominator'], m['denominator'])}{tail}"
    if agg == "count":
        return "COUNT(rows)"
    if agg == "weighted_mean":
        return f"Σ({m['column']} × {m['weight']}) ÷ Σ({m['weight']})"
    return f"{agg.upper()}({m['column']})"


def _in_period(dates: pd.Series, period: Dict[str, str]) -> pd.Series:
    return (dates >= pd.Timestamp(period["start"])) & (dates <= pd.Timestamp(period["end"]))


def _bucket(dates: pd.Series, granularity: str) -> pd.Series:
    if granularity == "day":
        return dates.dt.strftime("%Y-%m-%d")
    if granularity == "month":
        return dates.dt.strftime("%Y-%m")
    return (dates - pd.to_timedelta(dates.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")


def build(df: pd.DataFrame, recipe: Dict[str, Any], dataset_name: str = "dataset") -> Dict[str, Any]:
    """
    Compute a report from raw rows. Returns:
      spec:   dashboard spec (custom KPIs, trend, split, rankings, table) for the dashboard/PDF
      core:   impressions/clicks/leads/spend (+prev_) when the recipe defines those keys
      audit:  rows used, periods, and the formula behind every metric
    """
    r = validate_recipe(df, recipe)
    metrics = r["metrics"]
    labels = {m["key"]: m.get("label") or m["key"] for m in metrics}
    by_key = {m["key"]: m for m in metrics}

    data = df.copy()
    data["_date"] = pd.to_datetime(data[r["date_column"]].astype(str), errors="coerce", format="mixed")
    for flt in r.get("filters") or []:
        col = _require_column(data, flt.get("column"), "filters")
        data = data[data[col].astype(str).isin([str(v) for v in flt.get("values") or []])]

    cur_rows = data[_in_period(data["_date"], r["period"])]
    if cur_rows.empty:
        raise RecipeError(f"No rows fall inside the period {r['period']['start']} to {r['period']['end']}.")
    prev_rows = data[_in_period(data["_date"], r["compare_period"])] if r.get("compare_period") else data.iloc[0:0]

    cur = compute_metrics(cur_rows, metrics)
    prev = compute_metrics(prev_rows, metrics) if not prev_rows.empty else {}

    def fmt_of(key):
        return by_key[key].get("format", "number")

    def better(key):
        return by_key[key].get("higher_is_better", True)

    kpi_keys = r.get("kpis") or [m["key"] for m in metrics][:8]
    spec: Dict[str, Any] = {
        "currency": r.get("currency") or "$",
        "kpis": [{"label": labels[k], "value": cur[k], "prev": prev.get(k), "format": fmt_of(k),
                  "higher_is_better": better(k)} for k in kpi_keys[:8] if cur.get(k) is not None],
        "rankings": [],
    }

    if r.get("trend"):
        t = r["trend"]
        gran = t.get("granularity", "week")
        scope = t.get("range") or ("all" if gran == "month" else "current")
        rows = cur_rows if scope == "current" else data[data["_date"] <= pd.Timestamp(r["period"]["end"])]
        rows = rows.assign(_bucket=_bucket(rows["_date"], gran))
        if scope == "current" and gran == "week":
            # A week that starts before the period is labelled with the period's first day
            start = pd.Timestamp(r["period"]["start"]).strftime("%Y-%m-%d")
            rows["_bucket"] = rows["_bucket"].where(rows["_bucket"] >= start, start)
        buckets = sorted(b for b in rows["_bucket"].dropna().unique())
        per_bucket = {b: compute_metrics(rows[rows["_bucket"] == b], metrics) for b in buckets}
        series = []
        for i, k in enumerate(t["metrics"][:3]):
            series.append({"name": labels[k], "values": [per_bucket[b].get(k) or 0 for b in buckets],
                           "format": fmt_of(k), "axis": "right" if i == 1 and fmt_of(k) != fmt_of(t["metrics"][0]) else "left",
                           "higher_is_better": better(k)})
        spec["trend"] = {"title": t.get("title") or " & ".join(labels[k] for k in t["metrics"][:3]) + f" by {gran}",
                         "x": buckets, "series": series}

    def grouped(dimension: str) -> List[Tuple[str, Dict[str, Optional[float]]]]:
        return [(str(name), compute_metrics(g, metrics)) for name, g in cur_rows.groupby(dimension, sort=False)]

    if r.get("split"):
        sp = r["split"]
        groups = grouped(sp["dimension"])
        spec["split"] = {"title": sp.get("title") or f"{labels[sp['metric']]} by {sp['dimension']}",
                         "labels": [g for g, _ in groups], "values": [vals.get(sp["metric"]) or 0 for _, vals in groups],
                         "format": fmt_of(sp["metric"])}

    for rk in (r.get("rankings") or [])[:2]:
        groups = [(g, vals.get(rk["metric"])) for g, vals in grouped(rk["dimension"])]
        groups = [(g, v) for g, v in groups if v is not None]
        spec["rankings"].append({"title": rk.get("title") or f"{labels[rk['metric']]} by {rk['dimension']}",
                                 "labels": [g for g, _ in groups], "values": [v for _, v in groups],
                                 "format": fmt_of(rk["metric"]), "higher_is_better": better(rk["metric"])})

    if r.get("table"):
        tb = r["table"]
        keys = tb.get("metrics") or kpi_keys
        verdicts = r.get("verdicts") or {}
        rows_out = []
        for name, vals in grouped(tb["dimension"]):
            v = verdicts.get(name) or {}
            rows_out.append({"name": name, "values": {k: vals.get(k) for k in keys},
                             "verdict": v.get("verdict"), "note": v.get("note") or ""})
        sort_key = tb.get("sort_by")
        if sort_key in keys:
            asc = better(sort_key) is False
            rows_out.sort(key=lambda row: (row["values"].get(sort_key) is None,
                                           (row["values"].get(sort_key) or 0) * (1 if asc else -1)))
        spec["table"] = {"title": tb.get("title") or f"Performance by {tb['dimension']}",
                         "columns": [{"key": k, "label": labels[k], "format": fmt_of(k)} for k in keys],
                         "rows": rows_out}

    core = {}
    for field in CORE_FIELDS:
        if field in cur and cur[field] is not None:
            core[field] = cur[field]
            if prev.get(field) is not None:
                core[f"prev_{field}"] = prev[field]

    audit = {
        "dataset": dataset_name,
        "rows_total": int(len(df)),
        "rows_current": int(len(cur_rows)),
        "rows_previous": int(len(prev_rows)),
        "period": r["period"],
        "compare_period": r.get("compare_period"),
        "metrics": [{"key": m["key"], "label": labels[m["key"]], "formula": formula(m, labels),
                     "current": cur.get(m["key"]), "previous": prev.get(m["key"])} for m in metrics],
    }
    return {"spec": spec, "core": core, "audit": audit, "recipe": r}


def period_rows(df: pd.DataFrame, recipe: Dict[str, Any], which: str = "period") -> pd.DataFrame:
    """The exact source rows behind a report period (for the 'view source rows' audit)."""
    data = df.copy()
    dates = pd.to_datetime(data[recipe["date_column"]].astype(str), errors="coerce", format="mixed")
    for flt in recipe.get("filters") or []:
        mask = data[flt["column"]].astype(str).isin([str(v) for v in flt.get("values") or []])
        data, dates = data[mask], dates[mask]
    p = recipe.get(which)
    return data[_in_period(dates, p)] if p else data.iloc[0:0]
