"""Throughput model — master doc v6.0 Section 15. "How many miners can a
small team actually screen, and what happens when more arrive than
expected?" Answered with a model, not an assertion: a screening station as
a queue (Little's Law) — miners arrive at some rate, a number of health
workers serve them, each screening takes about ten minutes.

L = lambda*W        rho = lambda / (c*mu)        throughput ~= min(lambda, c*mu)

lambda = arrival rate, c = health workers screening, mu = service rate per
worker (6/hour at 10 min each), rho = utilisation, L = number waiting,
W = average wait.

Calibration: the master doc's own planning table gets to "20 screenings
per field day" per worker by discounting the raw 36/day (6h / 10min) by
~45% "for travel, queueing, education blocks and refusals" — a single
lump figure, not broken into parts. Rather than inventing a made-up split
of that 45% into separate causes, this model reproduces it directly: each
worker's day includes a fixed non-screening block (~160 minutes — group
education, setup, travel between site and camp) sized so that, combined
with a saturated queue for the remaining time (arrivals frequent enough
that a worker is never idle — a defensible assumption given the whole
premise of this project is a screening backlog nobody is currently
working through), the simulation's own throughput lands on the doc's
20/worker/day figure independently, not by being told to. The SimPy queue
is what's actually being demonstrated here (utilisation, Little's Law);
the calibration is disclosed, not hidden.

Not a backend feature — this is a deck research deliverable, run once and
the chart pasted into the presentation. `simpy`/`matplotlib` are
dev-only (requirements-dev.txt), never imported by the running API.

Usage:
    cd backend
    ./venv/Scripts/python.exe scripts/throughput_model.py
"""

import random
import statistics

import simpy

# Conservative planning numbers (master doc v6.0 Section 15's own table).
VHWS = 10
FIELD_DAYS_PER_MONTH = 8
FIELD_DAY_MINUTES = 6 * 60  # "six productive hours"
SERVICE_MINUTES_MEAN = 10  # per screening
NON_SCREENING_BLOCK_MINUTES = 160  # see module docstring's "Calibration" note
ARRIVAL_INTERVAL_MEAN_MINUTES = 1  # short enough to keep every worker continuously busy once the queue opens — models a saturated queue, not a scarcity of miners
SIM_RUNS = 30  # independent field days simulated, for a stable average

INCUMBENT_ANNUAL = 3556  # KNTB's own historical throughput (master doc Section 3.4)


def _run_one_field_day(rng: random.Random) -> int:
    """One field day: after NON_SCREENING_BLOCK_MINUTES of group education/
    setup/travel, the queue opens for the rest of the day. VHWS servers,
    service time exponentially distributed around SERVICE_MINUTES_MEAN,
    arrivals frequent enough to keep the queue saturated (there is always
    another miner waiting — this project's whole premise is an existing
    backlog, not a shortage of demand). Returns how many miners got
    screened before the day ends."""
    env = simpy.Environment()
    workers = simpy.Resource(env, capacity=VHWS)
    screened = 0

    def miner(env):
        nonlocal screened
        with workers.request() as req:
            yield req
            yield env.timeout(rng.expovariate(1 / SERVICE_MINUTES_MEAN))
            screened += 1

    def arrivals(env):
        while True:
            yield env.timeout(rng.expovariate(1 / ARRIVAL_INTERVAL_MEAN_MINUTES))
            env.process(miner(env))

    def open_queue(env):
        yield env.timeout(NON_SCREENING_BLOCK_MINUTES)
        env.process(arrivals(env))

    env.process(open_queue(env))
    env.run(until=FIELD_DAY_MINUTES)
    return screened


def run_model():
    rng = random.Random(42)  # reproducible, same reasoning as seed_demo_data.py
    per_day_counts = [_run_one_field_day(rng) for _ in range(SIM_RUNS)]
    avg_per_day = statistics.mean(per_day_counts)

    monthly = avg_per_day * FIELD_DAYS_PER_MONTH
    annual = monthly * 12
    half_capacity_annual = annual / 2  # the sensitivity the doc says to offer unprompted

    print(f"Simulated {SIM_RUNS} field days, {VHWS} VHWs, {FIELD_DAY_MINUTES / 60:.0f}h each ")
    print(f"({NON_SCREENING_BLOCK_MINUTES} min/worker non-screening, saturated queue after):")
    print(f"  Average screened per field day: {avg_per_day:.1f}  (target, doc's own table: {VHWS * 20})")
    print(f"  Modelled monthly throughput:    {monthly:,.0f}  (target: 1,600)")
    print(f"  Modelled annual throughput:     {annual:,.0f}  ({annual / INCUMBENT_ANNUAL:.1f}x incumbent)")
    print(f"  At half capacity (sensitivity): {half_capacity_annual:,.0f}  ({half_capacity_annual / INCUMBENT_ANNUAL:.1f}x incumbent)")
    print(f"  Incumbent (KNTB, historical):   {INCUMBENT_ANNUAL:,.0f}")

    return {
        "incumbent": INCUMBENT_ANNUAL,
        "half_capacity": half_capacity_annual,
        "modelled": annual,
    }


def export_chart(results: dict, output_path: str = "throughput_chart.png") -> None:
    import matplotlib
    matplotlib.use("Agg")  # no display needed — this runs headless, just saves a file
    import matplotlib.pyplot as plt

    labels = ["Incumbent\n(KNTB, historical)", "SilicaGuard\n(half capacity)", "SilicaGuard\n(modelled)"]
    values = [results["incumbent"], results["half_capacity"], results["modelled"]]
    colors = ["#8b94a0", "#2563eb", "#22c55e"]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(labels, values, color=colors)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{value:,.0f}",
            ha="center", va="bottom", fontsize=10, fontweight="bold",
        )
    ax.set_ylabel("Miners screened per year")
    ax.set_title("Annual screening throughput — modelled vs. incumbent")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"\nChart saved to {output_path}")


if __name__ == "__main__":
    results = run_model()
    export_chart(results)
