#!/usr/bin/python
"""Load the cluster's external-source manifest as Ansible facts."""

import configparser
import platform
import re
from pathlib import Path
from urllib.parse import urlsplit

import jinja2
import yaml
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.sys_info import (
    get_distribution,
    get_distribution_version,
)
from jinja2 import meta

CACHE_PATH = Path("/config/3rdparty")
MANIFEST_PATH = Path("/config/playbooks/versions.yaml")
INVENTORY_PATH = Path("/config/playbooks/inventory")

GENERIC_ARCHITECTURE = "noarch"
SUPPORTED_ARCHITECTURES = ("x86_64", "aarch64")
OS_KEYS = ("default", "ubuntu", "ubuntu22", "ubuntu24", "oraclelinux", "oraclelinux8", "oraclelinux9")

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def maybe_amd64(architecture):
    return "amd64" if architecture == "x86_64" else architecture


def maybe_arm64(architecture):
    return "arm64" if architecture == "aarch64" else architecture


class PreserveUndefined(jinja2.Undefined):
    def __init__(self, hint=None, obj=jinja2.utils.missing, name=None, exc=jinja2.UndefinedError):
        super().__init__(hint=hint, obj=obj, name=name, exc=exc)
        self.expression = name

    def __str__(self):
        return f"{{{{ {self.expression} }}}}"

    def __getattr__(self, name):
        return type(self)(name=f"{self.expression}.{name}")

    def __getitem__(self, key):
        key = key.expression if isinstance(key, PreserveUndefined) else repr(key)
        return type(self)(name=f"{self.expression}[{key}]")


JINJA_ENVIRONMENT = jinja2.Environment(undefined=PreserveUndefined)
JINJA_ENVIRONMENT.filters.update(maybe_amd64=maybe_amd64, maybe_arm64=maybe_arm64)


def detect_architecture():
    architecture = platform.machine()
    if architecture not in SUPPORTED_ARCHITECTURES:
        raise ValueError(
            f"Unsupported architecture {architecture}; supported architectures are x86_64 and aarch64"
        )
    return architecture


def get_inventory_variable(name):
    parser = configparser.ConfigParser(
        allow_no_value=True,
        interpolation=None,
        delimiters=("=",),
    )
    try:
        with INVENTORY_PATH.open() as inventory_file:
            parser.read_file(inventory_file)
    except OSError as error:
        raise ValueError(f"Unable to read inventory {INVENTORY_PATH}: {error}")
    return parser["all:vars"][name]


def validate_manifest(value, location="versions"):
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{location} must be a non-empty mapping")

    if any(key in value for key in OS_KEYS) and any(key not in OS_KEYS for key in value):
        raise ValueError(f"{location} cannot mix OS selectors and package keys")

    for key, child in value.items():
        if not isinstance(key, str) or not KEY_PATTERN.match(key):
            raise ValueError(f"{location} has invalid key {key!r}")
        if not isinstance(child, dict):
            raise ValueError(f"{location}.{key} must be a mapping")

        has_url = "url" in child
        has_repo = "repo" in child
        if key in OS_KEYS and not (has_url or has_repo):
            raise ValueError(f"{location}.{key} must define url or repo")
        if has_url or has_repo:
            if key not in OS_KEYS:
                raise ValueError(f"{location}.{key} requires an OS selector or default")
            if "cache" in child:
                raise ValueError(f"{location}.{key}.cache is generated and cannot be set in the manifest")
            if has_url and has_repo:
                raise ValueError(f"{location}.{key} cannot contain both url and repo")
            if has_url:
                urls = child["url"]
                if not isinstance(urls, (str, list)) or (
                    isinstance(urls, list) and (not urls or not all(isinstance(url, str) for url in urls))
                ):
                    raise ValueError(f"{location}.{key}.url must be a string or non-empty list")
                if not isinstance(child.get("version"), str) or not child["version"]:
                    raise ValueError(f"{location}.{key}.url requires a version")
            elif not isinstance(child["repo"], str) or not child["repo"]:
                raise ValueError(f"{location}.{key}.repo must be a non-empty string")
            elif not isinstance(child.get("packages"), list) or not child["packages"] or not all(
                isinstance(package, str) and package for package in child["packages"]
            ):
                raise ValueError(f"{location}.{key}.repo requires a non-empty packages list")
            continue

        validate_manifest(child, f"{location}.{key}")


