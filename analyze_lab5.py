"""Аналіз результатів ЛР5 (Варіант 24) і побудова діаграм у results/analysis/."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(ROOT, "results")
OUT = os.path.join(RES, "analysis")
os.makedirs(OUT, exist_ok=True)


def rw_over_g(v_rw: float, v_g: float) -> str:
    if v_g == 0.0:
        return f"{(v_rw - v_g):+.4f} (різниця)"
    return f"{(v_rw / v_g):.4f}"


def main():
    d = json.load(open(os.path.join(RES, "lab5_results.json"), encoding="utf-8"))
    env = d["env"]
    x1_g = d["X1_global"]["median"]
    x1_rw = d["X1_rwlock"]["median"]
    t_cs_w = d["t_cs"]["t_cs_w_us"]
    t_cs_r = d["t_cs"]["t_cs_r_us"]
    t_cs_bar = d["t_cs"]["t_cs_bar_us"]
    bound_g = 1e6 / t_cs_bar

    g = d["global"]
    rw = d["rwlock"]

    x_g = g["total"]["X"]
    x_rw = rw["total"]["X"]
    n = env["n"]

    metrics = {
        "S_global": round(x_g / x1_g, 4),
        "E_global": round((x_g / x1_g) / n, 4),
        "S_rwlock": round(x_rw / x1_rw, 4),
        "E_rwlock": round((x_rw / x1_rw) / n, 4),
        "S_w": round(rw["write"]["X"] / g["write"]["X"], 4),
        "S_r": round(rw["read"]["X"] / g["read"]["X"], 4),
        "S_total": round(x_rw / x_g, 4),
        "bound_global_ops_s": round(bound_g, 2),
        "rho_global": round(x_g * (t_cs_bar / 1e6), 4),
    }

    # Графік 1: Швидкість X_w, X_r, X для X_1, Global та RWLock
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    labels = ["Запис (X_w)", "Читання (X_r)", "Разом (X)"]
    g_vals = [g["write"]["X"], g["read"]["X"], g["total"]["X"]]
    rw_vals = [rw["write"]["X"], rw["read"]["X"], rw["total"]["X"]]
    xs = [0, 1, 2]
    w_bar = 0.34
    b1 = ax.bar([i - w_bar / 2 for i in xs], g_vals, width=w_bar, color="C0", label="Глобальний замок (G)")
    b2 = ax.bar([i + w_bar / 2 for i in xs], rw_vals, width=w_bar, color="C1", label="RWLock (Writer-Preferring)")
    ax.axhline(bound_g, color="red", ls="--", lw=1.1, label=f"Теор. межа 1/t̄_cs = {bound_g:.0f} оп/с")
    for bar in list(b1) + list(b2):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h, f"{h:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Пропускна здатність, оп/с")
    ax.set_title("ЛР5 (Варіант 24, С4, n=6): Швидкість під глобальним замком і RWLock", fontsize=10.5)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "throughput_compare.png"), dpi=130)
    plt.close(fig)

    # Графік 2: Затримки p50, p99 (мкс) та частка очікування w
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.3))
    roles = ["Запис", "Читання"]
    p50_g = [g["write"]["p50_us"], g["read"]["p50_us"]]
    p99_g = [g["write"]["p99_us"], g["read"]["p99_us"]]
    p50_rw = [rw["write"]["p50_us"], rw["read"]["p50_us"]]
    p99_rw = [rw["write"]["p99_us"], rw["read"]["p99_us"]]
    xr = [0, 1]
    axs[0].bar([i - 0.18 for i in xr], p99_g, width=0.34, color="C0", label="G: p99")
    axs[0].bar([i + 0.18 for i in xr], p99_rw, width=0.34, color="C1", label="RWLock: p99")
    axs[0].bar([i - 0.18 for i in xr], p50_g, width=0.34, color="navy", alpha=0.65, label="G: p50")
    axs[0].bar([i + 0.18 for i in xr], p50_rw, width=0.34, color="darkred", alpha=0.65, label="RWLock: p50")
    axs[0].set_xticks(xr)
    axs[0].set_xticklabels(roles)
    axs[0].set_ylabel("Тривалість операції, мкс")
    axs[0].set_title("Медіана p50 та 99-й перцентиль p99")
    axs[0].grid(axis="y", alpha=0.3)
    axs[0].legend(fontsize=8)

    w_g = [g["write"]["w"], g["read"]["w"]]
    w_rw = [rw["write"]["w"], rw["read"]["w"]]
    axs[1].bar([i - 0.18 for i in xr], w_g, width=0.34, color="C0", label="Глобальний замок")
    axs[1].bar([i + 0.18 for i in xr], w_rw, width=0.34, color="C1", label="RWLock")
    for idx in xr:
        axs[1].text(idx - 0.18, w_g[idx], f"{w_g[idx]:.3f}", ha="center", va="bottom", fontsize=8)
        axs[1].text(idx + 0.18, w_rw[idx], f"{w_rw[idx]:.3f}", ha="center", va="bottom", fontsize=8)
    axs[1].set_xticks(xr)
    axs[1].set_xticklabels(roles)
    axs[1].set_ylim(0, 1.1)
    axs[1].set_ylabel("Частка часу в очікуванні w")
    axs[1].set_title("Частка часу в очікуванні замка w")
    axs[1].grid(axis="y", alpha=0.3)
    axs[1].legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "latency_wait_compare.png"), dpi=130)
    plt.close(fig)

    # Графік 3: Кількість операцій по потоках 1..6
    fig, ax = plt.subplots(figsize=(8, 4.2))
    tids = [str(i) for i in range(1, n + 1)]
    t_labels = [f"Потік {i}\n({'запис' if i % 2 else 'читання'})" for i in range(1, n + 1)]
    tg = [g["thread_ops_median_run"][t] for t in tids]
    trw = [rw["thread_ops_median_run"][t] for t in tids]
    xt = list(range(n))
    ax.bar([i - 0.18 for i in xt], tg, width=0.35, color="C0", label="Глобальний замок")
    ax.bar([i + 0.18 for i in xt], trw, width=0.35, color="C1", label="RWLock")
    ax.set_xticks(xt)
    ax.set_xticklabels(t_labels, fontsize=8.5)
    ax.set_ylabel("Операцій за D = 10 с")
    ax.set_title("Розподіл кількості операцій по потоках (медіанний прогін)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "per_thread_ops.png"), dpi=130)
    plt.close(fig)

    summary = {"env": env, "X1_global": x1_g, "X1_rwlock": x1_rw, "t_cs": d["t_cs"], "global": g, "rwlock": rw, "metrics": metrics}
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    h_g_w = g["write"]["p99_us"] / g["write"]["p50_us"]
    h_g_r = g["read"]["p99_us"] / g["read"]["p50_us"]
    h_rw_w = rw["write"]["p99_us"] / rw["write"]["p50_us"]
    h_rw_r = rw["read"]["p99_us"] / rw["read"]["p50_us"]

    md = [
        "# Зведені таблиці ЛР5 (Варіант 24, С4, n = 6)\n",
        f"- **Таблиця 1 (Стенд):** n = {n}, n_w = {env['n_w']}, n_r = {env['n_r']}, Python {env['python']}, логічних ядер = {env['logical_cpus']}, X_1 (G) = {x1_g:.2f} оп/с, X_1 (RWLock) = {x1_rw:.2f} оп/с, інваріанти: `PASS`\n",
        "## Таблиця 2. Глобальний замок (медіана з 3 прогонів по 10 с)\n",
        "| Роль | Операцій за D | X, оп/с | p50, мкс | p99, мкс | Найбільший t_wait, мс | w | cv | t_cs, мкс |",
        "|---|---|---|---|---|---|---|---|---|",
        f"| Запис | {g['write']['ops']:.0f} | {g['write']['X']:.2f} | {g['write']['p50_us']:.2f} | {g['write']['p99_us']:.2f} | {g['write']['t_wait_max_ms']:.3f} | {g['write']['w']:.4f} | {g['write']['cv']:.4f} | {t_cs_w:.4f} |",
        f"| Читання | {g['read']['ops']:.0f} | {g['read']['X']:.2f} | {g['read']['p50_us']:.2f} | {g['read']['p99_us']:.2f} | {g['read']['t_wait_max_ms']:.3f} | {g['read']['w']:.4f} | {g['read']['cv']:.4f} | {t_cs_r:.4f} |",
        f"| Разом | {g['total']['ops']:.0f} | {g['total']['X']:.2f} | {g['total']['p50_us']:.2f} | {g['total']['p99_us']:.2f} | {g['total']['t_wait_max_ms']:.3f} | {g['total']['w']:.4f} | {g['total']['cv']:.4f} | {t_cs_bar:.4f} |",
        "\n## Таблиця 3. RWLock (Writer-Preferring на threading.Condition)\n",
        "| Роль | Операцій за D | X, оп/с | p50, мкс | p99, мкс | Найбільший t_wait, мс | w | cv |",
        "|---|---|---|---|---|---|---|---|",
        f"| Запис | {rw['write']['ops']:.0f} | {rw['write']['X']:.2f} | {rw['write']['p50_us']:.2f} | {rw['write']['p99_us']:.2f} | {rw['write']['t_wait_max_ms']:.3f} | {rw['write']['w']:.4f} | {rw['write']['cv']:.4f} |",
        f"| Читання | {rw['read']['ops']:.0f} | {rw['read']['X']:.2f} | {rw['read']['p50_us']:.2f} | {rw['read']['p99_us']:.2f} | {rw['read']['t_wait_max_ms']:.3f} | {rw['read']['w']:.4f} | {rw['read']['cv']:.4f} |",
        f"| Разом | {rw['total']['ops']:.0f} | {rw['total']['X']:.2f} | {rw['total']['p50_us']:.2f} | {rw['total']['p99_us']:.2f} | {rw['total']['t_wait_max_ms']:.3f} | {rw['total']['w']:.4f} | {rw['total']['cv']:.4f} |",
        "\n## Таблиця 4. Операції потоків за D = 10 с\n",
        "| Потік | Роль | Глобальний замок | RWLock |",
        "|---|---|---|---|",
    ]
    for tid in range(1, n + 1):
        role = "запис" if tid % 2 == 1 else "читання"
        md.append(f"| {tid} | {role} | {g['thread_ops_median_run'][str(tid)]} | {rw['thread_ops_median_run'][str(tid)]} |")

    md.extend([
        "\n## Таблиця 5. Метрики прискорення\n",
        "| Метрика | Формула | Значення |",
        "|---|---|---|",
        f"| S(n), глобальний замок | X(G) / X_1 | {metrics['S_global']:.4f} |",
        f"| E(n), глобальний замок | S(n) / n | {metrics['E_global']:.4f} |",
        f"| S(n), RWLock | X(RW) / X_1(RW) | {metrics['S_rwlock']:.4f} |",
        f"| E(n), RWLock | S(n) / n | {metrics['E_rwlock']:.4f} |",
        f"| S_w | X_w(RW) / X_w(G) | {metrics['S_w']:.4f} |",
        f"| S_r | X_r(RW) / X_r(G) | {metrics['S_r']:.4f} |",
        f"| S_Σ | X(RW) / X(G) | {metrics['S_total']:.4f} |",
        f"| ρ, завантаженість глобального замка | X(G) · t̄_cs | {metrics['rho_global']:.4f} |",
        f"| Межа 1 / t̄_cs | 1 / t̄_cs | {bound_g:.2f} оп/с |",
        "\n## Таблиця 6. Порівняння доступу до даних\n",
        "| Показник | G: запис | G: читання | RW: запис | RW: читання | RW / G: запис | RW / G: читання |",
        "|---|---|---|---|---|---|---|",
        f"| X, оп/с | {g['write']['X']:.2f} | {g['read']['X']:.2f} | {rw['write']['X']:.2f} | {rw['read']['X']:.2f} | {rw_over_g(rw['write']['X'], g['write']['X'])} | {rw_over_g(rw['read']['X'], g['read']['X'])} |",
        f"| x, оп/с на потік ролі | {g['write']['x_per_thread']:.2f} | {g['read']['x_per_thread']:.2f} | {rw['write']['x_per_thread']:.2f} | {rw['read']['x_per_thread']:.2f} | {rw_over_g(rw['write']['x_per_thread'], g['write']['x_per_thread'])} | {rw_over_g(rw['read']['x_per_thread'], g['read']['x_per_thread'])} |",
        f"| p50, мкс | {g['write']['p50_us']:.2f} | {g['read']['p50_us']:.2f} | {rw['write']['p50_us']:.2f} | {rw['read']['p50_us']:.2f} | {rw_over_g(rw['write']['p50_us'], g['write']['p50_us'])} | {rw_over_g(rw['read']['p50_us'], g['read']['p50_us'])} |",
        f"| p99, мкс | {g['write']['p99_us']:.2f} | {g['read']['p99_us']:.2f} | {rw['write']['p99_us']:.2f} | {rw['read']['p99_us']:.2f} | {rw_over_g(rw['write']['p99_us'], g['write']['p99_us'])} | {rw_over_g(rw['read']['p99_us'], g['read']['p99_us'])} |",
        f"| h = p99 / p50 | {h_g_w:.2f} | {h_g_r:.2f} | {h_rw_w:.2f} | {h_rw_r:.2f} | {rw_over_g(h_rw_w, h_g_w)} | {rw_over_g(h_rw_r, h_g_r)} |",
        f"| Найбільший t_wait, мс | {g['write']['t_wait_max_ms']:.3f} | {g['read']['t_wait_max_ms']:.3f} | {rw['write']['t_wait_max_ms']:.3f} | {rw['read']['t_wait_max_ms']:.3f} | {rw_over_g(rw['write']['t_wait_max_ms'], g['write']['t_wait_max_ms'])} | {rw_over_g(rw['read']['t_wait_max_ms'], g['read']['t_wait_max_ms'])} |",
        f"| w | {g['write']['w']:.4f} | {g['read']['w']:.4f} | {rw['write']['w']:.4f} | {rw['read']['w']:.4f} | {rw_over_g(rw['write']['w'], g['write']['w'])} | {rw_over_g(rw['read']['w'], g['read']['w'])} |",
        f"| cv | {g['write']['cv']:.4f} | {g['read']['cv']:.4f} | {rw['write']['cv']:.4f} | {rw['read']['cv']:.4f} | {rw_over_g(rw['write']['cv'], g['write']['cv'])} | {rw_over_g(rw['read']['cv'], g['read']['cv'])} |",
        f"| φ | {g['write']['phi']:.4f} | {g['read']['phi']:.4f} | {rw['write']['phi']:.4f} | {rw['read']['phi']:.4f} | {rw_over_g(rw['write']['phi'], g['write']['phi'])} | {rw_over_g(rw['read']['phi'], g['read']['phi'])} |",
    ])
    with open(os.path.join(OUT, "tables.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print("Lab 5 analysis written to results/analysis/")


if __name__ == "__main__":
    main()
