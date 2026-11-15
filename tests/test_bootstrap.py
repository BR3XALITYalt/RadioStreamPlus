import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from radiostream_bootstrap import (
    BootstrapError,
    extract_source_archive,
    install_source_archive,
    load_archive_cache,
    read_source_commit,
    source_is_complete,
)


COMMIT = "a" * 40


def make_archive(files, *, root="RadioStreamPlus-test"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(root + "/", b"")
        for filename, content in files.items():
            archive.writestr(root + "/" + filename, content)
    return output.getvalue()


def required_files():
    return {
        name: b"# test source\n"
        for name in (
            "radiostream.py",
            "radiostream_server.py",
            "radiostream_core.py",
            "index.html",
            "manage.html",
            "sdr.html",
            "app.js",
            "m.html",
            "maintenance.js",
            "radiostream.example.json",
        )
    }


class BootstrapTests(unittest.TestCase):
    def test_extracts_source_archive_into_target_directory(self):
        archive_data = make_archive(required_files())

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "source"
            extract_source_archive(archive_data, target)

            self.assertTrue(source_is_complete(target))
            self.assertEqual(
                (target / "radiostream.py").read_bytes(),
                b"# test source\n",
            )

    def test_rejects_path_traversal(self):
        files = required_files()
        files["../outside.txt"] = b"not allowed"
        archive_data = make_archive(files)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "source"
            with self.assertRaises(BootstrapError):
                extract_source_archive(archive_data, target)
            self.assertFalse((Path(directory) / "outside.txt").exists())

    def test_rejects_multiple_root_folders(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("RadioStreamPlus-a/radiostream.py", b"")
            archive.writestr("another-root/extra.txt", b"")

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(BootstrapError):
                extract_source_archive(output.getvalue(), Path(directory) / "source")

    def test_rejects_symbolic_links(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("RadioStreamPlus-test/", b"")
            entry = zipfile.ZipInfo("RadioStreamPlus-test/link")
            entry.create_system = 3
            entry.external_attr = (0o120777 << 16)
            archive.writestr(entry, "target")

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(BootstrapError):
                extract_source_archive(output.getvalue(), Path(directory) / "source")

    def test_rejects_missing_runtime_files(self):
        archive_data = make_archive({"radiostream.py": b"print('incomplete')"})

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(BootstrapError):
                extract_source_archive(archive_data, Path(directory) / "source")

    def test_install_writes_marker_and_verifiable_offline_cache(self):
        archive_data = make_archive(required_files())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = install_source_archive(archive_data, COMMIT, root)

            self.assertTrue(source_is_complete(source))
            self.assertEqual(read_source_commit(source), COMMIT)

            cached_commit, cached_archive = load_archive_cache(root / "cache")
            self.assertEqual(cached_commit, COMMIT)
            self.assertEqual(cached_archive, archive_data)


if __name__ == "__main__":
    unittest.main()
