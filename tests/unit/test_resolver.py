import re
from pathlib import Path
from typing import Callable
from unittest import mock

import pytest

from cachi2.core import resolver
from cachi2.core.errors import UnsupportedFeature
from cachi2.core.models.input import Request
from cachi2.core.models.output import BuildConfig, EnvironmentVariable, ProjectFile, RequestOutput
from cachi2.core.models.sbom import Component

GOMOD_OUTPUT = RequestOutput.from_obj_list(
    components=[
        Component(
            type="library",
            name="github.com/foo/bar",
            version="v1.0.0",
            purl="pkg:golang/github.com/foo/bar@v1.0.0",
        )
    ],
    environment_variables=[
        EnvironmentVariable(name="GOMODCACHE", value="deps/gomod/pkg/mod", kind="path"),
    ],
    project_files=[
        ProjectFile(abspath="/your/project/go.mod", template="Hello gomod my old friend.")
    ],
)

PIP_OUTPUT = RequestOutput.from_obj_list(
    components=[
        Component(type="library", name="spam", version="1.0.0", purl="pkg:pypi/spam@1.0.0")
    ],
    environment_variables=[
        EnvironmentVariable(name="PIP_INDEX_URL", value="file:///some/path", kind="literal"),
    ],
    project_files=[
        ProjectFile(
            abspath="/your/project/requirements.txt", template="I've come to talk with you again."
        ),
    ],
)

NPM_OUTPUT = RequestOutput.from_obj_list(
    components=[Component(type="library", name="eggs", version="1.0.0", purl="pkg:npm/eggs@1.0.0")],
    environment_variables=[
        EnvironmentVariable(name="CHROMEDRIVER_SKIP_DOWNLOAD", value="true", kind="literal"),
    ],
    project_files=[
        ProjectFile(
            abspath="/your/project/package-lock.json", template="Because a vision softly creeping."
        )
    ],
)

COMBINED_OUTPUT = RequestOutput.from_obj_list(
    components=GOMOD_OUTPUT.components + NPM_OUTPUT.components + PIP_OUTPUT.components,
    environment_variables=(
        GOMOD_OUTPUT.build_config.environment_variables
        + PIP_OUTPUT.build_config.environment_variables
        + NPM_OUTPUT.build_config.environment_variables
    ),
    project_files=(
        GOMOD_OUTPUT.build_config.project_files
        + PIP_OUTPUT.build_config.project_files
        + NPM_OUTPUT.build_config.project_files
    ),
)


def test_resolve_packages(tmp_path: Path) -> None:
    request = Request(
        source_dir=tmp_path,
        output_dir=tmp_path,
        packages=[{"type": "pip"}, {"type": "npm"}, {"type": "gomod"}],
    )

    calls_by_pkgtype = []

    def mock_fetch(pkgtype: str, output: RequestOutput) -> Callable[[Request], RequestOutput]:
        def fetch(req: Request) -> RequestOutput:
            assert req == request
            calls_by_pkgtype.append(pkgtype)
            return output

        return fetch

    with mock.patch.dict(
        resolver._package_managers,
        {
            "gomod": mock_fetch("gomod", GOMOD_OUTPUT),
            "npm": mock_fetch("npm", NPM_OUTPUT),
            "pip": mock_fetch("pip", PIP_OUTPUT),
        },
    ):
        assert resolver.resolve_packages(request) == COMBINED_OUTPUT

    assert calls_by_pkgtype == ["gomod", "npm", "pip"]


@pytest.mark.parametrize(
    "flags",
    [
        pytest.param(["dev-package-managers"], id="dev-package-managers-true"),
        pytest.param([], id="dev-package-managers-false"),
    ],
)
def test_dev_mode(flags: list[str]) -> None:
    mock_resolver = mock.Mock()
    mock_resolver.return_value = RequestOutput.empty()
    with (
        mock.patch.dict(
            resolver._package_managers,
            values={"gomod": mock_resolver},
            clear=True,
        ),
        mock.patch.dict(
            resolver._dev_package_managers,
            values={"shrubbery": mock_resolver},
            clear=True,
        ),
    ):
        dev_package_input = mock.Mock()
        dev_package_input.type = "shrubbery"

        request = mock.Mock()
        request.flags = flags
        request.packages = [dev_package_input]

        if flags:
            assert resolver.resolve_packages(request) == RequestOutput(
                components=[], build_config=BuildConfig(environment_variables=[], project_files=[])
            )
        else:
            expected_error = re.escape("Package manager(s) not yet supported: shrubbery")
            with pytest.raises(UnsupportedFeature, match=expected_error):
                resolver.resolve_packages(request)


def test_resolve_with_released_and_dev_package_managers() -> None:
    mock_resolve_gomod = mock.Mock(return_value=RequestOutput.empty())
    mock_resolve_pip = mock.Mock(return_value=RequestOutput.empty())

    with (
        mock.patch.dict(
            resolver._package_managers,
            values={"gomod": mock_resolve_gomod},
            clear=True,
        ),
        mock.patch.dict(
            resolver._dev_package_managers,
            values={"pip": mock_resolve_pip},
            clear=True,
        ),
    ):
        dev_package_input = mock.Mock()
        dev_package_input.type = "pip"

        released_package_input = mock.Mock()
        released_package_input.type = "gomod"

        request = mock.Mock()
        request.flags = ["dev-package-managers"]
        request.packages = [released_package_input, dev_package_input]

        resolver.resolve_packages(request)

        mock_resolve_gomod.assert_has_calls([mock.call(request)])
        mock_resolve_pip.assert_has_calls([mock.call(request)])
