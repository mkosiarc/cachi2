import logging

from cachi2.core.errors import PackageRejected
from cachi2.core.models.input import Request
from cachi2.core.models.output import Component, EnvironmentVariable, RequestOutput
from cachi2.core.package_managers.yarn.project import (
    Project,
    get_semver_from_package_manager,
    get_semver_from_yarn_path,
)
from cachi2.core.package_managers.yarn.resolver import create_components, resolve_packages
from cachi2.core.package_managers.yarn.utils import run_yarn_cmd
from cachi2.core.rooted_path import RootedPath

log = logging.getLogger(__name__)


def fetch_yarn_source(request: Request) -> RequestOutput:
    """Process all the yarn source directories in a request."""
    components = []

    for package in request.yarn_packages:
        path = request.source_dir.join_within_root(package.path)
        project = Project.from_source_dir(path)
        components.extend(_resolve_yarn_project(project, request.output_dir))

    return RequestOutput.from_obj_list(
        components, _generate_environment_variables(), project_files=[]
    )


def _resolve_yarn_project(project: Project, output_dir: RootedPath) -> list[Component]:
    """Process a request for a single yarn source directory.

    :param project: the directory to be processed.
    :param output_dir: the directory where the prefetched dependencies will be placed.
    """
    log.info(f"Fetching the yarn dependencies at the subpath {output_dir.subpath_from_root}")

    _configure_yarn_version(project)

    try:
        _set_yarnrc_configuration(project, output_dir)
        packages = resolve_packages(project.source_dir)

        if project.is_zero_installs:
            _check_yarn_cache(project.source_dir)
        else:
            _fetch_dependencies(project.source_dir, output_dir)
    finally:
        _undo_changes(project)

    return create_components(packages, project, output_dir)


def _configure_yarn_version(project: Project) -> None:
    """Resolve the yarn version and set it in the package.json file if needed.

    :raises PackageRejected:
        if the yarn version can't be determined from either yarnPath or packageManager
        if there is a mismatch between the yarn version specified by yarnPath and PackageManager
    """
    if project.yarn_rc:
        yarn_path_version = get_semver_from_yarn_path(project.yarn_rc.yarn_path)
    else:
        yarn_path_version = None

    package_manager_version = get_semver_from_package_manager(project.package_json.package_manager)

    if not yarn_path_version and not package_manager_version:
        raise PackageRejected(
            "Unable to determine the yarn version to use to process the request",
            solution=(
                "Ensure that either yarnPath is defined in .yarnrc.yml or that packageManager "
                "is defined in package.json"
            ),
        )

    if (
        yarn_path_version
        and package_manager_version
        and yarn_path_version != package_manager_version
    ):
        raise PackageRejected(
            (
                f"Mismatch between the yarn versions specified by yarnPath (yarn@{yarn_path_version}) "
                f"and packageManager (yarn@{package_manager_version})"
            ),
            solution=(
                "Ensure that the versions of yarn specified by yarnPath in .yarnrc.yml and "
                "packageManager in package.json agree"
            ),
        )

    if not package_manager_version:
        project.package_json.package_manager = f"yarn@{yarn_path_version}"
        project.package_json.write_to_file()


def _set_yarnrc_configuration(project: Project, output_dir: RootedPath) -> None:
    """Set all the necessary configuration in yarnrc for the project processing.

    :param project: the configuration changes dependending on if the project uses the zero-installs
        or the regular workflow.
    :param output_dir: in case the dependencies need to be fetched, this is where they will be
        downloaded to.
    """
    # the plugins should be disabled here regardless of the project workflow.
    pass


def _check_yarn_cache(source_dir: RootedPath) -> None:
    """Check the contents of the yarn cache using 'yarn install'.

    :param source_dir: the directory in which the yarn command will be called.
    :raises YarnCommandError: if the 'yarn install' command fails.
    """
    # the yarn commands can be called by using the core.utils.run_cmd function
    pass


def _fetch_dependencies(source_dir: RootedPath, output_dir: RootedPath) -> None:
    """Fetch dependencies using 'yarn install'.

    :param source_dir: the directory in which the yarn command will be called.
    :param output_dir: the directory where the yarn dependencies will be downloaded to.
    :raises YarnCommandError: if the 'yarn install' command fails.
    """
    cachi2_output = output_dir.join_within_root("deps", "yarn")

    args = ["install", "--mode", "skip-build"]
    run_yarn_cmd(args, source_dir, {"YARN_GLOBAL_FOLDER": str(cachi2_output)})


def _undo_changes(project: Project) -> None:
    """Undo any changes that were made to the files during the request's processing."""
    # restore the disabled plugins here, as well as undo any additional changes
    pass


def _generate_environment_variables() -> list[EnvironmentVariable]:
    """Generate environment variables that will be used for building the project."""
    return []