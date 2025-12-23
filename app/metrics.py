from prometheus_client import Counter

dispatch_attempts = Counter(
    "dispatch_attempts_total",
    "Total dispatch attempts",
)

dispatch_success = Counter(
    "dispatch_success_total",
    "Successful dispatches",
)

dispatch_failure = Counter(
    "dispatch_failure_total",
    "Failed dispatches",
)
