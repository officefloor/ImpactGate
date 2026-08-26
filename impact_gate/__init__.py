"""impact-gate — report the change-impact of a change and gate on it.

A lightweight front-end over the change-impact measure (shared, single-sourced with
Surveyor / the PetClinic-Evolve harness). It scores a change against a base — a
committed range vs `main`, staged changes, or the working tree — reports the number,
and warns or blocks when the impact is too high.
"""
__version__ = "0.1.0"
