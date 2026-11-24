"""Потокобезпечна обмежена пріоритетна черга (Структура С4, Варіант 24)
та реалізація замка читання-запису (Writer-Preferring RWLock) на threading.Condition.
"""
import threading
import time
from typing import Any, List, Optional, Tuple


class WriterPreferringRWLock:
    """Замок читання-запису (RWLock) з пріоритетом запису на базі threading.Condition.

    Політика (Writer-Preferring):
    - Дозволяє довільній кількості читачів одночасно утримувати замок, якщо жоден писець
      не активний і жоден писець не очікує в черзі.
    - Коли писець викликає acquire_write(), він збільшує лічильник writers_waiting:
      нові читачі блокуються доти, доки активні писці й писці в черзі не завершать роботу.
      Це запобігає голодуванню писців (writer starvation) за інтенсивного читання.
    """

    def __init__(self):
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0
        self._writer_active = False
        self._writers_waiting = 0

    def acquire_read(self):
        with self._cond:
            while self._writer_active or self._writers_waiting > 0:
                self._cond.wait()
            self._readers += 1

    def release_read(self):
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def acquire_write(self):
        with self._cond:
            self._writers_waiting += 1
            try:
                while self._writer_active or self._readers > 0:
                    self._cond.wait()
                self._writer_active = True
            finally:
                self._writers_waiting -= 1

    def release_write(self):
        with self._cond:
            self._writer_active = False
            self._cond.notify_all()


class _GlobalLockAdapter:
    """Адаптер звичайного threading.Lock до інтерфейсу acquire_read / acquire_write."""

    def __init__(self):
        self._lock = threading.Lock()

    def acquire_read(self):
        self._lock.acquire()

    def release_read(self):
        self._lock.release()

    def acquire_write(self):
        self._lock.acquire()

    def release_write(self):
        self._lock.release()


