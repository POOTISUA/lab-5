"""Стенд вимірювання ЛР5 (Варіант 24: Структура С4, місткість 256, n=6 потоків: 3 запису, 3 читання)."""
import argparse
import array
import json
import math
import os
import platform
import random
import statistics
import sys
import threading
import time

from sync_pq import BoundedPriorityQueue

N_THREADS = 6
CAPACITY = 256
INITIAL_FILL = 128
WARMUP_S = 1.0
DURATION_S = 10.0
REPEATS = 3


def exact_percentile_us(sorted_ns: list, q: float) -> float:
    """Перцентиль p_q = tau_(ceil(q * N)) у мікросекундах."""
    n = len(sorted_ns)
    if n == 0:
        return 0.0
    idx = min(n - 1, max(0, math.ceil(q * n) - 1))
    return sorted_ns[idx] / 1000.0


def compute_cv(counts: list) -> float:
    k = len(counts)
    if k == 0:
        return 0.0
    mu = sum(counts) / k
    if mu == 0:
        return 0.0
    sigma = math.sqrt(sum((c - mu) ** 2 for c in counts) / k)
    return sigma / mu


def run_multi_thread(lock_mode: str, duration_s: float = DURATION_S, warmup_s: float = WARMUP_S) -> dict:
    pq = BoundedPriorityQueue(capacity=CAPACITY, lock_mode=lock_mode)
    rng_init = random.Random(2400)
    initial_ids = list(range(INITIAL_FILL))
    for iid in initial_ids:
        ok, _, _, _ = pq.push(rng_init.randint(1, 10000), iid)
        assert ok
    pq.min_size_seen = INITIAL_FILL
    pq.max_size_seen = INITIAL_FILL

    barrier = threading.Barrier(N_THREADS)
    stop_warmup = threading.Event()
    stop_measure = threading.Event()

    per_thread = {}

    def worker_fn(tid: int):
        is_writer = (tid % 2 == 1)
        rng = random.Random(2400 + tid)
        pushed_ids = array.array("Q")
        popped_ids = array.array("Q")
        tau_ns = array.array("q")
        wait_ns = array.array("q")

        # унікальний діапазон item_id для кожного потоку (крок 10_000_000)
        next_id = tid * 10_000_000 + 1
        do_push = True
        do_peek = True
        in_measure = False

        barrier.wait()

        if is_writer:
            while not stop_measure.is_set():
                if not in_measure and stop_warmup.is_set():
                    in_measure = True
                if do_push:
                    prio = rng.randint(1, 10000)
                    iid = next_id
                    next_id += 1
                    ok, w_ns, tot_ns, _ = pq.push(prio, iid)
                    assert ok, f"Queue overflow on thread {tid}"
                    pushed_ids.append(iid)
                else:
                    res, w_ns, tot_ns, _ = pq.pop()
                    assert res is not None, f"Unexpected empty queue on thread {tid}"
                    popped_ids.append(res[1])
                do_push = not do_push
                if in_measure:
                    tau_ns.append(tot_ns)
                    wait_ns.append(w_ns)
        else:
            last_peek_ok = True
            while not stop_measure.is_set():
                if not in_measure and stop_warmup.is_set():
                    in_measure = True
                if do_peek:
                    res, w_ns, tot_ns, _ = pq.peek_max()
                    if res is None:
                        last_peek_ok = False
                else:
                    sz, w_ns, tot_ns, _ = pq.size()
                    if not (0 <= sz <= CAPACITY):
                        last_peek_ok = False
                do_peek = not do_peek
                if in_measure:
                    tau_ns.append(tot_ns)
                    wait_ns.append(w_ns)
            assert last_peek_ok

        per_thread[tid] = {
            "tid": tid,
            "role": "write" if is_writer else "read",
            "count": len(tau_ns),
            "tau_ns": tau_ns,
            "wait_ns": wait_ns,
            "pushed_ids": pushed_ids,
            "popped_ids": popped_ids,
        }

    threads = [threading.Thread(target=worker_fn, args=(i,), daemon=True) for i in range(1, N_THREADS + 1)]
    for th in threads:
        th.start()

    time.sleep(warmup_s)
    t_m0 = time.perf_counter()
    stop_warmup.set()
    time.sleep(duration_s)
    stop_measure.set()
    t_m1 = time.perf_counter()
    for th in threads:
        th.join()

    d_actual = t_m1 - t_m0

    # Перевірка інваріантів структури
    inv_ok, inv_msg = pq.verify_invariants()
    all_pushed = set(initial_ids)
    total_pushed_cnt = len(initial_ids)
    all_popped = []
    for d in per_thread.values():
        if d["role"] == "write":
            total_pushed_cnt += len(d["pushed_ids"])
            all_pushed.update(d["pushed_ids"])
            all_popped.extend(d["popped_ids"])
    remaining = pq.drain_ids()
    all_extracted = all_popped + remaining

    no_dups_and_exact_match = (
        len(all_pushed) == total_pushed_cnt
        and len(all_extracted) == total_pushed_cnt
        and len(set(all_extracted)) == total_pushed_cnt
        and set(all_extracted) == all_pushed
    )

    if not inv_ok or not no_dups_and_exact_match:
        raise AssertionError(
            f"Invariant failed ({lock_mode}): inv={inv_ok} ({inv_msg}), exact_match={no_dups_and_exact_match}, "
            f"pushed={total_pushed_cnt}, extracted={len(all_extracted)}"
        )

    w_taus = []
    w_waits = []
    w_counts = []
    r_taus = []
    r_waits = []
    r_counts = []
    thread_ops = {}

    for tid in range(1, N_THREADS + 1):
        d = per_thread[tid]
        thread_ops[str(tid)] = d["count"]
        if d["role"] == "write":
            w_counts.append(d["count"])
            w_taus.extend(d["tau_ns"])
            w_waits.extend(d["wait_ns"])
        else:
            r_counts.append(d["count"])
            r_taus.extend(d["tau_ns"])
            r_waits.extend(d["wait_ns"])

    n_w = len(w_counts)
    n_r = len(r_counts)
    n_tot_w = sum(w_counts)
    n_tot_r = sum(r_counts)
    n_tot = n_tot_w + n_tot_r

    w_taus.sort()
    r_taus.sort()
    all_taus = sorted(w_taus + r_taus)

    sum_wait_w_s = sum(w_waits) / 1e9
    sum_wait_r_s = sum(r_waits) / 1e9
    max_wait_w_ms = (max(w_waits) / 1e6) if w_waits else 0.0
    max_wait_r_ms = (max(r_waits) / 1e6) if r_waits else 0.0
    max_wait_all_ms = max(max_wait_w_ms, max_wait_r_ms)

    x_w = n_tot_w / duration_s
    x_r = n_tot_r / duration_s
    x_all = x_w + x_r

    return {
        "lock_mode": lock_mode,
        "duration_s": duration_s,
        "actual_elapsed_s": round(d_actual, 4),
        "invariant": f"PASS ({inv_msg}, exact {total_pushed_cnt} items)",
        "thread_ops": thread_ops,
        "write": {
            "ops": n_tot_w,
            "X": x_w,
            "x_per_thread": x_w / n_w,
            "p50_us": exact_percentile_us(w_taus, 0.50),
            "p99_us": exact_percentile_us(w_taus, 0.99),
            "t_wait_max_ms": max_wait_w_ms,
            "w": sum_wait_w_s / (n_w * duration_s),
            "cv": compute_cv(w_counts),
            "phi": n_tot_w / n_tot if n_tot else 0.0,
        },
        "read": {
            "ops": n_tot_r,
            "X": x_r,
            "x_per_thread": x_r / n_r,
            "p50_us": exact_percentile_us(r_taus, 0.50),
            "p99_us": exact_percentile_us(r_taus, 0.99),
            "t_wait_max_ms": max_wait_r_ms,
            "w": sum_wait_r_s / (n_r * duration_s),
            "cv": compute_cv(r_counts),
            "phi": n_tot_r / n_tot if n_tot else 0.0,
        },
        "total": {
            "ops": n_tot,
            "X": x_all,
            "p50_us": exact_percentile_us(all_taus, 0.50),
            "p99_us": exact_percentile_us(all_taus, 0.99),
            "t_wait_max_ms": max_wait_all_ms,
            "w": (sum_wait_w_s + sum_wait_r_s) / (N_THREADS * duration_s),
            "cv": compute_cv(w_counts + r_counts),
        },
    }


