"""
Reads a list of delivery requests from a JSON file and groups them into
vehicle trips, respecting a maximum per-trip weight capacity, while trying
to keep deliveries for the same area together and handling the most
urgent (lowest priority number) deliveries first.

Usage:
    python planner.py deliveries.json (OUTPUT SHOWS IN TERMINAL)
    python planner.py deliveries.json --capacity 10 --output trips.json (OUTPUT GETS STORED IN OUTPUT .JSON FILE)
"""

import argparse
import json
import csv
import sys
from copy import deepcopy


DEFAULT_CAPACITY_KG = 10.0
Priority_Added_to_trip = 1

# How urgently each priority level should be delivered, used only by the
# customer-support tracking sheet (see generate_support_tracking below).
# Anything not listed here (priority 4+) falls back to "Same day".
SLA_HOURS_BY_PRIORITY = {1: 2, 2: 4, 3: 8}


def sla_label_for_priority(priority):
    """Return a human-readable label for the SLA implied by a given priority level.
    Thus the priority number is used to determine how quickly the delivery should be made,
    and this function returns a string that describes that urgency in hours."""

    hours = SLA_HOURS_BY_PRIORITY.get(priority)
    return f"Deliver within {hours}h" if hours is not None else "Deliver same day"


# Loading & validation Section: read the input JSON file and check that it is well-formed

