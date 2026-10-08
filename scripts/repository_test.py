"""Exercise real OSTree signing, incremental updates and safe Pages snapshots."""

import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import repository as repo


class ReleaseAssetTests(unittest.TestCase):
    """Keep new and previously published snapshots deployable through Pages."""

    def test_current_and_legacy_assets_with_both_tag_spellings(self):
        for tag in ('1.2.3', 'v1.2.3'):
            for metadata_name, archive_name in (
                ('focale-1.2.3-flatpak.json', 'focale-1.2.3-flatpak.tar.gz'),
                ('snapshot.json', 'Focale-flatpak-1.2.3+4.tar.gz'),
            ):
                with self.subTest(tag=tag, name=metadata_name), tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    metadata = directory / metadata_name
                    repo.write_json(metadata, {'version': '1.2.3+4', 'tag': tag, 'archive': archive_name})
                    self.assertEqual(repo.release_snapshot(directory, tag), (metadata, archive_name))

    def test_invalid_version_and_archive_identity_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            metadata = directory / 'focale-1.2.3-flatpak.json'
            identity = {'version': '1.2.3+4', 'tag': '1.2.3', 'archive': 'focale-1.2.3-flatpak.tar.gz'}
            for changes in ({'version': '1.2.4+4'}, {'tag': '1.2.4'},
                            {'archive': '../focale-1.2.3-flatpak.tar.gz'},
                            {'archive': 'focale-1.2.4-flatpak.tar.gz'},
                            {'archive': 'Focale-flatpak-1.2.3+5.tar.gz'}):
                with self.subTest(changes=changes):
                    repo.write_json(metadata, {**identity, **changes})
                    with self.assertRaises(ValueError):
                        repo.release_snapshot(directory, '1.2.3')

    def test_missing_or_competing_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'Missing'):
                repo.release_snapshot(directory, '1.2.3')
            for name in ('snapshot.json', 'focale-1.2.3-flatpak.json'):
                (directory / name).write_text('{}')
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                repo.release_snapshot(directory, '1.2.3')


class RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.root = Path(cls.workspace.name)
        cls.public = cls.root / "public"
        cls.public.mkdir()
        settings = json.loads((repo.ROOT / "repository.json").read_text())
        settings["gpgFingerprint"] = None
        repo.write_json(cls.public / "repository.json", settings)
        cls.root_patch = patch.object(repo, "ROOT", cls.public)
        cls.root_patch.start()
        cls.secrets = cls.root / "secrets"
        repo.create_key(cls.secrets)
        cls.home = cls.secrets / "gnupg"
        cls.settings = repo.config()

    @classmethod
    def tearDownClass(cls):
        cls.root_patch.stop()
        cls.workspace.cleanup()

    def source(self, directory, value):
        build = directory / "build"
        binary = build / "files/bin/focale"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\necho " + value + "\n")
        binary.chmod(0o755)
        (build / "metadata").write_text(
            "[Application]\nname=app.focaleeditor.Focale\n"
            "runtime=org.freedesktop.Platform/x86_64/25.08\nsdk=org.freedesktop.Sdk/x86_64/25.08\ncommand=focale\n"
        )
        repo.run(
            "flatpak", "build-finish", "--command=focale", build, capture_output=True
        )
        source = directory / "unsigned"
        repo.run(
            "flatpak",
            "build-export",
            "--arch=x86_64",
            "--no-update-summary",
            source,
            build,
            "stable",
            capture_output=True,
        )
        return source

    def test_real_signed_repository_preserves_parent_and_supports_client_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = repo.assemble(
                self.source(root / "one", "one"),
                root / "first",
                "1.0.0+1",
                "1.0.0",
                self.home,
            )
            self.assertEqual(first.name, 'focale-1.0.0-flatpak.tar.gz')
            site = root / "site-one"
            repo.stage(first, first.parent / "snapshot.json", site)
            descriptors = (site / "Focale.flatpakref").read_text()
            self.assertIn("https://flatpak.focale-editor.app/repo/", descriptors)
            self.assertIn("GPGKey=", descriptors)
            self.assertEqual(
                (site / "CNAME").read_text(), "flatpak.focale-editor.app\n"
            )
            old = json.loads((first.parent / "snapshot.json").read_text())["commit"]
            second = repo.assemble(
                self.source(root / "two", "two"),
                root / "second",
                "1.1.0+2",
                "1.1.0",
                self.home,
                site / "repo",
            )
            self.assertEqual(second.name, 'focale-1.1.0-flatpak.tar.gz')
            updated = root / "site-two"
            repo.stage(second, second.parent / "snapshot.json", updated)
            new = json.loads((second.parent / "snapshot.json").read_text())["commit"]
            self.assertNotEqual(old, new)
            history = repo.run(
                "ostree",
                f"--repo={updated / 'repo'}",
                "log",
                repo.application_ref(self.settings),
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn(old, history)
            deltas = repo.run(
                "ostree",
                f"--repo={updated / 'repo'}",
                "static-delta",
                "list",
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn(old + "-" + new, deltas)
            descriptor = site / "Focale.flatpakrepo"
            descriptor.write_text(
                descriptor.read_text().replace(
                    self.settings["baseUrl"] + "/repo/", (site / "repo").as_uri()
                )
            )
            environment = {
                **os.environ,
                "FLATPAK_USER_DIR": str(root / "flatpak-installation"),
            }
            repo.run(
                "flatpak",
                "remote-add",
                "--user",
                "--from",
                "focale",
                descriptor,
                env=environment,
                capture_output=True,
            )
            repo.run(
                "flatpak",
                "install",
                "--user",
                "--noninteractive",
                "--no-deps",
                "--no-related",
                "focale",
                "app.focaleeditor.Focale//stable",
                env=environment,
                capture_output=True,
            )
            installed = repo.run(
                "flatpak",
                "info",
                "--user",
                "--show-commit",
                "app.focaleeditor.Focale",
                env=environment,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(installed, old)
            repo.run(
                "flatpak",
                "remote-modify",
                "--user",
                "--url=" + (updated / "repo").as_uri(),
                "focale",
                env=environment,
                capture_output=True,
            )
            repo.run(
                "flatpak",
                "update",
                "--user",
                "--noninteractive",
                "--no-deps",
                "--no-related",
                "app.focaleeditor.Focale",
                env=environment,
                capture_output=True,
            )
            installed = repo.run(
                "flatpak",
                "info",
                "--user",
                "--show-commit",
                "app.focaleeditor.Focale",
                env=environment,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(installed, new)
            # A client pinned to our key accepts the new commit and its file tree.
            client = root / "client"
            repo.run(
                "ostree",
                f"--repo={client}",
                "init",
                "--mode=archive",
                capture_output=True,
            )
            repo.run(
                "ostree",
                f"--repo={client}",
                "remote",
                "add",
                f"--gpg-import={self.public / 'focale-flatpak.asc'}",
                "--set=gpg-verify-summary=true",
                "focale",
                (site / "repo").as_uri(),
                capture_output=True,
            )
            repo.run(
                "ostree",
                f"--repo={client}",
                "pull",
                "focale",
                repo.application_ref(self.settings),
                capture_output=True,
            )
            repo.run(
                "ostree",
                f"--repo={client}",
                "remote",
                "delete",
                "focale",
                capture_output=True,
            )
            repo.run(
                "ostree",
                f"--repo={client}",
                "remote",
                "add",
                f"--gpg-import={self.public / 'focale-flatpak.asc'}",
                "--set=gpg-verify-summary=true",
                "focale",
                (updated / "repo").as_uri(),
                capture_output=True,
            )
            repo.run(
                "ostree",
                f"--repo={client}",
                "pull",
                "focale",
                repo.application_ref(self.settings),
                capture_output=True,
            )
            repo.run(
                "ostree",
                f"--repo={client}",
                "checkout",
                "--user-mode",
                new,
                root / "checked-out",
                capture_output=True,
            )
            self.assertIn(
                "echo two", (root / "checked-out/files/bin/focale").read_text()
            )

    def test_corrupted_summary_signature_is_rejected_by_the_client(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = repo.assemble(
                self.source(root / "source", "one"),
                root / "signed",
                "1.0.0+1",
                "1.0.0",
                self.home,
            )
            repository = archive.parent / "repo"
            (repository / "summary.sig").write_bytes(b"invalid signature")
            with self.assertRaises(subprocess.CalledProcessError):
                repo.verify_repository(repository, self.settings)

    def test_snapshot_checksum_and_archive_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                stream.addfile(tarfile.TarInfo("../outside"))
            metadata = root / "snapshot.json"
            repo.write_json(
                metadata,
                {
                    "version": "1.0.0+1",
                    "archive": archive.name,
                    "sha256": "wrong",
                    "gpgFingerprint": self.settings["gpgFingerprint"],
                },
            )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                repo.stage(archive, metadata, root / "checksum")
            value = json.loads(metadata.read_text())
            value["sha256"] = repo.digest(archive)
            repo.write_json(metadata, value)
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                repo.stage(archive, metadata, root / "traversal")
            self.assertFalse((root / "outside").exists())

    def test_stable_key_cannot_be_regenerated(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            repo.create_key(self.root / "another-secret")
        settings = {**self.settings, "gpgFingerprint": "0" * 40}
        with self.assertRaisesRegex(ValueError, "permanent"):
            repo.validate_key(settings)


if __name__ == "__main__":
    unittest.main()