def run_single_thread_x1(lock_mode: str, duration_s: float = DURATION_S, warmup_s: float = WARMUP_S) -> float:
    """Вимір X_1: 1 потік по черзі виконує запис і читання у пропорції n_w : n_r = 3 : 3 = 1 : 1
    (push -> peek_max -> pop -> size) під тим самим замком.
    """
    pq = BoundedPriorityQueue(capacity=CAPACITY, lock_mode=lock_mode)
    rng = random.Random(2499)
    for iid in range(INITIAL_FILL):
        pq.push(rng.randint(1, 10000), iid)

    # Прогрів 1 с
    next_id = 1_000_000
    t_end_warm = time.perf_counter() + warmup_s
    while time.perf_counter() < t_end_warm:
        prio = rng.randint(1, 10000)
        pq.push(prio, next_id)
        next_id += 1
        pq.peek_max()
        pq.pop()
        pq.size()

    # Вимір D = 10 с
    ops = 0
    t_end = time.perf_counter() + duration_s
    while time.perf_counter() < t_end:
        prio = rng.randint(1, 10000)
        pq.push(prio, next_id)
        next_id += 1
        pq.peek_max()
        pq.pop()
        pq.size()
        ops += 4

    ok, _ = pq.verify_invariants()
    assert ok
    return ops / duration_s


