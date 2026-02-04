AGE_BOOST_PER_SEC = 0.015   # priority gain per second waiting
MAX_BOOST = 40.0

def effective_priority(priority, created_ts):
    age = now_ts() - created_ts
    boost = min(age * AGE_BOOST_PER_SEC, MAX_BOOST)
    return priority + boost


def fair_pick(rows, quotas):
    counts = {}
    eligible = []

    for r in rows:
        src = r["source"] or "reddit"
        counts.setdefault(src, 0)

        if counts[src] < quotas.get(src, 1):
            eligible.append(r)
            counts[src] += 1

    if not eligible:
        return rows[0]

    return max(
        eligible,
        key=lambda r: effective_priority(r["priority"], r["created_ts"])
    )
