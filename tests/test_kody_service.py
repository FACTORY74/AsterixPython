from __future__ import annotations

from datetime import UTC, datetime, timedelta

from asterix import Provenance, TrackTermination, TrackUpdate
from examples.kody_tracks_service import DisplayState

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROVENANCE = Provenance(62, "1.21", 0)


def _update(track_id: str, observed_at: datetime) -> TrackUpdate:
    return TrackUpdate(track_id, 51.5, -0.1, observed_at, PROVENANCE)


def test_display_state_applies_explicit_termination() -> None:
    state = DisplayState()
    state.apply(_update("track", NOW))

    state.apply(TrackTermination("track", NOW + timedelta(seconds=1), PROVENANCE))

    assert state.tracks == {}
    assert state.revision_number == 2


def test_display_state_expires_stale_tracks() -> None:
    state = DisplayState(stale_after=timedelta(seconds=30))
    state.apply(_update("stale", NOW))
    state.apply(_update("current", NOW + timedelta(seconds=20)))

    state.expire(NOW + timedelta(seconds=31))

    assert set(state.tracks) == {"current"}
    assert state.revision_number == 3