def measure_t_cs(iterations: int = 200_000) -> dict:
    """Однопотоковий вимір часу утримання глобального замка t_cs,w та t_cs,r у мікросекундах."""
    pq = BoundedPriorityQueue(capacity=CAPACITY, lock_mode="global")
    rng = random.Random(2477)
    for iid in range(INITIAL_FILL):
        pq.push(rng.randint(1, 10000), iid)

    sum_cs_w = 0
    sum_cs_r = 0
    next_id = 5_000_000
    for _ in range(iterations):
        prio = rng.randint(1, 10000)
        _, _, _, cs1 = pq.push(prio, next_id)
        next_id += 1
        _, _, _, cs2 = pq.pop()
        _, _, _, cs3 = pq.peek_max()
        _, _, _, cs4 = pq.size()
        sum_cs_w += cs1 + cs2
        sum_cs_r += cs3 + cs4

    t_cs_w_us = (sum_cs_w / (2 * iterations)) / 1000.0
    t_cs_r_us = (sum_cs_r / (2 * iterations)) / 1000.0
    t_cs_bar_us = (3 * t_cs_w_us + 3 * t_cs_r_us) / 6.0
    return {"t_cs_w_us": t_cs_w_us, "t_cs_r_us": t_cs_r_us, "t_cs_bar_us": t_cs_bar_us}


