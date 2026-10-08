#!/usr/bin/env python3
"""Sign, snapshot and deploy a public Flatpak repository without source code."""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\+([1-9]\d*)$")
MAXIMUM_SITE_BYTES = 950 * 1024 * 1024


def run(*arguments, **options):
    """Execute argument vectors without a shell or credential logging."""
    return subprocess.run([str(value) for value in arguments], check=True, **options)


def config():
    """Load the public installation contract and its pinned signing key."""
    value = json.loads((ROOT / "repository.json").read_text())
    if (
        value["baseUrl"] != "https://flatpak.focale-editor.app"
        or value["branch"] != "stable"
    ):
        raise ValueError("Unexpected Flatpak publication identity.")
    return value


def write_json(path, value):
    """Write normalized release metadata beside the immutable snapshot."""
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(path):
    """Hash large snapshots with bounded memory."""
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def public_fingerprint(key):
    """Check the exact primary key, rather than accepting another valid signer."""
    result = run(
        "gpg",
        "--batch",
        "--with-colons",
        "--import-options",
        "show-only",
        "--import",
        key,
        capture_output=True,
        text=True,
    )
    fingerprints = [
        line.split(":")[9]
        for line in result.stdout.splitlines()
        if line.startswith("fpr:")
    ]
    if not fingerprints:
        raise ValueError("Missing public GPG key.")
    return fingerprints[0]


def validate_key(settings):
    """Require a committed public key matching the configured fingerprint."""
    key = ROOT / "focale-flatpak.asc"
    if (
        not settings.get("gpgFingerprint")
        or public_fingerprint(key) != settings["gpgFingerprint"]
    ):
        raise ValueError(
            "Configure the permanent Flatpak signing key before publication."
        )
    return key


