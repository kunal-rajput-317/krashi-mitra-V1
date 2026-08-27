"""The net-price calculator's "and who will haul it" panel.

/bhav/net-price makes a farmer pick a vehicle and then costs the trip in it.
That vehicle is a machine in the /rental registry, so the panel under the
answer is the owners of *that* machine, nearest to *this* farmer.

Three claims are asserted here, because all three fail silently:

* **The tier → machine mapping cannot rot.** Every vehicle in the picker must
  name a slug the registry actually carries; a renamed machine would otherwise
  link every farmer into a 404 and nothing would raise.
* **Ordering is distance and nothing else.** Inherited from services/rental.py,
  where it is the one rule the directory refuses to sell. Reached from the
  outside, it is just as easy to break — hence a cheap-but-far owner must lose
  to a dearer-but-near one here too.
* **The panel can never take the answer down.** नेट भाव is what this endpoint
  owes the farmer; the owner list is a bonus. A dropped machine, a lapsed
  owner or a database that is down must cost the panel and nothing else.
"""

from datetime import datetime, timedelta

import pytest

from backend.database.db import RentalListing, RentalProvider
from backend.routes import bhav
from backend.services import freight, rental


# Bareilly-ish; the two owners below sit at known distances from it.
FARMER_LAT, FARMER_LON = 28.36, 79.43


def _provider(db, slug, name, lat, lon, **kw):
    row = RentalProvider(slug=slug, name=name, district="Bareilly",
                         state="Uttar Pradesh", phone="9870951001", kind="owner",
                         plan="season", plan_months=3, active=True,
                         lat=lat, lon=lon, **kw)
    db.add(row)
    return row


@pytest.fixture()
def hauliers(db_session):
    """Two live trolley owners: one near and dear, one far and cheap."""
    stamp = datetime.utcnow().strftime("%H%M%S%f")
    near, far = f"haul-near-{stamp}", f"haul-far-{stamp}"

    _provider(db_session, near, "Pass Wala Trolley", 28.40, 79.45)
    _provider(db_session, far, "Door Wala Trolley", 29.20, 79.90)
    db_session.add(RentalListing(provider_slug=near, equipment_slug="tractor-trolley",
                                 rate=1400, rate_unit_hi="प्रति ट्रिप",
                                 active=True, available=True))
    db_session.add(RentalListing(provider_slug=far, equipment_slug="tractor-trolley",
                                 rate=900, rate_unit_hi="प्रति ट्रिप",
                                 active=True, available=True))
    db_session.commit()
    yield {"near": near, "far": far}

    db_session.rollback()
    db_session.query(RentalListing).filter(
        RentalListing.provider_slug.in_([near, far])).delete(synchronize_session=False)
    db_session.query(RentalProvider).filter(
        RentalProvider.slug.in_([near, far])).delete(synchronize_session=False)
    db_session.commit()


# ── the mapping ─────────────────────────────────────────────

@pytest.mark.parametrize("tier", sorted(freight.tiers()))
def test_every_vehicle_tier_names_a_real_machine(tier):
    """Rename a machine's slug and this is the test that says so — before a
    farmer taps the link and lands on a 404 nobody hears about."""
    slug = freight.rental_slug(tier)
    assert slug, f"freight tier {tier!r} names no /rental machine"
    assert rental.by_slug(slug), f"tier {tier!r} → unknown machine {slug!r}"


def test_every_haulage_machine_is_reachable_from_the_calculator():
    """The other direction: the vehicles the calculator offers and the machines
    the registry files under haulage are the same set, minus the JCB — which is
    a digger, not a way to get a crop to a mandi."""
    haulage = {e["slug"] for e in rental.equipment() if e["cat"] == "haulage"}
    offered = {freight.rental_slug(t) for t in freight.tiers()}
    assert offered <= haulage
    assert haulage - offered == {"jcb"}


def test_a_calculator_link_is_not_labelled_as_an_article():
    """The haulage rows send the farmer to /bhav/net-price, not to a guide. A
    button that says "पूरा लेख पढ़ें" and opens a calculator is caught on the
    tap — so every non-article target must carry its own label."""
    from backend.routes import rental as rental_route

    for e in rental.equipment():
        target = e.get("article") or ""
        if target and not target.startswith("/articles/"):
            assert target in rental_route._CTA_LABELS,                 f"{e['slug']}: {target} has no CTA label and is not an article"


# ── what the farmer sees ────────────────────────────────────

def test_owners_are_ranked_by_distance_not_by_price(hauliers):
    """The cheaper owner is 90km away. He still comes second."""
    html = bhav._haul_html("trolley", FARMER_LAT, FARMER_LON)
    assert html.index(hauliers["near"]) < html.index(hauliers["far"])


def test_panel_links_into_rental_and_names_the_owner(hauliers):
    html = bhav._haul_html("trolley", FARMER_LAT, FARMER_LON)
    assert f'href="/rental/tractor-trolley/{hauliers["near"]}"' in html
    assert "Pass Wala Trolley" in html
    assert 'href="/rental/tractor-trolley"' in html      # "सभी मालिक" link


def test_a_lapsed_owner_is_not_offered_a_trip(db_session, hauliers):
    """The listing fee's whole claim: money stops, the row stops being rendered
    — including here, one page away from where it was sold."""
    row = rental.provider_get(db_session, hauliers["near"])
    row.paid_until = datetime.utcnow() - timedelta(days=1)
    db_session.commit()

    html = bhav._haul_html("trolley", FARMER_LAT, FARMER_LON)
    assert hauliers["near"] not in html
    assert hauliers["far"] in html


def test_no_owners_still_answers_where_to_get_one():
    """A vehicle nobody has listed yet: the panel must not go blank, because
    /rental still says what the haul should cost and routes to a govt CHC."""
    html = bhav._haul_html("truck", FARMER_LAT, FARMER_LON)
    assert 'href="/rental/truck"' in html
    assert "np-haul-lone" in html
    assert "np-haul-row" not in html        # never implies an owner exists


# ── it can never take the answer down ───────────────────────

def test_a_dead_database_never_reaches_the_farmer(monkeypatch, hauliers):
    """It must not raise, and it must not turn a failed lookup into the claim
    that nobody hires a trolley out — so it falls back to the one line that is
    true with or without a database, naming no owner at all."""
    def boom(*a, **kw):
        raise RuntimeError("database is down")
    monkeypatch.setattr(bhav.rental_svc, "offers_for_equipment", boom)

    html = bhav._haul_html("trolley", FARMER_LAT, FARMER_LON)
    assert 'href="/rental/tractor-trolley"' in html
    assert "np-haul-row" not in html
    assert hauliers["near"] not in html


def test_a_machine_dropped_from_the_registry_renders_nothing(monkeypatch):
    monkeypatch.setattr(bhav.freight, "rental_slug", lambda tier: "no-such-machine")
    assert bhav._haul_html("trolley", FARMER_LAT, FARMER_LON) == ""


def test_the_net_price_answer_survives_without_the_panel():
    """_net_price_html's contract: haul is optional and the ranking is not."""
    ranked = [{"market": "Bareilly", "district": "Bareilly", "state": "Uttar Pradesh",
               "ss": "uttar-pradesh", "ds": "bareilly", "modal": 2400,
               "freight_per_q": 40, "net_per_q": 2360, "distance_km": 12.0}]
    html = bhav._net_price_html("wheat", "गेहूँ", ranked, 20, "trolley")
    assert "np-list" in html and "np-haul" not in html
