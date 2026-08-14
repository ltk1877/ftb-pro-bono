#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create charts for a ZIP/ZCTA food insecurity forecast CSV.

Usage:
    python scripts/create_food_insecurity_forecast_charts.py \
        --input forecasts/fl_food_insecurity_forecast_2027.csv \
        --output-dir reports/figures/fl_food_insecurity_forecast_2027

The script writes PNG charts, summary CSVs, and an HTML index page that can be
opened in a browser or shared with non-technical reviewers.
"""
import argparse
import html
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "figures" / "fl_food_insecurity_forecast_2027"

RATE_COL = "predicted_food_insecurity_rate"
POP_COL = "population"
COUNTY_COL = "County, State"
ZCTA_COL = "zcta"
FOOD_BANK_COL = "Food Bank 1"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="Forecast CSV path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help=f"Directory for charts and summaries. Default: {DEFAULT_OUTPUT_DIR.relative_to(PROJECT_ROOT)}")
    parser.add_argument("--top-n", type=int, default=25, help="Number of rows to show in ranked bar charts. Default: 25.")
    return parser.parse_args()


def require_columns(df, columns):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError("Missing required column(s): {}".format(", ".join(missing)))


def pct(value):
    if pd.isna(value):
        return ""
    return "{:.1%}".format(value)


def whole_number(value):
    if pd.isna(value):
        return ""
    return "{:,.0f}".format(value)


def style_axis(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", color="#d9dee7", linewidth=0.8, alpha=0.85)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=9, colors="#2e3440")


def save_horizontal_bar(df, label_col, value_col, title, xlabel, output_path, formatter, color="#2f6f8f"):
    plot_df = df.dropna(subset=[value_col]).copy()
    plot_df = plot_df.sort_values(value_col, ascending=True)
    if plot_df.empty:
        return None

    height = max(5.5, min(14, 0.34 * len(plot_df) + 1.6))
    fig, ax = plt.subplots(figsize=(10, height))
    ax.barh(plot_df[label_col], plot_df[value_col], color=color)
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color="#17202a")
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel("")
    style_axis(ax)

    max_value = plot_df[value_col].max()
    offset = max_value * 0.012 if max_value else 0.01
    for i, value in enumerate(plot_df[value_col]):
        ax.text(value + offset, i, formatter(value), va="center", fontsize=8.5, color="#17202a")

    ax.set_xlim(0, max_value * 1.16 if max_value else 1)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_histogram(df, output_path):
    rates = df[RATE_COL].dropna()
    if rates.empty:
        return None

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(rates, bins=24, color="#5a8f7b", edgecolor="white")
    ax.axvline(rates.mean(), color="#b94747", linewidth=2, label="Average")
    ax.axvline(rates.median(), color="#3f5f9f", linewidth=2, linestyle="--", label="Median")
    ax.set_title("Distribution of Predicted Food Insecurity Rates", loc="left", fontsize=14, fontweight="bold", color="#17202a")
    ax.set_xlabel("Predicted food insecurity rate")
    ax.set_ylabel("Number of ZIP/ZCTA rows")
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    style_axis(ax)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_scatter(df, output_path):
    plot_df = df.dropna(subset=[POP_COL, RATE_COL]).copy()
    plot_df = plot_df.loc[plot_df[POP_COL] > 0]
    if plot_df.empty:
        return None

    fig, ax = plt.subplots(figsize=(10, 6))
    poverty = plot_df["poverty_rate"] if "poverty_rate" in plot_df.columns else None
    scatter = ax.scatter(
        plot_df[POP_COL],
        plot_df[RATE_COL],
        c=poverty,
        cmap="YlOrRd" if poverty is not None else None,
        color=None if poverty is not None else "#2f6f8f",
        s=36,
        alpha=0.72,
        edgecolors="white",
        linewidths=0.3,
    )
    ax.set_xscale("log")
    ax.set_title("Predicted Rate Compared With ZIP/ZCTA Population", loc="left", fontsize=14, fontweight="bold", color="#17202a")
    ax.set_xlabel("Population, log scale")
    ax.set_ylabel("Predicted food insecurity rate")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    style_axis(ax)
    if poverty is not None:
        cbar = fig.colorbar(scatter, ax=ax)
        cbar.set_label("Poverty rate")
        cbar.ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_food_bank_boxplot(df, output_path):
    if FOOD_BANK_COL not in df.columns:
        return None
    groups = []
    labels = []
    for food_bank, group in df.dropna(subset=[RATE_COL]).groupby(FOOD_BANK_COL):
        rates = group[RATE_COL].dropna()
        if len(rates) >= 3:
            labels.append(str(food_bank))
            groups.append(rates)
    if not groups:
        return None

    medians = [float(np.median(values)) for values in groups]
    ordered = sorted(zip(medians, labels, groups), reverse=True)
    labels = [item[1] for item in ordered]
    groups = [item[2] for item in ordered]

    fig, ax = plt.subplots(figsize=(11, max(5.5, 0.46 * len(labels) + 1.5)))
    ax.boxplot(groups, vert=False, labels=labels, patch_artist=True, boxprops={"facecolor": "#d8c99b", "color": "#7c6f48"})
    ax.set_title("Predicted Rate Ranges by Food Bank", loc="left", fontsize=14, fontweight="bold", color="#17202a")
    ax.set_xlabel("Predicted food insecurity rate")
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    style_axis(ax)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_correlation_chart(df, output_path):
    numeric = df.select_dtypes(include=[np.number]).copy()
    drop_cols = {"row_id", "county_fips", "forecast_year", "source_year", ZCTA_COL}
    numeric = numeric.drop(columns=[col for col in drop_cols if col in numeric.columns], errors="ignore")
    if RATE_COL not in numeric.columns:
        return None

    correlations = numeric.corr()[RATE_COL].drop(labels=[RATE_COL], errors="ignore").dropna()
    correlations = correlations.reindex(correlations.abs().sort_values(ascending=False).head(12).index)
    if correlations.empty:
        return None

    chart_df = correlations.sort_values().reset_index()
    chart_df.columns = ["driver", "correlation"]
    colors = ["#b94747" if value > 0 else "#2f6f8f" for value in chart_df["correlation"]]

    fig, ax = plt.subplots(figsize=(10, 6.5))
    ax.barh(chart_df["driver"], chart_df["correlation"], color=colors)
    ax.axvline(0, color="#2e3440", linewidth=0.8)
    ax.set_title("Drivers Most Correlated With Predicted Rate", loc="left", fontsize=14, fontweight="bold", color="#17202a")
    ax.set_xlabel("Pearson correlation")
    ax.set_ylabel("")
    style_axis(ax)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def build_county_summary(df):
    work = df.dropna(subset=[RATE_COL, POP_COL]).copy()
    work["estimated_food_insecure_people"] = work[RATE_COL] * work[POP_COL]

    rows = []
    for county, group in work.groupby(COUNTY_COL):
        row = {
            COUNTY_COL: county,
            "zcta_rows": group[ZCTA_COL].nunique(),
            "total_population": group[POP_COL].sum(),
            "estimated_food_insecure_people": group["estimated_food_insecure_people"].sum(),
            "average_predicted_rate": group[RATE_COL].mean(),
            "max_predicted_rate": group[RATE_COL].max(),
            "average_poverty_rate": group["poverty_rate"].mean() if "poverty_rate" in group.columns else np.nan,
            "average_unemployment_rate": group["unemployment_rate"].mean() if "unemployment_rate" in group.columns else np.nan,
        }
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary["population_weighted_predicted_rate"] = summary["estimated_food_insecure_people"] / summary["total_population"]
    return summary.sort_values("population_weighted_predicted_rate", ascending=False)


def build_food_bank_summary(df):
    if FOOD_BANK_COL not in df.columns:
        return pd.DataFrame()
    work = df.dropna(subset=[RATE_COL, POP_COL]).copy()
    work["estimated_food_insecure_people"] = work[RATE_COL] * work[POP_COL]
    rows = []
    for food_bank, group in work.groupby(FOOD_BANK_COL):
        rows.append(
            {
                FOOD_BANK_COL: food_bank,
                "zcta_rows": group[ZCTA_COL].nunique(),
                "counties": group[COUNTY_COL].nunique(),
                "total_population": group[POP_COL].sum(),
                "estimated_food_insecure_people": group["estimated_food_insecure_people"].sum(),
                "average_predicted_rate": group[RATE_COL].mean(),
            }
        )
    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    summary["population_weighted_predicted_rate"] = summary["estimated_food_insecure_people"] / summary["total_population"]
    return summary.sort_values("population_weighted_predicted_rate", ascending=False)


def write_dashboard(output_dir, chart_paths, df, county_summary, food_bank_summary, input_name):
    scored = df.dropna(subset=[RATE_COL, POP_COL]).copy()
    forecast_year = int(scored["forecast_year"].dropna().iloc[0]) if "forecast_year" in scored.columns and not scored.empty else ""
    total_population = scored[POP_COL].sum()
    estimated_people = (scored[RATE_COL] * scored[POP_COL]).sum()
    weighted_rate = estimated_people / total_population if total_population else np.nan

    chart_cards = []
    for title, path in chart_paths:
        rel_path = html.escape(path.name)
        chart_cards.append(
            '<section class="chart-card"><h2>{}</h2><img src="{}" alt="{}"></section>'.format(
                html.escape(title), rel_path, html.escape(title)
            )
        )

    top_counties = county_summary.head(8)
    county_rows = "\n".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(row[COUNTY_COL])),
            pct(row["population_weighted_predicted_rate"]),
            whole_number(row["estimated_food_insecure_people"]),
            whole_number(row["total_population"]),
        )
        for _, row in top_counties.iterrows()
    )

    food_bank_table = ""
    if not food_bank_summary.empty:
        fb_rows = "\n".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(str(row[FOOD_BANK_COL])),
                pct(row["population_weighted_predicted_rate"]),
                whole_number(row["estimated_food_insecure_people"]),
                whole_number(row["total_population"]),
            )
            for _, row in food_bank_summary.head(8).iterrows()
        )
        food_bank_table = """
        <section class="table-card">
          <h2>Highest-Rate Food Banks</h2>
          <table>
            <thead><tr><th>Food bank</th><th>Weighted rate</th><th>Est. people</th><th>Population</th></tr></thead>
            <tbody>{}</tbody>
          </table>
        </section>
        """.format(fb_rows)

    page = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Florida Food Insecurity Forecast {forecast_year}</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: #17202a;
      background: #f5f7fa;
    }}
    header {{
      padding: 32px 42px 24px;
      background: #ffffff;
      border-bottom: 1px solid #d9dee7;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      letter-spacing: 0;
    }}
    p {{
      margin: 0;
      color: #4d5968;
      line-height: 1.45;
    }}
    main {{
      padding: 28px 42px 42px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }}
    .metric, .chart-card, .table-card {{
      background: #ffffff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(23, 32, 42, 0.05);
    }}
    .metric {{
      padding: 16px 18px;
    }}
    .metric strong {{
      display: block;
      font-size: 24px;
      margin-bottom: 4px;
    }}
    .metric span {{
      color: #5d6876;
      font-size: 13px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(520px, 1fr));
      gap: 18px;
      align-items: start;
    }}
    .chart-card, .table-card {{
      padding: 18px;
    }}
    h2 {{
      font-size: 18px;
      margin: 0 0 12px;
    }}
    img {{
      width: 100%;
      height: auto;
      display: block;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      border-bottom: 1px solid #e4e8ef;
      padding: 9px 7px;
      vertical-align: top;
    }}
    th {{
      color: #4d5968;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    @media (max-width: 700px) {{
      header, main {{ padding-left: 18px; padding-right: 18px; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Florida Food Insecurity Forecast {forecast_year}</h1>
    <p>Charts generated from <code>{input_name}</code>. Rates are model predictions; estimated people are predicted rate multiplied by ZIP/ZCTA population.</p>
  </header>
  <main>
    <section class="metrics">
      <div class="metric"><strong>{row_count}</strong><span>ZIP/ZCTA-county rows</span></div>
      <div class="metric"><strong>{scored_count}</strong><span>Rows with predictions</span></div>
      <div class="metric"><strong>{weighted_rate}</strong><span>Population-weighted rate</span></div>
      <div class="metric"><strong>{estimated_people}</strong><span>Estimated food-insecure people</span></div>
      <div class="metric"><strong>{county_count}</strong><span>Counties represented</span></div>
    </section>
    <section class="table-card" style="margin-bottom:18px;">
      <h2>Highest-Rate Counties</h2>
      <table>
        <thead><tr><th>County</th><th>Weighted rate</th><th>Est. people</th><th>Population</th></tr></thead>
        <tbody>{county_rows}</tbody>
      </table>
    </section>
    {food_bank_table}
    <section class="grid">
      {chart_cards}
    </section>
  </main>
</body>
</html>
""".format(
        forecast_year=forecast_year,
        input_name=html.escape(input_name),
        row_count=whole_number(len(df)),
        scored_count=whole_number(len(scored)),
        weighted_rate=pct(weighted_rate),
        estimated_people=whole_number(estimated_people),
        county_count=whole_number(df[COUNTY_COL].nunique() if COUNTY_COL in df.columns else np.nan),
        county_rows=county_rows,
        food_bank_table=food_bank_table,
        chart_cards="\n".join(chart_cards),
    )

    dashboard_path = output_dir / "forecast_dashboard.html"
    dashboard_path.write_text(page, encoding="utf-8")
    return dashboard_path