def create_key(secrets):
    """Create the first signing identity; never replace an installed-client pin."""
    settings = config()
    if settings.get("gpgFingerprint") or (ROOT / "focale-flatpak.asc").exists():
        raise ValueError(
            "A signing identity already exists. Never regenerate it for a release."
        )
    secrets.mkdir(parents=True, exist_ok=True, mode=0o700)
    homedir = secrets / "gnupg"
    homedir.mkdir(mode=0o700)
    run(
        "gpg",
        "--batch",
        "--homedir",
        homedir,
        "--pinentry-mode",
        "loopback",
        "--passphrase",
        "",
        "--quick-generate-key",
        "Focale Flatpak <release@focale-editor.app>",
        "ed25519",
        "sign",
        "0",
        capture_output=True,
    )
    key = ROOT / "focale-flatpak.asc"
    exported = run(
        "gpg",
        "--batch",
        "--homedir",
        homedir,
        "--armor",
        "--export",
        capture_output=True,
    ).stdout
    key.write_bytes(exported)
    settings["gpgFingerprint"] = public_fingerprint(key)
    private = run(
        "gpg",
        "--batch",
        "--homedir",
        homedir,
        "--armor",
        "--export-secret-keys",
        settings["gpgFingerprint"],
        capture_output=True,
    ).stdout
    descriptor = os.open(
        secrets / "focale-flatpak-private.asc",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(private)
    write_json(ROOT / "repository.json", settings)
    print(
        "Public key and fingerprint prepared. Private backup: "
        + str(secrets / "focale-flatpak-private.asc")
    )


def verify_repository(repository, settings):
    """Verify the GPG-signed summary and app commit with the client's own tools."""
    key = validate_key(settings)
    with tempfile.TemporaryDirectory(prefix="focale-flatpak-verify-") as temporary:
        verifier = Path(temporary) / "repo"
        run(
            "ostree",
            f"--repo={verifier}",
            "init",
            "--mode=archive",
            capture_output=True,
        )
        run(
            "ostree",
            f"--repo={verifier}",
            "remote",
            "add",
            f"--gpg-import={key}",
            "--set=gpg-verify=true",
            "--set=gpg-verify-summary=true",
            "focale",
            repository.resolve().as_uri(),
            capture_output=True,
        )
        run(
            "ostree",
            f"--repo={verifier}",
            "remote",
            "summary",
            "focale",
            capture_output=True,
        )
        ref = application_ref(settings)
        run(
            "ostree",
            f"--repo={verifier}",
            "pull",
            "--depth=0",
            "--disable-static-deltas",
            "focale",
            ref,
            capture_output=True,
        )


def application_ref(settings):
    """Name the stable application ref, independently of AppStream refs."""
    return f"app/{settings['applicationId']}/{settings['architecture']}/{settings['branch']}"


def descriptors(destination, settings):
    """Embed the stable public key in software-center installation descriptors."""
    key = base64.b64encode(validate_key(settings).read_bytes()).decode()
    url = settings["baseUrl"].rstrip("/") + "/repo/"
    common = f"Title=Focale\nUrl={url}\nGPGKey={key}\n"
    (destination / "Focale.flatpakrepo").write_text(
        "[Flatpak Repo]\n" + common + "DefaultBranch=stable\n"
    )
    (destination / "Focale.flatpakref").write_text(
        "[Flatpak Ref]\n"
        + common
        + f"Name={settings['applicationId']}\nBranch={settings['branch']}\nIsRuntime=false\nSuggestRemoteName=focale\n"
        "RuntimeRepo=https://dl.flathub.org/repo/flathub.flatpakrepo\n"
    )
    (destination / "CNAME").write_text("flatpak.focale-editor.app\n")
    (destination / ".nojekyll").touch()
    (destination / "index.html").write_text("""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Focale — Flatpak repository</title>
<style>body{font:1rem system-ui;max-width:46rem;margin:4rem auto;padding:0 1.5rem;line-height:1.6;color:#181f33}a{color:#24528c}pre{padding:1rem;background:#f1f2f4;overflow:auto;border-radius:.5rem}</style>
<h1>Focale for Linux</h1><p>Install Focale with Flatpak. Your software center handles updates.</p>
<p><a href="Focale.flatpakref">Install Focale</a> · <a href="Focale.flatpakrepo">Add the repository</a> · <a href="https://focale-editor.app">Discover Focale</a></p>
<pre>flatpak install --user https://flatpak.focale-editor.app/Focale.flatpakref</pre>
<p>The package is designed for x86_64 systems and uses the Freedesktop runtime available on Flathub.</p></html>
""")


def assemble(source, output, version, tag, gpg_home, previous=None):
    """Keep prior commits, import the new app, sign and generate delta updates."""
    settings = config()
    validate_key(settings)
    if not VERSION.fullmatch(version) or tag.removeprefix("v") != version.split("+")[0]:
        raise ValueError("Tag and source version do not match.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty output directory.")
    output.mkdir(parents=True, exist_ok=True)
    repository = output / "repo"
    if previous:
        verify_repository(previous, settings)
        shutil.copytree(previous, repository)
    else:
        run(
            "ostree",
            f"--repo={repository}",
            "init",
            "--mode=archive",
            capture_output=True,
        )
    ref = application_ref(settings)
    run(
        "flatpak",
        "build-commit-from",
        f"--src-repo={source}",
        f"--src-ref={ref}",
        "--untrusted",
        "--force",
        "--no-update-summary",
        f"--gpg-sign={settings['gpgFingerprint']}",
        f"--gpg-homedir={gpg_home}",
        repository,
        ref,
        capture_output=True,
    )
    run(
        "flatpak",
        "build-update-repo",
        "--generate-static-deltas",
        "--static-delta-jobs=2",
        "--prune",
        "--prune-depth=2",
        "--default-branch=stable",
        "--title=Focale",
        "--homepage=https://focale-editor.app",
        f"--gpg-sign={settings['gpgFingerprint']}",
        f"--gpg-homedir={gpg_home}",
        repository,
        capture_output=True,
    )
    verify_repository(repository, settings)
    if (
        sum(path.stat().st_size for path in repository.rglob("*") if path.is_file())
        > MAXIMUM_SITE_BYTES
    ):
        raise ValueError(
            "Flatpak repository exceeds the GitHub Pages size budget; change hosting before publication."
        )
    commit = run(
        "ostree",
        f"--repo={repository}",
        "rev-parse",
        ref,
        capture_output=True,
        text=True,
    ).stdout.strip()
    archive = output / f"focale-{version.split('+')[0]}-flatpak.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(repository, arcname="repo")
    write_json(
        output / "snapshot.json",
        {
            "version": version,
            "tag": tag,
            "archive": archive.name,
            "sha256": digest(archive),
            "gpgFingerprint": settings["gpgFingerprint"],
            "ref": ref,
            "commit": commit,
        },
    )
    return archive


def release_snapshot(directory, tag):
    """Resolve current or legacy release assets before downloading a snapshot."""
    if not re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag):
        raise ValueError("Invalid Flatpak release tag.")
    version = tag.removeprefix("v")
    candidates = [directory / f"focale-{version}-flatpak.json", directory / "snapshot.json"]
    matches = [path for path in candidates if path.is_file()]
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous Flatpak snapshot metadata.")
    metadata = matches[0]
    info = json.loads(metadata.read_text())
    if not VERSION.fullmatch(info["version"]) or info["tag"] != tag or info["version"].split("+")[0] != version:
        raise ValueError("Snapshot tag mismatch.")
    if info["archive"] not in (f"focale-{version}-flatpak.tar.gz", f"Focale-flatpak-{info['version']}.tar.gz"):
        raise ValueError("Unsafe release asset name.")
    return metadata, info["archive"]


