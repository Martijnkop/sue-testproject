# CPU-Time Anti-Patterns for Testing an AI Optimization Pipeline

24 patterns that are harder to fix or harder for an analyzer to pick up.

- **H1-H10**: the "hidden / data-dependent / NumPy" patterns from the second list (first 10 items).
- **P1-P14**: the "profile-driven" patterns (flamegraph, `self_time`, `total_time`) from the latest list.

**Sorting:** grouped by ease of fix (Easy, Medium, Hard, No fix needed), then by impact (highest first), then alphabetically by pattern name.

**Notes on the ratings**
- All ratings are my own estimates.
- H-ratings come from the earlier list. P-ratings for impact and frequency were not given before, so I assigned them here.
- Where a pattern had a range for ease (e.g. "Easy to medium"), it is grouped under the harder end of the range.
- Where impact varies a lot (H4), I ranked it by its typical case.

Impact scale used for ordering: Extreme > Very high > High > Medium to high > Medium > Low to medium > Low.

---

## Summary table

### Group 1: Easy to fix

| ID | Pattern | Impact | Frequency | Ease (exact) |
|----|---------|--------|-----------|--------------|
| H5 | Bad `__hash__` degrading dict/set to O(n²) | Extreme | Rare | Easy once found |
| P4 | Recursion distorting total time (no memoization) | Very high | Occasional | Easy |
| H10 | Growing arrays or DataFrames in a loop | High | Very common | Easy |
| H1 | Property or helper that recomputes on every access | High | Common | Easy once found |
| H4 | Eager log formatting | Medium (varies, low to very high) | Very common | Easy |

### Group 2: Medium to fix

| ID | Pattern | Impact | Frequency | Ease (exact) |
|----|---------|--------|-----------|--------------|
| P9 | CPU work blocking the event loop | High | Common | Medium |
| H2 | Hidden quadratic work in a helper (list membership) | High | Very common | Easy to medium |
| P11 | Hot because of workload, not code | High (varies) | Common | Medium |
| H9 | `np.vectorize` / `apply` pretending to be vectorized | High | Common | Easy to medium |
| P1 | Self time in a builtin, fix in the caller | High | Very common | Medium |
| H7 | Caches that never hit or hurt | Medium to high | Occasional | Medium |
| H8 | Dynamic regex patterns thrashing the `re` cache | Medium to high | Occasional | Medium |
| P5 | GC time attributed to the wrong function | Medium to high | Occasional | Medium |
| P2 | Many cheap calls, no single hot function | Medium to high | Very common | Medium |
| H6 | Recursion with slicing | Medium to high | Common | Easy to medium |
| H3 | Repeated validation or serialization between layers | Medium to high | Common | Medium |
| P14 | Import-time and startup cost | Medium | Common | Easy to medium |

### Group 3: Hard to fix

| ID | Pattern | Impact | Frequency | Ease (exact) |
|----|---------|--------|-----------|--------------|
| P12 | Needs a build-level change (Cython / Numba) | Very high | Occasional | Hard to medium |
| P7 | Process pool where pickling / IPC dominates | High | Common | Hard |
| P3 | Flat profile ("death by a thousand cuts") | Medium to high | Very common | Hard |
| P8 | Lock contention and GIL waiting | Medium | Occasional to common | Medium to hard |
| P13 | Memory layout and cache effects | Medium | Common | Hard |

### Group 4: No fix needed (restraint tests)

| ID | Pattern | Impact | Frequency | Ease (exact) |
|----|---------|--------|-----------|--------------|
| P10 | Legitimately expensive work | High (in the profile) | Common | N/A, leave it |
| P6 | Profiler overhead inflating tiny functions | Low (artifact) | Common | N/A, leave it |

---

## Explanations

### Group 1: Easy to fix

#### H5: Bad `__hash__` degrading dict/set to O(n²)
```python
class Key:
    def __hash__(self): return 1          # or hash(self.type_name) with few distinct values
    def __eq__(self, o): return self.id == o.id

cache = {Key(i): v for i, v in enumerate(vals)}
```
**Why it's slow:** Every key lands in the same bucket, so each insert or lookup compares against all existing keys.
**Fix:** Hash on the same fields `__eq__` uses, e.g. `hash(self.id)`.
**Profile signal:** `__eq__` and dict internals dominate, but only with real data distributions. A benign dataset hides it.

#### P4: Recursion distorting total time (no memoization)
```python
def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)
```
**Why it's slow:** Exponential repeated work. In the flamegraph, the same function appears in deep nested frames, and `total_time` double-counts them.
**Fix:** `functools.lru_cache`, or an iterative version.
**Test:** Check that the AI doesn't report cumulative time above 100% and does identify memoization as the fix.

