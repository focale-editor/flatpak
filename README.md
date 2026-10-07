<p align="center">
  <a href="https://focale-editor.app">
    <img src="assets/branding/app_icon_512.png" alt="Focale app logo" width="112" height="112">
  </a>
</p>

<h1 align="center">Focale Flatpak</h1>

The official Flatpak distribution repository for [Focale](https://focale-editor.app),
a raster image editor. Install Focale on Linux and receive updates through Flatpak
or a compatible software center.

[Website](https://focale-editor.app) ·
[Releases](https://github.com/focale-editor/flatpak/releases) ·
[Community & support](https://github.com/focale-editor/community)

## Install

You need an **x86_64 Linux system** with Flatpak installed. See the
[Flatpak setup guide](https://flatpak.org/setup/) for your distribution.

Install Focale for your current user:

```bash
flatpak install --user https://flatpak.focale-editor.app/Focale.flatpakref
```

Follow the prompts to add the Focale remote and install the required runtime from
Flathub. Then open Focale from your application launcher, or run:

```bash
flatpak run app.focaleeditor.Focale
```

The package includes desktop integration for the application launcher, icons,
supported image formats, and `.focale` documents.

## Update or uninstall

Updates are delivered through Flatpak. Use your compatible software center or run:

```bash
flatpak update --user app.focaleeditor.Focale
```

To uninstall:

```bash
flatpak uninstall --user app.focaleeditor.Focale
```

These commands use the per-user installation created above. If you installed
Focale system-wide, use `--system` in place of `--user`.

## Package details

| Property | Value |
| --- | --- |
| Application ID | `app.focaleeditor.Focale` |
| Architecture | `x86_64` |
| Repository branch | `stable` |
| Runtime | Freedesktop 25.08, provided by Flathub |
| Repository URL | `https://flatpak.focale-editor.app/repo/` |

The `stable` branch identifies the Flatpak update channel; check the release notes
for the application's development status.

## About this repository

This repository contains the public distribution configuration, signing key, and
publication tools.

| File | Purpose |
| --- | --- |
| [`repository.json`](repository.json) | Repository URL, application ID, branch, architecture, and signing-key fingerprint. |
| [`focale-flatpak.asc`](focale-flatpak.asc) | Public GPG key used to verify the repository. |
| [`scripts/repository.py`](scripts/repository.py) | Assemble signed snapshots, verify them, and prepare the Pages site. |
| [`scripts/repository_test.py`](scripts/repository_test.py) | Integration tests for signatures, snapshots, and client updates. |
| [`.github/workflows/pages.yml`](.github/workflows/pages.yml) | Deploy a verified release snapshot to GitHub Pages. |

OSTree repository data and delta updates are stored as GitHub Release assets.
Each release contains `snapshot.json` and `Focale-flatpak-<version>.tar.gz`;
these generated files are not committed to Git.

## Publication and maintenance

The release pipeline imports each new build into the previous signed repository,
retains two levels of commit history, and generates delta updates. Published
snapshots are treated as immutable.

The Pages workflow takes a release tag, verifies the archive's SHA-256 checksum,
the GPG signatures on the repository summary and application commit, and the
expected application ref and commit. It then generates `Focale.flatpakref` and
`Focale.flatpakrepo` with the public key embedded and deploys the site. It refuses
to deploy a release other than the latest non-draft, non-prerelease release.

Keep the signing identity stable across releases: installed clients trust the
existing public key. Any key rotation needs an explicit migration plan. Private
signing keys must stay outside this repository, public release assets, and Pages.

The tooling enforces a **950 MiB limit on uncompressed repository files**, leaving
room for generated descriptors within the Pages site budget. If the application
and retained history outgrow this limit, move the repository to suitable hosting
before publishing.

### Local validation

On Linux, install **Python 3.12 or newer**, **Flatpak**, **OSTree**, and **GnuPG**.
Run the existing integration tests from the repository root:

```bash
python3 -m unittest discover -s scripts -p '*_test.py'
```

The tests create temporary repositories, signing keys, and a separate Flatpak
installation. They exercise signed test packages, commit history, delta updates,
client installation and updates, and rejection of invalid signatures or archives.

To verify and stage an existing release snapshot locally:

```bash
python3 scripts/repository.py stage \
  --snapshot build/Focale-flatpak-1.0.0+1.tar.gz \
  --metadata build/snapshot.json \
  --output site
```

Replace the example archive with the actual release asset and use its matching
`snapshot.json`. The output directory must be empty or absent. This command
verifies the snapshot and generates the site locally; it does not publish it.

## Support and feedback

Report installation, update, and application issues in
[Focale Community](https://github.com/focale-editor/community). Include your Focale
version, Linux distribution, Flatpak version (`flatpak --version`), the command or
action that failed, and the full error message.
