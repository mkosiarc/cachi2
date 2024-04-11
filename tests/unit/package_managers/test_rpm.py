from pathlib import Path
from unittest import mock

import pytest
import yaml

from cachi2.core.errors import PackageManagerError, PackageRejected
from cachi2.core.package_managers.rpm import fetch_rpm_source
from cachi2.core.package_managers.rpm.main import (
    DEFAULT_LOCKFILE_NAME,
    _download,
    _resolve_rpm_project,
    _verify_downloaded,
)
from cachi2.core.package_managers.rpm.redhat import RedhatRpmsLock
from cachi2.core.rooted_path import RootedPath

RPM_LOCK_FILE_DATA = """
lockfileVersion: 1
lockfileVendor: redhat
arches:
  - arch: x86_64
    packages:
      - url: https://example.com/x86_64/Packages/v/vim-enhanced-9.1.158-1.fc38.x86_64.rpm
        checksum: sha256:21bb2a09852e75a693d277435c162e1a910835c53c3cee7636dd552d450ed0f1
        size: 1976132
        repoid: updates
    source:
      - url: https://example.com/source/tree/Packages/v/vim-9.1.158-1.fc38.src.rpm
        checksum: sha256:94803b5e1ff601bf4009f223cb53037cdfa2fe559d90251bbe85a3a5bc6d2aab
        size: 14735448
        repoid: updates-source
"""


@mock.patch("cachi2.core.package_managers.rpm.main.RequestOutput.from_obj_list")
@mock.patch("cachi2.core.package_managers.rpm.main._resolve_rpm_project")
def test_fetch_rpm_source(
    mock_resolve_rpm_project: mock.Mock,
    mock_from_obj_list: mock.Mock,
) -> None:
    mock_component = mock.Mock()
    mock_resolve_rpm_project.return_value = [mock_component]
    mock_request = mock.Mock()
    mock_request.rpm_packages = [mock.Mock()]
    fetch_rpm_source(mock_request)
    mock_resolve_rpm_project.assert_called_once()
    mock_from_obj_list.assert_called_once_with(
        components=[mock_component], environment_variables=[], project_files=[]
    )


def test_resolve_rpm_project_no_lockfile(rooted_tmp_path: RootedPath) -> None:
    with pytest.raises(PackageRejected) as exc_info:
        mock_source_dir = mock.Mock()
        mock_source_dir.join_within_root.return_value.path.exists.return_value = False
        _resolve_rpm_project(mock_source_dir, mock.Mock())
    assert f"RPM lockfile '{DEFAULT_LOCKFILE_NAME}' missing, refusing to continue" in str(
        exc_info.value
    )


def test_resolve_rpm_project_invalid_yaml_format(rooted_tmp_path: RootedPath) -> None:
    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        # colon is missing at the end
        f.write("lockfileVendor: redhat\nlockfileVersion: 1\narches\n")
    with pytest.raises(PackageRejected) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)

    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        # end of line is missing between items
        f.write("lockfileVendor: redhat lockfileVersion: 1\narches:\n")
    with pytest.raises(PackageRejected) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)
    assert f"RPM lockfile '{DEFAULT_LOCKFILE_NAME}' yaml format is not correct" in str(
        exc_info.value
    )


def test_resolve_rpm_project_invalid_lockfile_format(rooted_tmp_path: RootedPath) -> None:
    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "lockfileVendor": "unknown",
                "lockfileVersion": 1,
                "arches": [],
            },
            f,
        )
    with pytest.raises(PackageManagerError) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)

    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "lockfileVendor": "redhat",
                "lockfileVersion": 2,
                "arches": [],
            },
            f,
        )
    with pytest.raises(PackageManagerError) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)

    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "lockfileVendor": "redhat",
                "lockfileVersion": "zz",
                "arches": [],
            },
            f,
        )
    with pytest.raises(PackageManagerError) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)

    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "vendor": "redhat",
                "lockfileVersion": 1,
                "arches": [],
            },
            f,
        )
    with pytest.raises(PackageManagerError) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)

    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "lockfileVendor": "redhat",
                "lockfileVersion": 1,
                "arches": "everything",
            },
            f,
        )
    with pytest.raises(PackageManagerError) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)

    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "lockfileVendor": "redhat",
                "lockfileVersion": "zz",
                "arches": [
                    {
                        "arch": "x86_64",
                        "packages": [
                            {
                                "address": "SOME_ADDRESS",
                                "size": 1111,
                            },
                        ],
                    },
                ],
            },
            f,
        )
    with pytest.raises(PackageManagerError) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)
    assert f"RPM lockfile '{DEFAULT_LOCKFILE_NAME}' format is not valid" in str(exc_info.value)


def test_resolve_rpm_project_arch_empty(rooted_tmp_path: RootedPath) -> None:
    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "lockfileVendor": "redhat",
                "lockfileVersion": 1,
                "arches": [
                    {
                        "arch": "x86_64",
                    },
                ],
            },
            f,
        )
    with pytest.raises(PackageManagerError) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)

    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "lockfileVendor": "redhat",
                "lockfileVersion": 1,
                "arches": [
                    {
                        "arch": "aarch64",
                        "packages": [],
                    },
                ],
            },
            f,
        )
    with pytest.raises(PackageManagerError) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)

    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "lockfileVendor": "redhat",
                "lockfileVersion": 1,
                "arches": [
                    {
                        "arch": "i686",
                        "packages": [],
                        "source": [],
                    },
                    {
                        "arch": "x86_64",
                        "packages": [
                            {
                                "url": "SOME_URL",
                            },
                        ],
                    },
                ],
            },
            f,
        )
    with pytest.raises(PackageManagerError) as exc_info:
        _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)
    assert "At least one field ('packages', 'source') must be set in every arch." in str(
        exc_info.value
    )