#### H10: Growing arrays or DataFrames in a loop
```python
result = np.array([])
for chunk in chunks:
    result = np.append(result, process(chunk))

df = pd.DataFrame()
for r in rows:
    df = pd.concat([df, pd.DataFrame([r])])
```
**Why it's slow:** Each iteration copies everything accumulated so far, making the loop O(n²).
**Fix:** Collect pieces in a list, then build once with `np.concatenate` or `pd.concat`.

#### H1: Property or helper that recomputes on every access
```python
class Report:
    @property
    def sorted_rows(self):
        return sorted(self._rows, key=expensive_key)

for i in range(len(r.sorted_rows)):
    use(r.sorted_rows[i])        # sorts twice per iteration
```
**Why it's slow:** The loop looks innocent, but each property access redoes a sort.
**Fix:** Compute once before the loop, or use `functools.cached_property`.
**Profile signal:** The sort shows up as a wide box under the loop's caller, so this is straightforward with flamegraphs.

#### H4: Eager log formatting
```python
logger.debug(f"State: {expensive_repr(state)}")   # runs even if DEBUG is off
```
**Why it's slow:** The f-string and `expensive_repr` are evaluated before `debug()` checks the level.
**Fix:** `logger.debug("State: %s", state)` or guard with `if logger.isEnabledFor(logging.DEBUG)`.
**Note:** Impact depends entirely on how expensive the repr is.

---

### Group 2: Medium to fix

#### P9: CPU work blocking the event loop
```python
async def handle(req):
    return hash_password(req.pw)     # bcrypt, parsing, etc.
```
**Why it's slow:** The call looks like an ordinary hot frame, but while it runs every other task waits. A CPU flamegraph doesn't show the latency harm.
**Fix:** `await loop.run_in_executor(...)`. Process pool vs thread pool is a real decision (GIL, pickling cost).

#### H2: Hidden quadratic work in a helper (list membership)
```python
def is_known(x):
    return x in KNOWN_LIST      # a list, defined in another module

filtered = [x for x in stream if is_known(x)]
```
**Why it's slow:** `in` on a list is O(n), so the comprehension is O(n·m).
**Fix:** Make `KNOWN_LIST` a `frozenset`, after checking who else uses it.
**Profile signal:** Time lands in `list.__contains__`. See also P1.

#### P11: Hot because of workload, not code
**Scenario:** The profile was captured on a small or unrepresentative input. Hostile-hash (H5) and regex-backtracking cases won't show up at all if the profiled workload avoids the bad data.
**Fix:** Capture profiles from representative workloads, then fix the underlying code.
**Test:** Give the AI two profiles of the same code (benign vs hostile input) and check it notices the difference.

#### H9: `np.vectorize` / `apply` pretending to be vectorized
```python
f = np.vectorize(lambda x: math.sin(x) if x > 0 else 0)
out = f(arr)                       # still a Python loop
```
**Why it's slow:** `np.vectorize` is a convenience wrapper around a Python loop. A naive analyzer may approve it because it looks like NumPy.
**Fix:** `np.where(arr > 0, np.sin(arr), 0)` and other ufuncs.

#### P1: Self time in a builtin, fix in the caller
```python
def is_known(x):
    return x in KNOWN_LIST        # self time shows up in list.__contains__
```
**Why it's tricky:** Self time sits in a C frame with no useful source. The real fix is the data structure passed in, possibly two frames up.
**Test:** Check whether the AI walks up the stack instead of "optimizing" the leaf.

#### H7: Caches that never hit or hurt
```python
@lru_cache(maxsize=None)
def price(item, timestamp):        # timestamp makes every key unique
    ...
```
**Why it's slow:** Zero hit rate, unbounded memory growth, and rising GC cost. A wasted cache is worse than none.
**Fix:** Decide what the key should be (drop or bucket the timestamp), and bound `maxsize`.
**Profile signal:** Needs hit-rate data. A flamegraph alone shows only extra time in cache wrapper and GC.

#### H8: Dynamic regex patterns thrashing the `re` cache
```python
for term in terms:                       # thousands of distinct terms
    if re.search(rf"\b{term}\b", text): ...
```
**Why it's slow:** `re` caches only about 512 compiled patterns, so large pattern sets recompile constantly.
**Fix:** One combined alternation pattern, or a different algorithm such as Aho-Corasick.

#### P5: GC time attributed to the wrong function
**Scenario:** In a sampling profile, a GC pause lands in whichever function was allocating at that moment. The "hot" function is innocent.
**Fix:** Reduce container allocations (`__slots__`, tuples, arrays), or use `gc.freeze()` / tune thresholds.
**Test:** Strong false-positive trap. The AI should not rewrite the innocent function.

