"""Changes to saved ads, backed by what the platform shows.

A network error is never taken as evidence that a car was sold: only the platform saying so
(sold / removed / reserved) changes an ad's availability.
"""

import hashlib
import json

from common import COLOR_AR, color_of

FIELDS = {"price": "السعر", "title": "عنوان الإعلان", "year": "الموديل", "mileage": "الممشى", "color": "اللون",
          "location": "الموقع", "phone": "هاتف البائع", "vin": "رقم الشاصي"}
LABELS = {"available": "متاح", "sold": "مباع حسب المنصة", "unavailable": "الإعلان غير متاح",
          "reserved": "محجوز حسب المنصة"}
KEEP_ALERTS = 300


def _availability_from(status, values):
    if status == "sold":
        return "sold"
    if status == "gone":
        return "unavailable"
    return values.get("availability") or "available"


def _comparable(field, value):
    """Colours are compared by meaning ("White" and "أبيض" are the same)."""
    if field == "color":
        return COLOR_AR.get(color_of(str(value or "")), value)
    return value


def _field_changes(listing, values):
    changes = []
    for field, label in FIELDS.items():
        new = _comparable(field, values.get("km" if field == "mileage" else field))
        old = _comparable(field, listing.get(field))
        # A value missing on a freshly rendered page is not proof the seller edited it.
        if old in (None, "") or new in (None, ""):
            continue
        if str(old).strip() != str(new).strip():
            changes.append({"field": field, "label": label, "old": old, "new": new})
    return changes


def observe(eng, listing, status, values, at):
    """Record one re-read of a saved ad. Returns the alert events it produced (0 or 1)."""
    listing["last_check_attempt"] = at
    if status == "failed":
        listing["check_status"] = "unreachable"
        return []
    listing["check_status"] = "checked"

    old_avail = listing.get("availability") or ("unavailable" if listing.get("state") == "sold" else "available")
    new_avail = _availability_from(status, values)
    changes = []
    if old_avail != new_avail:
        changes.append({"field": "availability", "label": "حالة الإعلان", "old": old_avail, "new": new_avail})
    if status == "ok":
        changes += _field_changes(listing, values)

    listing["availability"] = new_avail
    if new_avail in ("sold", "unavailable"):
        if listing.get("state") != "sold":
            listing["last_active_state"] = listing.get("state", "unverified")
        listing.update(state="sold", note=LABELS[new_avail], last_checked=at)
    elif listing.get("state") == "sold":
        listing["state"] = listing.get("last_active_state", "unverified")

    if not changes:
        return []
    event = {"listing_id": listing["id"], "at": at, "title": listing.get("title") or "سيارة محفوظة",
             "url": listing["url"], "platform": listing["platform"], "changes": changes}
    event["id"] = hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    eng.setdefault("alerts", []).insert(0, event)
    eng["alerts"] = eng["alerts"][:KEEP_ALERTS]
    listing["last_changed_at"] = at
    return [event]


def _shown(value):
    return format(value, ",") if isinstance(value, (int, float)) else value


def message(events, site):
    """Notification text for a batch of changes."""
    lines = ["تحديثات السيارات المحفوظة"]
    for event in events[:30]:
        lines.append(event["title"])
        for c in event["changes"]:
            old, new = c["old"], c["new"]
            if c["field"] == "availability":
                old, new = LABELS.get(old, old), LABELS.get(new, new)
            lines.append(f"• {c['label']}: {_shown(old)} ← {_shown(new)}")
        lines.append(event["url"])
    if len(events) > 30:
        lines.append(f"وبقية التحديثات ({len(events) - 30}) في اللوحة")
    lines.append(site)
    return "\n".join(lines)
