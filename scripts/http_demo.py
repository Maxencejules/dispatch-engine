"""Real HTTP proof against a fresh, dedicated demo database; no direct database writes."""

import argparse
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(base, method, path, payload=None, expected=200):
    body = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    message = Request(
        base.rstrip("/") + path,
        method=method,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(message, timeout=15) as response:
            status, body = response.status, response.read()
    except HTTPError as error:
        status, body = error.code, error.read()
    result = json.loads(body)
    assert status == expected, (method, path, status, result)
    return result


def stable(receipt):
    return {key: value for key, value in receipt.items() if key != "idempotent"}


def match(base, order_id, *, expected=200):
    return request(base, "POST", f"/dispatch/match?order_id={order_id}", expected=expected)


def create_order(base):
    return request(
        base,
        "POST",
        "/orders",
        dict(pickup_lat=43.65, pickup_lng=-79.38, dropoff_lat=43.70, dropoff_lng=-79.40),
    )["id"]


def run(base, path):
    assert request(base, "GET", "/health") == {"status": "ok"}
    courier = request(base, "POST", "/couriers", dict(lat=43.65, lng=-79.38, capacity=2))
    first = create_order(base)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: match(base, first), range(4)))
    assert sorted(result["idempotent"] for result in results) == [False, True, True, True]
    assert all(stable(result) == stable(results[0]) for result in results)
    assert results[0]["courier_id"] == courier["id"], "Use a fresh dedicated demo database"
    assert request(base, "GET", f"/couriers/{courier['id']}")["status"] == "available"
    second = match(base, create_order(base))
    assert second["courier_id"] == courier["id"]
    assert request(base, "GET", f"/couriers/{courier['id']}")["status"] == "assigned"
    unavailable = match(base, create_order(base), expected=409)
    assert unavailable["code"] == "no_couriers_available"
    # Setting a full courier available cannot erase its reserved capacity.
    request(base, "PATCH", f"/couriers/{courier['id']}/status?status=available")
    assert match(base, create_order(base), expected=409)["code"] == "no_couriers_available"
    request(base, "PATCH", f"/couriers/{courier['id']}/status?status=offline")
    spare = request(base, "POST", "/couriers", dict(lat=43.65, lng=-79.38, capacity=1))
    request(base, "PATCH", f"/couriers/{spare['id']}/status?status=offline")
    assert match(base, create_order(base), expected=409)["code"] == "no_couriers_available"
    location = request(
        base, "PATCH", f"/couriers/{courier['id']}/location", dict(lat=43.66, lng=-79.39)
    )
    assert location["last_seen_at"] > courier["last_seen_at"]
    assert (
        request(base, "POST", "/couriers", dict(lat=91, lng=0), expected=422)["code"]
        == "invalid_request"
    )
    assert match(base, "invalid", expected=422)["code"] == "invalid_request"
    assert match(base, str(uuid.uuid4()), expected=404)["code"] == "order_not_found"
    receipts = [stable(results[0]), stable(second)]
    assert all(receipt["explain"] is not None for receipt in receipts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipts, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("HTTP demo passed: parallel retry, two slots, over-capacity/offline and JSON failures")


def verify(base, path):
    receipts = json.loads(path.read_text(encoding="utf-8"))
    for original in receipts:
        replay = match(base, original["order_id"])
        assert replay["idempotent"] is True
        assert stable(replay) == original
    print(
        f"Restart proof passed: {len(receipts)} identical persisted receipts including explanation"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--receipts", type=Path, default=Path("reports/receipts.json"))
    parser.add_argument("--verify-receipts", action="store_true")
    arguments = parser.parse_args()
    (verify if arguments.verify_receipts else run)(arguments.base_url, arguments.receipts)