#### P2: Many cheap calls, no single hot function
```python
for row in rows:                  # 2M iterations
    normalize(row)                # ~2µs per call, tiny self time
```
**Why it's tricky:** No frame has a large `self_time`. The cost is in the caller's `total_time`.
**Fix:** Batch the work or remove the call.
**Test:** Depends on whether you expose call counts. Without them, this may be undetectable by design.

#### H6: Recursion with slicing
```python
def total(xs):
    return 0 if not xs else xs[0] + total(xs[1:])
```
**Why it's slow:** Each slice copies the remaining list (O(n²) overall), and recursion depth can hit limits. Also seen in binary search implemented with slices.
**Fix:** Pass indices, or iterate.

#### H3: Repeated validation or serialization between layers
```python
def handler(payload):
    data = json.loads(payload)
    return service(json.dumps(data))      # service immediately loads it again

def service(s):
    return repo(json.loads(s))
```
**Why it's slow:** Repeated parse and dump round-trips. Variants: pydantic models revalidated at every layer, or `deepcopy` via a pickle round-trip.
**Fix:** Pass parsed objects between layers. This changes interfaces, so callers must be updated.

#### P14: Import-time and startup cost
**Scenario:** Steady-state profiles miss it entirely. A short-lived CLI may be dominated by heavy imports (pandas, torch, etc.).
**Fix:** Lazy imports, or moving work out of module top level.
**Test:** Include a profile captured from process start to exit.

---

### Group 3: Hard to fix

#### P12: Needs a build-level change (Cython / Numba)
```python
def count_primes(n):
    count = 0
    for i in range(2, n):
        for j in range(2, int(i**0.5) + 1):
            if i % j == 0: break
        else:
            count += 1
    return count
```
**Why it's hard:** The hot loop is easy to detect at 80% of runtime, but the right fix (Cython, Numba `@njit`, or NumPy) adds a dependency or build step. Speedups can be 50-200x.
**Test:** Check whether the AI proposes a proportionate fix and states the tradeoff, rather than only pure-Python tweaks.

#### P7: Process pool where pickling / IPC dominates
```python
with ProcessPoolExecutor() as ex:
    results = ex.map(score, big_dataframes)    # hundreds of MB serialized per task
```
**Why it's slow:** Serialization and IPC can cost more than the work itself, sometimes making it slower than serial.
**Fix:** Shared memory, worker initializers, or sending indices instead of data.
**Profile signal:** Appears in the parent as `multiprocessing` internals or idle waiting, while worker profiles are separate unless captured with `py-spy --subprocesses`.

#### P3: Flat profile ("death by a thousand cuts")
**Scenario:** Pydantic validation, logging, attribute lookups and dict copies each take 2-3% across the codebase. No box stands out, but together they cost about 30%.
**Fix:** Usually architectural, with many small changes.
**Test:** Check the AI doesn't give up or invent a hot spot.

#### P8: Lock contention and GIL waiting
```python
lock = Lock()
def worker(x):
    with lock:                     # serializes the whole function
        return expensive(x)
```
**Why it's tricky:** Threads blocked on `lock.acquire` aren't burning CPU, so depending on whether the profiler samples idle frames (`py-spy --idle`, `--gil`) the problem looks dominant or invisible.
**Fix:** Narrow the lock scope, or use processes for CPU-bound work.
**Test:** Since your target is CPU time, check the AI separates wall time from CPU time.

#### P13: Memory layout and cache effects
```python
a = np.random.rand(5000, 5000)          # float64 where float32 might do
for j in range(a.shape[1]):
    col_sum = a[:, j].copy().sum()       # strided access plus unnecessary copy
```
**Why it's hard:** The profile shows a slow `sum`, with no signal about why. The fix needs knowledge of precision requirements and memory order (`axis=` reductions, contiguous arrays, dtype choice).

---

### Group 4: No fix needed (restraint tests)

#### P10: Legitimately expensive work
**Scenario:** `bcrypt`, compression, crypto hashing, a required `deepcopy`, or the `fsync` in a durability guarantee dominate `self_time`.
**Expected behavior:** The AI should say the cost is inherent and not "optimize" it.

#### P6: Profiler overhead inflating tiny functions
**Scenario:** `cProfile` is deterministic and penalizes call-heavy code, so small helpers look expensive when they aren't. A sampling profile of the same code looks different.
**Expected behavior:** The AI should not rewrite functions that are only slow under instrumentation. If your pipeline mixes profile sources, test with both.

---

## Suggested test design

- **Score blame, not just detection:** record which frame the correct fix touches, and check whether the AI changes that frame or just the leaf with the highest `self_time` (P1, P5, H2).
- **Provide benign and hostile inputs** for data-dependent cases (H5, H8, P11).
- **Include the no-fix cases** (P10, P6) and flat profiles (P3), where profile-driven pipelines tend to hallucinate improvements.
- **Add a correctness oracle and a benchmark threshold** for every fixable case.
