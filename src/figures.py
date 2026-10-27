"""Draw the README figures, each in a light and a dark version (docs/figures/*_{light,dark}.png).

Colors come from a validated two-slot palette (blue for data, orange for the Medicare
benchmark; both pass the CVD and contrast checks on their surface). Each figure has one
data series, so the title names it and there is no legend box; the Medicare line is
labeled directly.
"""

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from analysis import CASE_RATE_RULE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
RESULTS = ROOT / "results"

THEMES = {
    "light": {"surface": "#fcfcfb", "text": "#0b0b0b", "text2": "#52514e", "grid": "#e4e3df",
              "data": "#2a78d6", "bench": "#eb6834"},
    "dark": {"surface": "#1a1a19", "text": "#f0efec", "text2": "#c3c2b7", "grid": "#383835",
             "data": "#3987e5", "bench": "#d95926"},
}
SEGMENTS = [  # display order and short labels
    ("Commercial", "Commercial\n(employer plans)"),
    ("Exchange (individual/small group)", "Exchange\n(individual market)"),
    ("Essential Plan", "NY Essential Plan"),
    ("Medicare Advantage", "Medicare Advantage"),
    ("Medicaid managed care", "Medicaid\nmanaged care"),
]
SHORT = {
    "wmc": "Westchester Medical Center", "nyp_hv": "NYP Hudson Valley", "nyp_wch": "NYP Westchester",
    "nwh": "Northern Westchester", "phelps": "Phelps", "wph": "White Plains Hospital",
    "mmv": "Montefiore Mount Vernon", "mnr": "Montefiore New Rochelle", "sjr": "St. John's Riverside",
    "sjmc": "St. Joseph's",
}


