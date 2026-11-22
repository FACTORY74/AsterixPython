"""Minimal ASTERIX-to-Kody GeoJSON microservice.

FastAPI is an adapter dependency, not a core ASTERIX dependency. Production
code should load receiver and edition settings
from validated configuration rather than module constants.
"""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from asterix import DecodeContext, Decoder, SchemaRegistry
from asterix.normalize import TrackTermination, TrackUpdate, normalise
from examples.receive_udp import datagrams

GROUP = "239.1.2.3"
PORT = 8600
EDITIONS = {21: "2.7", 48: "1.32", 62: "1.21"}


class ActivityRequest(BaseModel):
    active: bool


@dataclass
class DisplayState:
    tracks: dict[str, TrackUpdate] = field(default_factory=dict)
    revision_number: int = 0
    active: bool = True
    last_error: str | None = None

    def apply(self, event: TrackUpdate | TrackTermination) -> None:
        if isinstance(event, TrackTermination):
            changed = self.tracks.pop(event.track_id, None) is not None
        else:
            previous = self.tracks.get(event.track_id)
            changed = previous != event
            self.tracks[event.track_id] = event
        if changed:
            self.revision_number += 1

    @property
    def revision(self) -> str:
        value = f"asterix-tracks:{self.revision_number}".encode()
        return hashlib.sha256(value).hexdigest()[:16]


state = DisplayState()


def track_feature(track: TrackUpdate) -> dict[str, Any]:
    """Project a normalised track into Kody's safe display contract."""
    return {
        "type": "Feature",
        "id": track.track_id,
        "geometry": {
            "type": "Point",
            "coordinates": [track.longitude_degrees, track.latitude_degrees],
        },
        "properties": {
            "trackId": track.track_id,
            "callsign": track.callsign,
            "altitudeFeet": track.altitude_feet,
            "groundSpeedKnots": track.ground_speed_knots,
            "headingDegrees": track.heading_degrees,
            "observedAt": track.observed_at.astimezone(UTC).isoformat(),
            "sourceCategory": track.provenance.category,
            "sourceEdition": track.provenance.edition,
            "kody": {
                "selectable": True,
                "selectionLabel": track.callsign or track.track_id,
            },
        },
    }


async def receive() -> None:
    decoder = Decoder(
        registry=SchemaRegistry.builtin(),
        context=DecodeContext(editions=EDITIONS, validation="compatible"),
    )
    while True:
        if not state.active:
            await asyncio.sleep(0.25)
            continue
        try:
            async for payload in datagrams(GROUP, PORT):
                if not state.active:
                    break
                for message in decoder.decode_datagram(payload):
                    for event in normalise(message):
                        if isinstance(event, (TrackUpdate, TrackTermination)):
                            state.apply(event)
                state.last_error = None
        except asyncio.CancelledError:
            raise
        except Exception as error:  # service boundary: retain health and retry
            state.last_error = f"receiver error: {type(error).__name__}"
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(receive(), name="asterix-receiver")
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="ASTERIX tracks for Kody", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/kody/manifest")
def manifest() -> dict[str, Any]:
    return {
        "kodyApiVersion": "1",
        "serviceId": "asterix-tracks",
        "displayName": "ASTERIX Tracks",
        "capabilities": {
            "dataLayer": {
                "kind": "geojson",
                "dataPath": "/api/data",
                "refreshSeconds": 1,
                "activityPath": "/api/activity",
            }
        },
    }


@app.get("/api/data")
def data() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "revision": state.revision,
        "features": [track_feature(track) for track in state.tracks.values()],
        "source": {
            "lastError": state.last_error,
            "generatedAt": datetime.now(UTC).isoformat(),
        },
    }


@app.post("/api/activity")
def activity(request: ActivityRequest) -> dict[str, bool]:
    state.active = request.active
    return {"active": state.active}