def main():
    args = parse_args()
    input_path = args.input
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError("Forecast CSV not found: {}".format(input_path))

    df = pd.read_csv(input_path)
    require_columns(df, [ZCTA_COL, COUNTY_COL, POP_COL, RATE_COL])

    df[RATE_COL] = pd.to_numeric(df[RATE_COL], errors="coerce")
    df[POP_COL] = pd.to_numeric(df[POP_COL], errors="coerce")
    df["estimated_food_insecure_people"] = df[RATE_COL] * df[POP_COL]
    df["zcta_label"] = "ZCTA " + df[ZCTA_COL].astype(str) + " (" + df[COUNTY_COL].astype(str).str.title() + ")"

    scored = df.dropna(subset=[RATE_COL, POP_COL]).copy()
    if scored.empty:
        raise ValueError("No rows have both population and predicted food insecurity rate values.")

    county_summary = build_county_summary(df)
    food_bank_summary = build_food_bank_summary(df)
    county_summary.to_csv(output_dir / "county_summary.csv", index=False)
    if not food_bank_summary.empty:
        food_bank_summary.to_csv(output_dir / "food_bank_summary.csv", index=False)

    top_zctas_by_rate = scored.nlargest(args.top_n, RATE_COL)[["zcta_label", RATE_COL, POP_COL, "estimated_food_insecure_people"]]
    top_zctas_by_people = scored.nlargest(args.top_n, "estimated_food_insecure_people")[["zcta_label", RATE_COL, POP_COL, "estimated_food_insecure_people"]]
    top_zctas_by_rate.to_csv(output_dir / "top_zctas_by_rate.csv", index=False)
    top_zctas_by_people.to_csv(output_dir / "top_zctas_by_estimated_people.csv", index=False)

    chart_paths = []
    chart_specs = [
        (
            "Highest Predicted Rates by ZIP/ZCTA",
            save_horizontal_bar(
                top_zctas_by_rate,
                "zcta_label",
                RATE_COL,
                "Highest Predicted Food Insecurity Rates by ZIP/ZCTA",
                "Predicted food insecurity rate",
                output_dir / "top_zctas_by_rate.png",
                pct,
                "#b94747",
            ),
        ),
        (
            "Largest Estimated Food-Insecure Populations by ZIP/ZCTA",
            save_horizontal_bar(
                top_zctas_by_people,
                "zcta_label",
                "estimated_food_insecure_people",
                "Largest Estimated Food-Insecure Populations by ZIP/ZCTA",
                "Estimated food-insecure people",
                output_dir / "top_zctas_by_estimated_people.png",
                whole_number,
                "#2f6f8f",
            ),
        ),
        (
            "Highest Population-Weighted Rates by County",
            save_horizontal_bar(
                county_summary.head(args.top_n),
                COUNTY_COL,
                "population_weighted_predicted_rate",
                "Highest Population-Weighted Predicted Rates by County",
                "Population-weighted predicted food insecurity rate",
                output_dir / "county_weighted_rates.png",
                pct,
                "#8a5f38",
            ),
        ),
        (
            "Largest Estimated Food-Insecure Populations by County",
            save_horizontal_bar(
                county_summary.sort_values("estimated_food_insecure_people", ascending=False).head(args.top_n),
                COUNTY_COL,
                "estimated_food_insecure_people",
                "Largest Estimated Food-Insecure Populations by County",
                "Estimated food-insecure people",
                output_dir / "county_estimated_people.png",
                whole_number,
                "#5a8f7b",
            ),
        ),
        ("Distribution of Predicted Rates", save_histogram(scored, output_dir / "rate_distribution.png")),
        ("Predicted Rate Compared With Population", save_scatter(scored, output_dir / "population_vs_predicted_rate.png")),
        ("Predicted Rate Ranges by Food Bank", save_food_bank_boxplot(scored, output_dir / "food_bank_rate_boxplot.png")),
        ("Drivers Correlated With Predicted Rate", save_correlation_chart(scored, output_dir / "driver_correlations.png")),
    ]
    chart_paths.extend((title, path) for title, path in chart_specs if path is not None)

    dashboard_path = write_dashboard(output_dir, chart_paths, df, county_summary, food_bank_summary, input_path.name)

    print("Wrote charts and summaries to {}".format(output_dir))
    for _, path in chart_paths:
        print("- {}".format(path.name))
    print("- {}".format((output_dir / "county_summary.csv").name))
    print("- {}".format((output_dir / "top_zctas_by_rate.csv").name))
    print("- {}".format((output_dir / "top_zctas_by_estimated_people.csv").name))
    print("- {}".format(dashboard_path.name))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Chart generation failed: {}".format(exc), file=sys.stderr)
        sys.exit(1)
