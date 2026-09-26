"""Provider-independent match events (Phase 1, Increment B).

Planned contents, kept deliberately small for the attacking-side shift detector:

- ``ActionType``: a small enumeration of the actions the detector needs.
- ``Outcome``: whether an action was completed.
- ``Event``: identity and ordering, team, period and elapsed time, action type,
  start and end location, completion status, and the original provider record.

See ``docs/specs/phase-1-attacking-side-shift.md`` for the definitions these
types must support.
"""