def style(ax, t):
    ax.set_facecolor(t["surface"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(t["grid"])
    ax.tick_params(colors=t["text2"], length=0, labelsize=10)
    ax.grid(axis="x", color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def finish(fig, ax, t, title, subtitle, name, mode):
    fig.patch.set_facecolor(t["surface"])
    fig.text(0.02, 0.97, title, color=t["text"], fontsize=13, fontweight="bold", va="top")
    fig.text(0.02, 0.915, subtitle, color=t["text2"], fontsize=10, va="top")
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}_{mode}.png", dpi=160, facecolor=t["surface"])
    plt.close(fig)


def fig_segments(con, mode):
    """Every plan's diagnostic colonoscopy rate, as a multiple of Medicare, by segment."""
    t = THEMES[mode]
    df = con.sql(f"""
        SELECT segment, pct_of_medicare FROM negotiated
        WHERE code = '45378' AND {CASE_RATE_RULE}
    """).df()
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    fig.subplots_adjust(left=0.2, right=0.97, top=0.8, bottom=0.12)
    off_edge = int((df.pct_of_medicare > 12).sum())
    for i, (seg, label) in enumerate(SEGMENTS):
        vals = df.loc[df.segment == seg, "pct_of_medicare"].sort_values().to_numpy()
        y = len(SEGMENTS) - 1 - i
        jitter = ((pd.Series(range(len(vals))) % 7) - 3) * 0.045
        ax.scatter(vals, y + jitter, s=22, color=t["data"], alpha=0.55, edgecolors="none")
        med = pd.Series(vals).median()
        ax.plot([med, med], [y - 0.32, y + 0.32], color=t["text"], linewidth=2.2, solid_capstyle="round")
        ax.text(med, y + 0.38, f"{med:.1f}x", color=t["text"], fontsize=9.5, ha="center", va="bottom")
    ax.axvline(1, color=t["bench"], linewidth=2)
    ax.text(1.08, -0.45, "Medicare = 1x ($1,161)", color=t["text2"], fontsize=9, va="center")
    ax.set_yticks(range(len(SEGMENTS)))
    ax.set_yticklabels([lab for _, lab in reversed(SEGMENTS)], color=t["text"])
    ax.set_xlim(0, 12)
    ax.set_xticks(range(0, 13, 2))
    ax.set_xticklabels([f"{x}x" for x in range(0, 13, 2)])
    ax.set_ylim(-0.7, len(SEGMENTS) - 0.2)
    style(ax, t)
    finish(fig, ax, t, "One diagnostic colonoscopy, priced as a multiple of Medicare",
           "Each dot is one plan's published rate at one of 10 Westchester hospitals. Line = median.\n"
           f"Commercial and Exchange = whole-visit case rates. {off_edge} commercial rates above 12x are off the right edge.",
           "fig1_segments", mode)


def fig_hospitals(mode):
    """Commercial case rate for a diagnostic colonoscopy at each hospital: median and range."""
    t = THEMES[mode]
    df = pd.read_csv(RESULTS / "commercial_by_hospital.csv", dtype={"code": str})
    df = df[df.code == "45378"].sort_values("median_dollar")
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    fig.subplots_adjust(left=0.31, right=0.96, top=0.8, bottom=0.12)
    for y, r in enumerate(df.itertuples()):
        ax.plot([r.low_dollar, r.high_dollar], [y, y], color=t["data"], linewidth=2, alpha=0.45,
                solid_capstyle="round")
        ax.scatter([r.median_dollar], [y], s=70, color=t["data"], zorder=3,
                   edgecolors=t["surface"], linewidths=2)
        near_line = r.median_dollar < 2500  # keep the label clear of the Medicare line
        ax.text(r.median_dollar + (450 if near_line else 0), y + (0 if near_line else 0.28),
                f"${r.median_dollar:,.0f}", color=t["text"], fontsize=9,
                ha="left" if near_line else "center", va="center" if near_line else "bottom")
    medicare = df.medicare_rate.iloc[0]
    ax.axvline(medicare, color=t["bench"], linewidth=2)
    ax.text(medicare + 150, -0.75, f"Medicare ${medicare:,.0f}", color=t["text2"], fontsize=9, va="center")
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels([f"{SHORT[h]} ({n})" for h, n in zip(df.hospital_id, df.commercial_plans)], color=t["text"])
    ax.set_xlim(0, 20000)
    ax.set_xticks(range(0, 20001, 5000))
    ax.set_xticklabels([f"${x // 1000}k" if x else "$0" for x in range(0, 20001, 5000)])
    ax.set_ylim(-1.1, len(df) - 0.3)
    style(ax, t)
    finish(fig, ax, t, "Commercial price for a diagnostic colonoscopy, by hospital",
           "Dot = median commercial case rate; line = lowest to highest plan (plan count in parentheses).\n"
           "One plan at White Plains ($29,019) is off the right edge.",
           "fig2_hospitals", mode)


def fig_payers(mode):
    """Like-for-like insurer index: insurer rate / typical insurer rate at the same hospital and code."""
    t = THEMES[mode]
    df = pd.read_csv(RESULTS / "payer_index.csv").sort_values("index_vs_typical_insurer")
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    fig.subplots_adjust(left=0.3, right=0.96, top=0.78, bottom=0.13)
    for y, r in enumerate(df.itertuples()):
        ax.plot([r.p25, r.p75], [y, y], color=t["data"], linewidth=2, alpha=0.45, solid_capstyle="round")
        ax.scatter([r.index_vs_typical_insurer], [y], s=70, color=t["data"], zorder=3,
                   edgecolors=t["surface"], linewidths=2)
        ax.text(r.index_vs_typical_insurer, y + 0.25, f"{r.index_vs_typical_insurer:.2f}",
                color=t["text"], fontsize=9, ha="center", va="bottom")
    ax.axvline(1, color=t["text2"], linewidth=1, linestyle=(0, (3, 3)))
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels([f"{p} ({h} hosp.)" for p, h in zip(df.payer_family, df.hospitals)], color=t["text"])
    ax.set_xlim(0, 2.5)
    style(ax, t)
    finish(fig, ax, t, "Which insurers pay more for the same procedure at the same hospital?",
           "1.00 = the typical insurer's rate at that hospital for that code (each insurer counted once).\n"
           "Dot = median; line = middle half.",
           "fig3_payers", mode)


def main():
    con = duckdb.connect(str(ROOT / "data" / "gi_prices.duckdb"), read_only=True)
    for mode in THEMES:
        fig_segments(con, mode)
        fig_hospitals(mode)
        fig_payers(mode)
    print(f"wrote {len(list(FIG.glob('*.png')))} figures to docs/figures/")


if __name__ == "__main__":
    main()
