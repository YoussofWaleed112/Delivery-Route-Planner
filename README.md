# Delivery Route Planner

A small Python program that reads delivery requests and groups them into
vehicle trips, respecting a 10 kg capacity per trip, while trying to keep
deliveries for the same area together and always handling the most
urgent (lowest priority number) deliveries first.

## Files

- `delivery_planner.py` – the program
- `deliveries.json` – sample input
- `trips.json` – example JSON output produced by `--output`
- `driver_report.txt` – example output produced by `--driver-report`
- `support_tracking.csv` – example output produced by `--support-tracking`

## Input format

**JSON**, as a list of objects, one per delivery:

```json
[
    {"id": 1, "area": "Nasr City", "priority": 2, "weight_kg": 4.5},
    {"id": 2, "area": "Maadi", "priority": 1, "weight_kg": 2.0},
    {"id": 3, "area": "Nasr City", "priority": 3, "weight_kg": 1.2},
    {"id": 4, "area": "Zamalek", "priority": 1, "weight_kg": 2.0},
    {"id": 5, "area": "Maadi", "priority": 2, "weight_kg": 3.5},
    {"id": 6, "area": "Zamalek", "priority": 1, "weight_kg": 1.0}
]
```

Each object needs `id`, `area`, `priority` (integer, lower = more urgent)
and `weight_kg`.

## How to run it

Requires only Python 3 (standard library only — no `pip install` needed).

```bash
# Print the plan to the console
python3 delivery_planner.py deliveries.json

# Also write the plan to a JSON file
python3 delivery_planner.py deliveries.json --output trips.json

# Use a different vehicle capacity
python3 delivery_planner.py deliveries.json --capacity 12

# Also generate the two extension views (see below)
python3 delivery_planner.py deliveries.json \
    --driver-report driver_report.txt \
    --support-tracking support_tracking.csv
```

All three output flags (`--output`, `--driver-report`, `--support-tracking`)
are optional and independent — use any combination of them, or none.

Running it on the sample data prints:

```
Vehicle capacity: 10.0 kg

Trip 1 (9.7 kg)
    ID = 2   Priority = 1  Weight = 2.0kg    Area=Maadi
    ID = 5   Priority = 2  Weight = 3.5kg    Area=Maadi
    ID = 4   Priority = 1  Weight = 2.0kg    Area=Zamalek
    ID = 6   Priority = 1  Weight = 1.0kg    Area=Zamalek
    ID = 3   Priority = 3  Weight = 1.2kg    Area=Nasr City
Trip 2 (4.5 kg)
    ID = 1   Priority = 2  Weight = 4.5kg    Area=Nasr City
```

## 1. Solution approach

The core idea is: **sort by urgency first, then greedily build each trip
around the most urgent unassigned delivery, in two phases.**

1. Load the JSON file into a list of delivery dictionaries.
2. Any delivery whose weight already exceeds the vehicle's capacity is
   pulled out into a separate "unassignable" list — it can never be
   carried, so it should never silently disappear into a trip that
   secretly violates the capacity rule.
3. Sort the remaining deliveries by `priority` ascending. This becomes a
   working queue, `remaining`. Because Python's `sort` is stable,
   deliveries that tie on priority keep their original order.
4. To build one trip:
   - Pop the delivery at the front of `remaining`. This becomes the
     trip's `current_package`, fixes the trip's primary area, and fixes
     a single **target priority** for the trip: `current_package
     priority + 1`.
   - **Phase 1 – strict same-area match:** scan `remaining` for another
     delivery in the *same area* whose priority is *exactly* the target
     priority and that still fits under capacity. Add every match found
     (more than one delivery can share that exact priority), but never
     advance the target further — a same-area delivery two or more
     priority levels away is treated as too far removed in urgency to
     justify grouping with the current trip.
   - **Phase 2 – fill leftover :** once Phase 1 can't add
     anything more, scan whatever is left in `remaining` (any area, in
     priority order) and pick up anything that still fits, so spare
     vehicle capacity isn't wasted just because the one "ideal"
     same-area match wasn't available.
   - Close the trip.
5. Start a new trip with whichever delivery is now at the front of
   `remaining` (the next most urgent delivery overall — possibly a
   different area), and repeat.
6. Stop when `remaining` is empty. Every valid delivery ends up in
   exactly one trip.

## 2. Most difficult part

Two things were the trickiest.

First, deciding exactly how "close" in priority a same-area delivery
needs to be before it's worth grouping with `current_package`. Several
drafts tried chaining through consecutive priorities, or loosening the
match to "any same-area delivery regardless of gaps," before settling on
the fixed rule: a trip only ever reaches for the delivery at *exactly*
`current_package priority + 1 (Calibratable Value)` in that area.


## 3. Situations where the grouping may not be optimal

This is a **greedy** algorithm, not an optimal solver:

- **Priority gaps stop Phase 1, but Phase 2 can still merge across
  them anyway.** A same-area delivery only joins a trip in Phase 1 if
  its priority is exactly `current_package priority + 1`. If there's
  spare capacity afterwards, Phase 2 will still pick up a
  priority-distant delivery anyway, just for a different reason
  (filling space, not matching urgency).
- **Trips can span multiple areas.** Because Phase 2 fills leftover
  space from anywhere in the queue, a trip's deliveries are no longer
  guaranteed to share one area — area grouping is the *first*
  preference (via `current_package` and Phase 1), but capacity
  efficiency wins out once Phase 1 is exhausted.
- **No backtracking.** Once a delivery is placed in a trip, it's never
  moved to a different trip even if a smarter combination elsewhere
  would have used the vehicle's space better. True bin-packing (to
  minimize the number of trips or maximize average load) is NP-hard in
  general; this is a fast, "good enough" heuristic instead.