class BoundedPriorityQueue:
    """Обмежена max-heap пріоритетна черга місткістю capacity (С4, capacity = 256).

    Реалізовано без готових потокобезпечних колекцій (лише список та примітиви синхронізації).
    Кожен елемент у купі — кортеж (priority, seq_tiebreaker, item_id, payload).
    """

    def __init__(self, capacity: int = 256, lock_mode: str = "global"):
        if lock_mode not in ("global", "rwlock"):
            raise ValueError(f"Unsupported lock_mode: {lock_mode}")
        self.capacity = capacity
        self.lock_mode = lock_mode
        self._lock = _GlobalLockAdapter() if lock_mode == "global" else WriterPreferringRWLock()
        self._heap: List[Tuple[int, int, Any]] = []
        self._seq = 0
        self.min_size_seen = 0
        self.max_size_seen = 0

    def _sift_up(self, idx: int):
        heap = self._heap
        item = heap[idx]
        while idx > 0:
            parent = (idx - 1) >> 1
            if heap[parent][0] < item[0]:
                heap[idx] = heap[parent]
                idx = parent
            else:
                break
        heap[idx] = item

    def _sift_down(self, idx: int):
        heap = self._heap
        n = len(heap)
        item = heap[idx]
        while True:
            left = (idx << 1) + 1
            if left >= n:
                break
            right = left + 1
            largest = right if (right < n and heap[right][0] > heap[left][0]) else left
            if heap[largest][0] > item[0]:
                heap[idx] = heap[largest]
                idx = largest
            else:
                break
        heap[idx] = item

    def push(self, priority: int, item_id: int) -> Tuple[bool, int, int, int]:
        """Операція запису: додає елемент (priority, item_id) у чергу.
        Повертає (ok, wait_ns, total_ns, cs_ns).
        """
        t_call = time.perf_counter_ns()
        self._lock.acquire_write()
        t_acq = time.perf_counter_ns()
        try:
            n = len(self._heap)
            if n >= self.capacity:
                ok = False
            else:
                self._seq += 1
                self._heap.append((priority, self._seq, item_id))
                self._sift_up(n)
                new_len = n + 1
                if new_len > self.max_size_seen:
                    self.max_size_seen = new_len
                ok = True
            t_rel = time.perf_counter_ns()
        finally:
            self._lock.release_write()
        t_ret = time.perf_counter_ns()
        return ok, (t_acq - t_call), (t_ret - t_call), (t_rel - t_acq)

    def pop(self) -> Tuple[Optional[Tuple[int, int]], int, int, int]:
        """Операція запису: вилучає і повертає (priority, item_id) з найбільшим пріоритетом.
        Повертає (item_or_None, wait_ns, total_ns, cs_ns).
        """
        t_call = time.perf_counter_ns()
        self._lock.acquire_write()
        t_acq = time.perf_counter_ns()
        try:
            n = len(self._heap)
            if n == 0:
                res = None
            elif n == 1:
                p, _s, iid = self._heap.pop()
                res = (p, iid)
                if 0 < self.min_size_seen:
                    self.min_size_seen = 0
            else:
                top_p, _s, top_id = self._heap[0]
                self._heap[0] = self._heap.pop()
                self._sift_down(0)
                res = (top_p, top_id)
                new_len = n - 1
                if new_len < self.min_size_seen:
                    self.min_size_seen = new_len
            t_rel = time.perf_counter_ns()
        finally:
            self._lock.release_write()
        t_ret = time.perf_counter_ns()
        return res, (t_acq - t_call), (t_ret - t_call), (t_rel - t_acq)

    def peek_max(self) -> Tuple[Optional[Tuple[int, int]], int, int, int]:
        """Операція читання: повертає (priority, item_id) з найбільшим пріоритетом без зміни черги."""
        t_call = time.perf_counter_ns()
        self._lock.acquire_read()
        t_acq = time.perf_counter_ns()
        try:
            if self._heap:
                top_p, _s, top_id = self._heap[0]
                res = (top_p, top_id)
            else:
                res = None
            t_rel = time.perf_counter_ns()
        finally:
            self._lock.release_read()
        t_ret = time.perf_counter_ns()
        return res, (t_acq - t_call), (t_ret - t_call), (t_rel - t_acq)

    def size(self) -> Tuple[int, int, int, int]:
        """Операція читання: повертає поточну кількість елементів у черзі без зміни структури."""
        t_call = time.perf_counter_ns()
        self._lock.acquire_read()
        t_acq = time.perf_counter_ns()
        try:
            sz = len(self._heap)
            t_rel = time.perf_counter_ns()
        finally:
            self._lock.release_read()
        t_ret = time.perf_counter_ns()
        return sz, (t_acq - t_call), (t_ret - t_call), (t_rel - t_acq)

    def verify_invariants(self) -> Tuple[bool, str]:
        """Перевіряє властивість max-heap та обмеження місткості [0, capacity]."""
        self._lock.acquire_read()
        try:
            n = len(self._heap)
            if not (0 <= n <= self.capacity):
                return False, f"size {n} outside [0, {self.capacity}]"
            if not (0 <= self.min_size_seen and self.max_size_seen <= self.capacity):
                return False, f"observed size range [{self.min_size_seen}, {self.max_size_seen}] outside [0, {self.capacity}]"
            for i in range(1, n):
                parent = (i - 1) >> 1
                if self._heap[parent][0] < self._heap[i][0]:
                    return False, f"heap violation at {parent}->{i}: {self._heap[parent][0]} < {self._heap[i][0]}"
            if n > 0:
                max_p = max(x[0] for x in self._heap)
                if self._heap[0][0] != max_p:
                    return False, f"heap root {self._heap[0][0]} != max {max_p}"
            return True, f"ok (len={n}, range=[{self.min_size_seen},{self.max_size_seen}])"
        finally:
            self._lock.release_read()

    def drain_ids(self) -> List[int]:
        """Вилучає всі залишені item_id у черзі в порядку спадання пріоритету для перевірки точної множини."""
        self._lock.acquire_write()
        try:
            ids = []
            while self._heap:
                if len(self._heap) == 1:
                    _, _, iid = self._heap.pop()
                else:
                    _, _, iid = self._heap[0]
                    self._heap[0] = self._heap.pop()
                    self._sift_down(0)
                ids.append(iid)
            return ids
        finally:
            self._lock.release_write()
