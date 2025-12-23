def test_create_courier_and_order_then_fetch(client):
    courier = client.post(
        "/couriers",
        json={"lat": 43.6532, "lng": -79.3832, "capacity": 2},
    )
    assert courier.status_code == 200
    courier_id = courier.json()["id"]

    got_courier = client.get(f"/couriers/{courier_id}")
    assert got_courier.status_code == 200
    assert got_courier.json()["id"] == courier_id

    order = client.post(
        "/orders",
        json={
            "pickup_lat": 43.6510,
            "pickup_lng": -79.3470,
            "dropoff_lat": 43.7000,
            "dropoff_lng": -79.4000,
        },
    )
    assert order.status_code == 200
    order_id = order.json()["id"]

    got_order = client.get(f"/orders/{order_id}")
    assert got_order.status_code == 200
    assert got_order.json()["id"] == order_id


def test_dispatch_match_is_idempotent(client):
    courier = client.post(
        "/couriers",
        json={"lat": 43.6532, "lng": -79.3832, "capacity": 1},
    )
    assert courier.status_code == 200

    order = client.post(
        "/orders",
        json={
            "pickup_lat": 43.6510,
            "pickup_lng": -79.3470,
            "dropoff_lat": 43.7000,
            "dropoff_lng": -79.4000,
        },
    )
    assert order.status_code == 200
    order_id = order.json()["id"]

    first = client.post(f"/dispatch/match?order_id={order_id}")
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["idempotent"] is False

    second = client.post(f"/dispatch/match?order_id={order_id}")
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["idempotent"] is True

    assert second_body["assignment_id"] == first_body["assignment_id"]
    assert second_body["courier_id"] == first_body["courier_id"]