def load_deliveries(path):
    """Load the delivery list from a JSON file.

    Input Format Expected (list of objects):
        [
            {"id": 1, "area": "Nasr City", "priority": 2, "weight_kg": 4.5},
            ...
        ]
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    """Check if the input JSON is a list of delivery objects, if not raise an error"""

    if not isinstance(data, list):
        raise ValueError("Input JSON must be a list of delivery objects.")

    required_fields = {"id", "area", "priority", "weight_kg"}

    """Case where we might not have full delivery objects in the input JSON, we raise an error and show the missing fields"""
    for i, item in enumerate(data):
        missing = required_fields - item.keys()
        if missing:
            raise ValueError(f"Delivery at index {i} is missing fields: {missing}")

    return data


def split_valid_and_oversized(deliveries, capacity):
    """ Suppose we have a list of deliveries that are above the allowed capacity, although
    the capacity could be calibrated, but still assuming that the capacity is fixed.

    we need to consider cases where we might have deliveries that are above the allowed capacity.

    Separate deliveries that can never fit a trip (weight > capacity)
    from the ones that are valid candidates for planning.

    split_valid_and_oversized: a single package heavier than the vehicle capacity can never
    be transported in one trip under the "never exceed capacity" rule, so
    it is reported separately as "unassignable", making sure they aren't silently
    dropped (as in the problem of low priority tasks when scheduled by the OS, since they have a low priority , they might not even be considered )
    or forced into an over-capacity trip.
    """
    valid, oversized = [], []
    for item in deliveries:
        if item["weight_kg"] > capacity:
            oversized.append(item)
        else:
            valid.append(item)
    return valid, oversized


# Main algorithm (planning Section): sort by priority, then group into trips

def sort_by_priority(deliveries):
    """Sort deliveries by priority ascending (1 = most urgent first).

    Deliveries that share the same priority keep their original
    relative order (effectively the order they appeared in the input file) [from Python Implementation of sort].
    This is the documented tie-breaking rule for the "multiple deliveries,
    same priority" edge case.
    """

    """lambda function is used to extract the priority value from each delivery dictionary,
    and the sorted function sorts the deliveries based on that
    priority value in ascending order."""

    return sorted(deliveries, key=lambda d: d["priority"])


def plan_trips(deliveries, capacity=DEFAULT_CAPACITY_KG):
    """Group deliveries into trips.

    Algorithm (matches the approach described in the assignment):
      1. Sort every delivery by priority, most urgent first.

      2. Take that ordered list as a working queue ("remaining"), thus lowest priority is first
      to be popped from the queue.

      3. To build a trip: pop the first (most urgent remaining) delivery
         and make it the trip's "current_package" - this fixes the trip's area
         AND fixes a single "target priority" equal to `current_package priority
         + Priority_Added_to_trip` for this trip.

         Thus instead of grouping all deliveries of the same area together, we only group
         the current_package with deliveries of the same area that sit at exactly at the Priority_Added_to_trip.

         Thus if Priority_Added_to_trip is 1 , and current_package is at priority 1 as well , we will only
         consider deliveries of the same area that are at priority 2 for this trip, and not any other priority level.


      4. Scan "remaining" looking for a delivery in the SAME area whose
         priority is exactly the target priority (current_package + Priority_Added_to_trip).

         - If one is found and adding it keeps the trip at or under
           capacity, remove it from "remaining" and add it to the trip.

         - If it would push the trip over capacity, leave it and keep
           checking for any *other* delivery that also happens to sit at
           that exact target priority in that area ("go check the other
           one and so on").

      5. Repeat step 4 (re-scanning from the top after every successful
         addition) until either the vehicle is full or there is no more
         same-area delivery left at the target priority.


      6. After considering all same-area deliveries at the target priority, if the trip is still under capacity,
         consider the next highest priority delivery in the remaining list, regardless of area, and see if it can fit in the trip.

      7. Close the trip since that the capacity for the vehicle have been reached.
        Start a new trip with whichever delivery is now at the front of
         "remaining" - the next most urgent delivery overall, which may
         belong to a different area entirely ("continue to check the
         next-highest priority of another area").

      8. Repeat until "remaining" is empty.

    This keeps urgent deliveries first, and only ever pairs an current_package
    with an immediate-next-priority delivery in the same area - it
    deliberately does NOT reach further down an area's priority list to
    "settle" for a less urgent match when the immediate next priority
    isn't available, since a big priority gap is treated as too large a
    difference in urgency to justify grouping together.
    """

    """Deepcopy is used to create a new list of deliveries that is independent of the original list,
    so that any modifications made to the remaining list do not affect the original deliveries list."""

    remaining = sort_by_priority(deepcopy(deliveries))
    trips = []

    while remaining:
        current_package = remaining.pop(0)
        trip_items = [current_package]
        trip_weight = current_package["weight_kg"]
        area = current_package["area"]
        target_priority = current_package["priority"] + Priority_Added_to_trip  # fixed for this whole trip

        # Keep trying to pull in same-area deliveries that sit at exactly
        # the target priority, until nothing more fits / nothing more is
        # left at that priority level. The target never advances past
        # `current_package priority + 1` - this trip does not chain further.
        added_something = True
        while added_something:
            added_something = False
            for idx, candidate in enumerate(remaining):
                if candidate["area"] != area:
                    continue
                if candidate["priority"] != target_priority:
                    continue
                if trip_weight + candidate["weight_kg"] <= capacity:
                    remaining.pop(idx)
                    trip_items.append(candidate)
                    trip_weight += candidate["weight_kg"]
                    added_something = True
                    break  # restart the scan from the top of `remaining`
                # else: this candidate is at the right target priority
                # but too heavy - keep checking other candidates at that
                # same exact priority further down the list.

            """ After considering all same-area deliveries at the target priority,
            if the trip is still under capacity, consider the next highest priority delivery
            in the remaining list, regardless of area, and see if it can fit in the trip. """

            for idx, candidate in enumerate(remaining):
                if candidate["weight_kg"] + trip_weight <= capacity:
                    trip_items.append(remaining.pop(idx))
                    trip_weight += candidate["weight_kg"]
                    added_something = True
                    break

        trips.append({
            "trip_number": len(trips) + 1,
            "area": area,
            "total_weight_kg": round(trip_weight, 2),
            "deliveries": trip_items,
        })

    return trips


# Reporting Section at which we provide the final report in the terminal (or optionally write it to a JSON file)

def print_report(trips, oversized, capacity):
    if not trips and not oversized:
        print("No deliveries to plan.")
        return

    print(f"Vehicle capacity: {capacity} kg\n")

    if not trips:
        print("No deliveries could be planned into trips.")
    for trip in trips:
        ids = ", ".join(f"#{d['id']}" for d in trip["deliveries"])
        print(
            f"Trip {trip['trip_number']} "
            f"({trip['total_weight_kg']} kg)"
        )
        for d in trip["deliveries"]:
            print(
                f"    ID = {d['id']:<3} Priority = {d['priority']:<2} "
                f"Weight = {d['weight_kg']}kg"
                f"    Area={d['area']}"
            )

    if oversized:
        print("\nUnassignable deliveries (package exceeds vehicle capacity):")
        for d in oversized:
            print(
                f"    ID = {d['id']} Area = {d['area']} "
                f"Weight = {d['weight_kg']}kg > capacity {capacity}kg"
            )


def generate_driver_report(trips, path):
    """Write a plain-text, trip-by-trip checklist for the driver.

    One section per trip, stops listed in the order they should be
    delivered, each with a blank checkbox. Plain text on purpose - no
    app or spreadsheet software needed, easy to print or read on a
    phone screen between stops.
    """
    lines = ["DRIVER Report", "=" * 50]
    for trip in trips:
        areas = list(dict.fromkeys(d["area"] for d in trip["deliveries"]))
        lines.append("")
        lines.append(f"Trip {trip['trip_number']} - {', '.join(areas)} "
                     f"({trip['total_weight_kg']} kg)")
        lines.append("-" * 50)
        for stop_num, d in enumerate(trip["deliveries"], start=1):
            lines.append(
                f"[ ] Stop {stop_num}: #{d['id']:<3} {d['area']:<12} "
                f"priority {d['priority']}  ({d['weight_kg']} kg)"
            )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def generate_support_tracking(trips, oversized, path):
    """Write a CSV tracking sheet for customer support.

    One row per delivery (assigned or not), with which trip it's on, an
    SLA label derived from its priority, and a blank Status column
    support can fill in ("Delivered" / "Delayed") to check whether a
    delivery met the promise implied by its priority.
    """
    rows = []
    for trip in trips:
        for d in trip["deliveries"]:
            rows.append({
                "id": d["id"],
                "area": d["area"],
                "priority": d["priority"],
                "weight_kg": d["weight_kg"],
                "trip_number": trip["trip_number"],
                "sla": sla_label_for_priority(d["priority"]),
                "status": "Pending",
            })
    for d in oversized:
        rows.append({
            "id": d["id"],
            "area": d["area"],
            "priority": d["priority"],
            "weight_kg": d["weight_kg"],
            "trip_number": "UNASSIGNED",
            "sla": "N/A - exceeds vehicle capacity",
            "status": "Needs manual arrangement",
        })

    rows.sort(key=lambda r: r["priority"])

    fieldnames = ["id", "area", "priority", "weight_kg", "trip_number", "sla", "status"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Delivery Route Planner")
    parser.add_argument("input", help="Path to the input JSON file")
    parser.add_argument(
        "--capacity", type=float, default=DEFAULT_CAPACITY_KG,
        help=f"Vehicle capacity in kg (default: {DEFAULT_CAPACITY_KG})",
    )
    parser.add_argument(
        "--output", help="Optional path to write the resulting trips as JSON"
    )
    parser.add_argument(
        "--driver-report",
        help="Optional path to write a plain-text driver checklist (extension feature)",
    )
    parser.add_argument(
        "--support-tracking",
        help="Optional path to write a CSV tracking sheet for customer support (extension feature)",
    )
    args = parser.parse_args()

    try:
        deliveries = load_deliveries(args.input)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"Error reading input: {e}", file=sys.stderr)
        sys.exit(1)

    if not deliveries:
        print("No deliveries to plan.")
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump({"trips": [], "unassignable": []}, f, indent=2)
        return

    valid, oversized = split_valid_and_oversized(deliveries, args.capacity)
    trips = plan_trips(valid, args.capacity)

    print_report(trips, oversized, args.capacity)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"trips": trips, "unassignable": oversized}, f, indent=2)
        print(f"\nSaved trip plan to {args.output}")

    if args.driver_report:
        generate_driver_report(trips, args.driver_report)
        print(f"Saved driver report to {args.driver_report}")

    if args.support_tracking:
        generate_support_tracking(trips, oversized, args.support_tracking)
        print(f"Saved support tracking sheet to {args.support_tracking}")


if __name__ == "__main__":
    main()