@mock.patch("cachi2.core.package_managers.rpm.main._download")
def test_resolve_rpm_project_correct_format(
    mock_download: mock.Mock, rooted_tmp_path: RootedPath
) -> None:
    with open(rooted_tmp_path.join_within_root("rpms.lock.yaml"), "w") as f:
        yaml.safe_dump(
            {
                "lockfileVendor": "redhat",
                "lockfileVersion": 1,
                "arches": [
                    {
                        "arch": "x86_64",
                        "packages": [
                            {
                                "url": "SOME_URL",
                            },
                        ],
                        "source": [
                            {
                                "url": "SOME_URL",
                            },
                        ],
                    },
                ],
            },
            f,
        )
    _resolve_rpm_project(rooted_tmp_path, rooted_tmp_path)


@mock.patch(
    "cachi2.core.package_managers.rpm.main.open",
    new_callable=mock.mock_open,
)
@mock.patch("cachi2.core.package_managers.rpm.main._download")
@mock.patch("cachi2.core.package_managers.rpm.main._verify_downloaded")
@mock.patch("cachi2.core.package_managers.rpm.main.RedhatRpmsLock.model_validate")
def test_resolve_rpm_project(
    mock_model_validate: mock.Mock,
    mock_verify_downloaded: mock.Mock,
    mock_download: mock.Mock,
    mock_open: mock.Mock,
) -> None:
    output_dir = mock.Mock()
    mock_package_dir_path = mock.Mock()
    output_dir.join_within_root.return_value.path = mock_package_dir_path
    mock_download.return_value = {}

    _resolve_rpm_project(mock.Mock(), output_dir)
    mock_download.assert_called_once_with(mock_model_validate.return_value, mock_package_dir_path)
    mock_verify_downloaded.assert_called_once_with({})


@mock.patch("cachi2.core.package_managers.rpm.main.asyncio.run")
@mock.patch("cachi2.core.package_managers.rpm.main.async_download_files")
def test_download(
    mock_async_download_files: mock.Mock, mock_asyncio: mock.Mock, rooted_tmp_path: RootedPath
) -> None:
    lock = RedhatRpmsLock.model_validate(yaml.safe_load(RPM_LOCK_FILE_DATA))
    _download(lock, rooted_tmp_path.path)
    mock_async_download_files.assert_called_once_with(
        {
            "https://example.com/x86_64/Packages/v/vim-enhanced-9.1.158-1.fc38.x86_64.rpm": str(
                rooted_tmp_path.path.joinpath(
                    "x86_64/updates/vim-enhanced-9.1.158-1.fc38.x86_64.rpm"
                )
            ),
            "https://example.com/source/tree/Packages/v/vim-9.1.158-1.fc38.src.rpm": str(
                rooted_tmp_path.path.joinpath("x86_64/updates-source/vim-9.1.158-1.fc38.src.rpm")
            ),
        },
        5,
    )
    mock_asyncio.assert_called_once()


@mock.patch("pathlib.Path.stat")
def test_verify_downloaded_unexpected_size(stat_mock: mock.Mock) -> None:
    stat_mock.return_value = mock.Mock()
    stat_mock.st_size = 0
    metadata = {Path("foo"): {"size": 12345}}

    with pytest.raises(PackageRejected) as exc_info:
        _verify_downloaded(metadata)
    assert "Unexpected file size of" in str(exc_info.value)


def test_verify_downloaded_unsupported_hash_alg() -> None:
    metadata = {Path("foo"): {"checksum": "noalg:unmatchedchecksum", "size": None}}
    with pytest.raises(PackageRejected) as exc_info:
        _verify_downloaded(metadata)
    assert "Unsupported hashing algorithm" in str(exc_info.value)


@mock.patch(
    "cachi2.core.package_managers.rpm.main.open",
    new_callable=mock.mock_open,
    read_data=b"test",
)
def test_verify_downloaded_unmatched_checksum(mock_open: mock.Mock) -> None:
    metadata = {Path("foo"): {"checksum": "sha256:unmatchedchecksum", "size": None}}
    with pytest.raises(PackageRejected) as exc_info:
        _verify_downloaded(metadata)
    assert "Unmatched checksum of" in str(exc_info.value)


class TestRedhatRpmsLock:
    @pytest.fixture
    def raw_content(self) -> dict:
        return {"lockfileVendor": "redhat", "lockfileVersion": 1, "arches": []}

    @mock.patch("cachi2.core.package_managers.rpm.redhat.uuid")
    def test_internal_repoid(self, mock_uuid: mock.Mock, raw_content: dict) -> None:
        mock_uuid.uuid4.return_value.hex = "abcdefghijklmn"
        lock = RedhatRpmsLock.model_validate(raw_content)
        assert lock._uuid == "abcdef"
        assert lock.internal_repoid == "cachi2-abcdef"

    @mock.patch("cachi2.core.package_managers.rpm.redhat.uuid")
    def test_internal_source_repoid(self, mock_uuid: mock.Mock, raw_content: dict) -> None:
        mock_uuid.uuid4.return_value.hex = "abcdefghijklmn"
        lock = RedhatRpmsLock.model_validate(raw_content)
        assert lock._uuid == "abcdef"
        assert lock.internal_source_repoid == "cachi2-abcdef-source"

    def test_uuid(self, raw_content: dict) -> None:
        lock = RedhatRpmsLock.model_validate(raw_content)
        uuid = lock._uuid
        assert len(uuid) == 6