## 4. Behavior at 1,000,000 deliveries

The main bottleneck is the trip-building step: for every delivery added
to a trip (in either phase), the algorithm re-scans the remaining list
from the top. In the worst case this is O(n²) comparisons, which would
become very slow at a million records.

`list.pop(idx)` from the middle of a large Python list is itself an
O(n) operation, which compounds the slowdown further as trips are built.

Memory-wise, `deepcopy`-ing the full delivery list and holding both the
original and working copies in memory would also become expensive at
that scale, and the JSON/CSV outputs (`--output`, `--support-tracking`)
build their full result in memory before writing it out, which doesn't
scale to very large inputs either.

## 5. What I'd improve with another day

- **Index by area**: maintain a dictionary of `area -> list of
  deliveries` (already priority-sorted) instead of scanning the whole
  remaining list for each match. That turns "find the next same-area
  candidate" from an O(n) scan into a near O(1) lookup.
- **Streaming input/output**: for very large inputs, read the JSON with
  a streaming parser and write trips/CSV rows out incrementally instead
  of building one giant in-memory structure.
- **Tests**: a proper `pytest` suite for the edge cases (empty input,
  oversized packages, priority ties, exact-capacity fits) instead of
  manual runs.
- See also the two GUI/routing extensions proposed below.

## Extension

**What I added:** two extra, optional output views generated from the
same trip plan — a plain-text **driver report** (`--driver-report`) and
a CSV **customer-support tracking sheet** (`--support-tracking`).

- `driver_report.txt` lists each trip as a simple checklist, in the
  order stops should be made, with a blank `[ ]` box per stop:
  ```
  Trip 1 - Maadi, Zamalek, Nasr City (9.7 kg)
  --------------------------------------------------
  [ ] Stop 1: #2   Maadi        priority 1  (2.0 kg)
  [ ] Stop 2: #5   Maadi        priority 2  (3.5 kg)
  ...
  ```
- `support_tracking.csv` lists every delivery (including unassignable
  ones) with its trip number, an SLA label derived from its priority
  (`SLA_HOURS_BY_PRIORITY` at the top of the file — priority 1 → 2h,
  2 → 4h, 3 → 8h, anything else → same day), and a blank `status`
  column:
  ```
  id,area,priority,weight_kg,trip_number,sla,status
  2,Maadi,1,2.0,1,Deliver within 2h,Pending
  ...
  1,Nasr City,1,12.0,UNASSIGNED,N/A - exceeds vehicle capacity,Needs manual arrangement
  ```

**Why this, specifically:** the trip-planning data structure by itself
is only useful to the program. The two people who actually act on it day
to day are the driver and customer support, and they need it in
different shapes:

- The driver doesn't need JSON — they need an ordered, glanceable
  checklist they can follow stop by stop without needing any special
  software, and the checkboxes make it obvious at a glance which stops
  on a route are done and which are left. This directly helps the
  "keep same-area deliveries together" goal show up as something
  concrete: the driver can see when consecutive stops share an area and
  plan their route accordingly.
- Customer support doesn't work stop-by-stop, they work delivery-by-
  delivery when a customer calls in. A CSV is the natural format for
  that — anyone can open it in Excel/Sheets, sort or filter by
  `priority`, `trip_number`, or `status`, and immediately see whether a
  given delivery has an SLA it should have already met. This is also
  the shape a business would want for **analytics**: it's one row per
  delivery with priority, weight, area, and trip assignment already
  joined together, so it can be dropped straight into a spreadsheet or
  a BI tool to answer questions like "what fraction of priority-1
  deliveries are on time" or "which area generates the most oversized,
  unassignable packages" — without writing any extra code.

I kept both formats intentionally low-tech (plain text, CSV) rather than
a database or an API, since the assignment's scope doesn't justify more
than that, and both are things every driver's phone and every support
agent's laptop can already open.

### Two further extensions worth considering (not implemented)

**1. A GUI to choose the scheduling mode (priority-only vs. area-only).**
Right now the algorithm always does both: Phase 1 groups by area (within
one priority step), Phase 2 fills by priority regardless of area. A real
dispatch tool would probably want to let a manager toggle between:
  - *Priority-only mode*: ignore area entirely, just pack the vehicle in
    strict priority order. This would mean deleting the Phase 1
    same-area/`target_priority` block entirely and relying only on the
    Phase-2-style "does it fit" scan (starting from the top of the
    priority-sorted queue).
  - *Area-only mode*: ignore priority except for tie-breaking, and pack
    each trip by area alone. This would mean removing the
    `target_priority` check from Phase 1 (so it accepts *any* same-area
    delivery, not just the exact next priority) and dropping Phase 2's
    cross-area fill, so a trip never mixes areas.
  A small GUI (even a simple two-button toggle) sitting in front of
  `plan_trips()` could pass a `mode` flag in and switch which block of
  code runs, without touching the rest of the program (loading,
  validation, reporting, or the two extension views above all stay
  the same regardless of mode).

**2. Using real GPS/location data to group by proximity, not just
priority.** The current notion of "same area" is just a text label
(`"Maadi"`, `"Zamalek"`, ...), so it can't tell that two deliveries in
different named areas might actually be a two-minute drive apart, or
that two deliveries in the same named area might be at opposite ends of
a large district. If the input included real coordinates and the
company already has a GPS/tracking system in place, the grouping
condition could be extended (or replaced) with a proximity check —
e.g., "same area **or** within X km of the last stop" — so trips are
built around actual driving distance instead of a label. This would
make the trips shorter and more realistic to drive, at the cost of
needing real coordinate data and a distance calculation (or a routing
API) that this text-only assignment doesn't currently have.