def median_run_dict(runs: list, mode_name: str) -> dict:
    """Бере медіану кожного числового показника по 3 прогонах, а для thread_ops бере прогін із медіанним X."""
    runs_sorted = sorted(runs, key=lambda r: r["total"]["X"])
    med_run = runs_sorted[len(runs_sorted) // 2]

    out = {
        "lock_mode": mode_name,
        "repeats": len(runs),
        "all_invariants_passed": all(r["invariant"].startswith("PASS") for r in runs),
        "invariant_sample": med_run["invariant"],
        "thread_ops_median_run": med_run["thread_ops"],
        "thread_ops_by_run": [r["thread_ops"] for r in runs],
        "X_by_run": [round(r["total"]["X"], 2) for r in runs],
    }
    for section in ("write", "read", "total"):
        out[section] = {}
        for k in runs[0][section].keys():
            out[section][k] = round(statistics.median(r[section][k] for r in runs), 6)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["global", "rwlock", "single_global", "single_rwlock", "cs_measure", "all"], default="all")
    args = ap.parse_args()

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    res_path = os.path.join(out_dir, "lab5_results.json")
    data = json.load(open(res_path, encoding="utf-8")) if os.path.exists(res_path) else {}

    data["env"] = {
        "variant": 24,
        "structure": "С4 (BoundedPriorityQueue, capacity=256)",
        "n": N_THREADS,
        "n_w": 3,
        "n_r": 3,
        "capacity": CAPACITY,
        "D_s": DURATION_S,
        "warmup_s": WARMUP_S,
        "repeats": REPEATS,
        "python": sys.version.split()[0],
        "os": platform.platform(),
        "logical_cpus": os.cpu_count(),
    }

    if args.mode in ("single_global", "all"):
        vals = [run_single_thread_x1("global") for _ in range(REPEATS)]
        data["X1_global"] = {"runs": [round(v, 2) for v in vals], "median": round(statistics.median(vals), 2)}
        print(f"[X1 global] runs={data['X1_global']['runs']} -> median={data['X1_global']['median']:.2f} ops/s", flush=True)

    if args.mode in ("single_rwlock", "all"):
        vals = [run_single_thread_x1("rwlock") for _ in range(REPEATS)]
        data["X1_rwlock"] = {"runs": [round(v, 2) for v in vals], "median": round(statistics.median(vals), 2)}
        print(f"[X1 rwlock] runs={data['X1_rwlock']['runs']} -> median={data['X1_rwlock']['median']:.2f} ops/s", flush=True)

    if args.mode in ("cs_measure", "all"):
        cs_runs = [measure_t_cs() for _ in range(REPEATS)]
        data["t_cs"] = {
            "t_cs_w_us": round(statistics.median(r["t_cs_w_us"] for r in cs_runs), 4),
            "t_cs_r_us": round(statistics.median(r["t_cs_r_us"] for r in cs_runs), 4),
            "t_cs_bar_us": round(statistics.median(r["t_cs_bar_us"] for r in cs_runs), 4),
            "runs": cs_runs,
        }
        print(f"[t_cs] t_cs,w={data['t_cs']['t_cs_w_us']:.4f} us, t_cs,r={data['t_cs']['t_cs_r_us']:.4f} us, t_bar={data['t_cs']['t_cs_bar_us']:.4f} us", flush=True)

    if args.mode in ("global", "all"):
        runs_g = []
        for idx in range(REPEATS):
            r = run_multi_thread("global")
            runs_g.append(r)
            print(f"[global run {idx+1}/{REPEATS}] X_w={r['write']['X']:.1f} X_r={r['read']['X']:.1f} X={r['total']['X']:.1f} ops/s {r['invariant']}", flush=True)
        data["global"] = median_run_dict(runs_g, "global")
        data["global_runs"] = runs_g

    if args.mode in ("rwlock", "all"):
        runs_rw = []
        for idx in range(REPEATS):
            r = run_multi_thread("rwlock")
            runs_rw.append(r)
            print(f"[rwlock run {idx+1}/{REPEATS}] X_w={r['write']['X']:.1f} X_r={r['read']['X']:.1f} X={r['total']['X']:.1f} ops/s {r['invariant']}", flush=True)
        data["rwlock"] = median_run_dict(runs_rw, "rwlock")
        data["rwlock_runs"] = runs_rw

    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved results to {res_path}")


if __name__ == "__main__":
    main()
