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
built-in `GITHUB_TOKEN`.

**The package must stay public.** The README's `docker run` example and the GitLab and
Jenkins templates (`ci/gitlab-ci.yml`, `ci/Jenkinsfile`) all pull
`ghcr.io/officefloor/impact-gate:0` anonymously; a private package breaks all of them
with an `unauthorized` error, while leaving `pip install impact-gate` unaffected. Make it
public once at
https://github.com/orgs/officefloor/packages/container/impact-gate/settings (Danger Zone
> Change visibility). This needs public packages to be allowed at the org level first
(https://github.com/organizations/officefloor/settings/packages), or the per-package
control is disabled. Verify after any release or org-policy change with an anonymous
pull:

```bash
docker logout ghcr.io
docker pull ghcr.io/officefloor/impact-gate:0
```

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

The release workflow already creates a GitHub Release for each tag (the `github-release`
job), and a Release is where the Marketplace listing lives. `action.yml` is
Marketplace-ready: `name: impact-gate` (verified free on the Marketplace as of the last
release), and `branding.icon`/`branding.color` are set (`activity` / `purple`, both in
GitHub's allowed set).

Listing the Action on the Marketplace is a one-time manual UI step (the "publish"
checkbox is not exposed to the API):

1. Open the auto-created Release for the current tag (Releases page) and click Edit.
   If the Marketplace checkbox does not appear, confirm `action.yml` is on the default
   branch and the `name:` is still unique (names are global; change it if taken).
2. Tick "Publish this Action to the GitHub Marketplace", accept the agreement, and pick
   a primary category (e.g. Code quality) and optional secondary one.
3. Update the Release. Every later release created by the workflow updates the listing
   automatically; the checkbox only has to be set this once.
