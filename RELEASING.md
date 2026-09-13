# Releasing impact-gate

Distribution is fully automated by `.github/workflows/release.yml`. Pushing a
version tag builds and publishes everything; the steps below cover the tag scheme,
the one-time setup each channel needs, and how to promote the Action to the
Marketplace.

## Version scheme

- Full version tags are `vMAJOR.MINOR.PATCH`, e.g. `v0.1.0`. These are the tags you
  push; they trigger the release.
- The release moves a floating major tag (`v0`, `v1`, ...) to the newest release on
  that major. Consumers of the Action pin to the major: `officefloor/ImpactGate@v0`.
- The package version is single-sourced from `impact_gate/__init__.py` (`__version__`);
  `pyproject.toml` reads it dynamically. Bump it there before tagging, and keep the tag
  in sync with it (`v0.1.0` <-> `__version__ = "0.1.0"`). The release workflow enforces
  this: it fails fast if the pushed tag does not equal `v<__version__>`, so a mismatched
  release cannot publish. (PyPI publishes are also `skip-existing`, so re-running a
  release on an already-published version is a no-op rather than a failure.)

## One-time setup

### PyPI trusted publishing (no API token)

The `pypi` job authenticates over OIDC, so there is no token secret to manage. Configure
the publisher once, before the first release:

1. Go to https://pypi.org/manage/account/publishing/ (create the `impact-gate` project
   first if it does not exist yet, or add it as a pending publisher).
2. Add a GitHub publisher: owner `officefloor`, repository `ImpactGate`,
   workflow `release.yml`, environment `pypi`.
3. In this repo's Settings > Environments, create an environment named `pypi`
   (optionally require a reviewer to approve each publish).

### GHCR (Docker image)

No setup: the `docker` job pushes to `ghcr.io/officefloor/impact-gate` using the
built-in `GITHUB_TOKEN`. After the first push, make the package public in the repo's
Packages settings if anonymous `docker pull` is wanted.

## Cutting a release

```bash
# 1. Bump the version in impact_gate/__init__.py, commit it.
# 2. Tag and push.
git tag v0.1.0
git push origin v0.1.0
```

That one push runs the release workflow, which:

- builds the sdist + wheel and publishes them to PyPI (`pip install impact-gate`);
- builds and pushes the Docker image tagged `0.1.0`, `0.1`, `0`, and `latest`;
- moves the `v0` tag to this commit so `officefloor/ImpactGate@v0` resolves to it.

For a first release, cut `v0` for pinning:

```bash
git tag v0.1.0 && git push origin v0.1.0   # workflow also creates/moves v0
```

## GitHub Marketplace (the Action)

Publishing to the Marketplace is a manual GitHub UI step and only needs doing once:

1. Confirm the `name:` in `action.yml` is unique across the Marketplace (names are
   global). `impact-gate` is the current name; change it if it is taken.
2. Draft a GitHub Release for the version tag. GitHub shows a "Publish this Action to
   the GitHub Marketplace" checkbox — tick it, pick a category (e.g. Code quality),
   and accept the agreement. `branding.icon`/`branding.color` in `action.yml` are
   already set (`activity` / `purple`).
3. Publish the release. Later releases update the listing automatically.