def stage(snapshot, metadata, destination):
    """Verify an immutable release snapshot before generating the Pages site."""
    settings = config()
    info = json.loads(metadata.read_text())
    if (
        not VERSION.fullmatch(info["version"])
        or info["gpgFingerprint"] != settings["gpgFingerprint"]
    ):
        raise ValueError("Unexpected snapshot version or signing identity.")
    if info["archive"] != snapshot.name or info["sha256"] != digest(snapshot):
        raise ValueError("Snapshot SHA-256 mismatch.")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Use an empty site directory.")
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(snapshot) as stream:
        members = stream.getmembers()
        if (
            len(members) > 200000
            or sum(member.size for member in members) > MAXIMUM_SITE_BYTES
        ):
            raise ValueError("Snapshot exceeds the Pages size budget.")
        for member in members:
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] != "repo"
            ):
                raise ValueError("Unsafe repository snapshot path.")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Links/devices are forbidden in repository snapshots.")
        stream.extractall(destination, members=members, filter="data")
    verify_repository(destination / "repo", settings)
    ref = application_ref(settings)
    actual = run(
        "ostree",
        f"--repo={destination / 'repo'}",
        "rev-parse",
        ref,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if info["ref"] != ref or info["commit"] != actual:
        raise ValueError("Snapshot application commit mismatch.")
    descriptors(destination, settings)
    shutil.copy2(metadata, destination / "snapshot.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("create-key")
    setup.add_argument("--secrets-dir", type=Path, required=True)
    build = commands.add_parser("assemble")
    for name in ("input", "output", "gpg-home"):
        build.add_argument("--" + name, type=Path, required=True)
    build.add_argument("--previous", type=Path)
    build.add_argument("--version", required=True)
    build.add_argument("--tag", required=True)
    deploy = commands.add_parser("stage")
    deploy.add_argument("--snapshot", type=Path, required=True)
    deploy.add_argument("--metadata", type=Path, required=True)
    deploy.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "create-key":
        create_key(args.secrets_dir.resolve())
    elif args.command == "assemble":
        assemble(
            args.input.resolve(),
            args.output.resolve(),
            args.version,
            args.tag,
            args.gpg_home.resolve(),
            args.previous.resolve() if args.previous else None,
        )
    elif args.command == "stage":
        stage(args.snapshot.resolve(), args.metadata.resolve(), args.output.resolve())