class Expander:
    def __init__(self):
        self.__architecture = detect_architecture()
        self.__slurm_version = get_inventory_variable("slurm_version")
        distribution = get_distribution()
        os_version = get_distribution_version()
        if not os_version:
            raise ValueError("Unable to determine OS version")
        if distribution == "Ubuntu":
            self.__os_keys = (f"ubuntu{os_version.split('.', 1)[0]}", "ubuntu", "default")
        elif distribution == "Oracle":
            self.__os_keys = (f"oraclelinux{os_version.split('.', 1)[0]}", "oraclelinux", "default")
        else:
            raise ValueError(f"Unsupported distribution {distribution} for external source cache paths")
        self.__arch_map = {
            arch: {
                "architecture": arch,
                "x86_64_or_aarch64": arch,
                "amd64_or_arm64": maybe_arm64(maybe_amd64(arch)),
                "os_version": os_version,
                "os_version_major": os_version.split(".", 1)[0],
                "slurm_version": self.__slurm_version,
            }
            for arch in SUPPORTED_ARCHITECTURES
        }
        self.__arch_keys = {
            "architecture",
            "x86_64_or_aarch64",
            "amd64_or_arm64",
        }

    def __render(self, value, **kwargs):
        return JINJA_ENVIRONMENT.from_string(value).render(**kwargs)

    def __uses_architecture(self, urls):
        if isinstance(urls, str):
            urls = [urls]
        uses_architecture = {
            bool(meta.find_undeclared_variables(JINJA_ENVIRONMENT.parse(url)) & self.__arch_keys)
            for url in urls
        }
        if len(uses_architecture) > 1:
            raise ValueError("URL fallback list cannot mix architecture-specific and generic templates")
        return uses_architecture.pop()

    def __cache_path(self, path, architecture, url) -> str:
        url_stub = Path(urlsplit(url).path).name
        if not url_stub:
            raise ValueError(f"Unable to determine cache filename from {url}")
        return str(CACHE_PATH / architecture / Path(*path) / url_stub)

    def expand(self, value, path=()):
        for key, child in list(value.items()):
            if not isinstance(child, dict):
                continue

            if any(os_key in child for os_key in OS_KEYS):
                selected_os = next((os_key for os_key in self.__os_keys if os_key in child), None)
                if selected_os is None:
                    del value[key]
                    continue
                child = value[key] = child[selected_os]

            if child.get("version") == "{{ slurm_version }}":
                child["version"] = self.__slurm_version

            if "url" in child:
                version = child["version"]
                urls = child["url"]
                if self.__uses_architecture(urls):
                    for arch, kwargs in self.__arch_map.items():
                        kwargs = {**kwargs, "version": version}
                        if isinstance(urls, list):
                            rendered_urls = [self.__render(url, **kwargs) for url in urls]
                        else:
                            rendered_urls = self.__render(urls, **kwargs)
                        child[arch] = {"url": rendered_urls}
                        primary_url = rendered_urls[0] if isinstance(rendered_urls, list) else rendered_urls
                        child[arch]["cache"] = self.__cache_path(path + (key,), arch, primary_url)
                    child["url"] = child[self.__architecture]["url"]
                    child["cache"] = child[self.__architecture]["cache"]
                else:
                    kwargs = {**self.__arch_map[self.__architecture], "version": version}
                    if isinstance(urls, list):
                        child["url"] = [self.__render(url, **kwargs) for url in urls]
                    else:
                        child["url"] = self.__render(urls, **kwargs)
                    primary_url = child["url"][0] if isinstance(child["url"], list) else child["url"]
                    child["cache"] = self.__cache_path(
                        path + (key,), GENERIC_ARCHITECTURE, primary_url
                    )

            if "repo" in child:
                kwargs = self.__arch_map[self.__architecture].copy()
                if "version" in child:
                    kwargs["version"] = child["version"]
                child["repo"] = self.__render(child["repo"], **kwargs)

            if "url" not in child and "repo" not in child:
                self.expand(child, path + (key,))
                if not child:
                    del value[key]


def main():
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    if not MANIFEST_PATH.is_file():
        module.fail_json(msg=f"External source manifest not found: {MANIFEST_PATH}")

    try:
        with MANIFEST_PATH.open() as manifest_file:
            manifest = yaml.safe_load(manifest_file)
        validate_manifest(manifest)
        Expander().expand(manifest)
    except (OSError, ValueError, yaml.YAMLError) as error:
        module.fail_json(msg=f"Invalid external source manifest: {error}")

    module.exit_json(changed=False, ansible_facts={"oci_versions": manifest})


if __name__ == "__main__":
    main()
