import pytest
import sys
from pathlib import Path

import importlib.util

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FACTS_PATH = REPOSITORY_ROOT / "playbooks" / "library" / "oci_hpc_facts.py"


def load_facts_module():
    spec = importlib.util.spec_from_file_location("oci_hpc_facts", FACTS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {FACTS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


facts = load_facts_module()


@pytest.fixture
def expander(monkeypatch, tmp_path):
    monkeypatch.setattr(facts, "CACHE_PATH", tmp_path)
    monkeypatch.setattr(facts, "detect_architecture", lambda: "x86_64")
    monkeypatch.setattr(facts, "get_inventory_variable", lambda _: "24.11.0")
    monkeypatch.setattr(facts, "get_distribution", lambda: "Ubuntu")
    monkeypatch.setattr(facts, "get_distribution_version", lambda: "22.04")
    return facts.Expander()


@pytest.mark.parametrize(
    ("architecture", "amd64", "arm64"),
    [("x86_64", "amd64", "x86_64"), ("aarch64", "aarch64", "arm64")],
)
def test_architecture_filters(architecture, amd64, arm64):
    assert facts.maybe_amd64(architecture) == amd64
    assert facts.maybe_arm64(architecture) == arm64


def test_detect_architecture(monkeypatch):
    monkeypatch.setattr(facts.platform, "machine", lambda: "aarch64")

    assert facts.detect_architecture() == "aarch64"


def test_detect_architecture_rejects_unsupported_value(monkeypatch):
    monkeypatch.setattr(facts.platform, "machine", lambda: "ppc64le")

    with pytest.raises(ValueError, match="Unsupported architecture ppc64le"):
        facts.detect_architecture()


def test_get_inventory_variable(monkeypatch, tmp_path):
    inventory = tmp_path / "inventory"
    inventory.write_text("[all:vars]\nslurm_version=23.11.0\n", encoding="utf-8")
    monkeypatch.setattr(facts, "INVENTORY_PATH", inventory)

    assert facts.get_inventory_variable("slurm_version") == "23.11.0"
    with pytest.raises(KeyError, match="cluster_name"):
        facts.get_inventory_variable("cluster_name")


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"invalid-key": {}},
        {"artifact": {"default": {"url": "https://example.test/artifact.tar.gz"}}},
        {
            "artifact": {
                "default": {
                    "version": "1.0",
                    "url": "https://example.test/artifact.tar.gz",
                    "repo": "https://example.test/repo",
                }
            }
        },
        {"repo": {"default": {"repo": "https://example.test/repo", "packages": []}}},
    ],
)
def test_validate_manifest_rejects_invalid_entries(manifest):
    with pytest.raises(ValueError):
        facts.validate_manifest(manifest)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {"version": "1.0", "url": "https://example.test/artifact-{{ version }}.tar.gz"},
            "requires an OS selector or default",
        ),
        (
            {"repo": "https://example.test/repo", "packages": ["package"]},
            "requires an OS selector or default",
        ),
        (
            {
                "default": {"repo": "https://example.test/repo", "packages": ["package"]},
                "nested": {"default": {"repo": "https://example.test/repo", "packages": ["package"]}},
            },
            "cannot mix OS selectors and package keys",
        ),
        ({"default": {"nested": {}}}, "must define url or repo"),
        (
            {"oraclelinux10": {"repo": "https://example.test/repo", "packages": ["package"]}},
            "requires an OS selector or default",
        ),
    ],
)
def test_validate_manifest_rejects_invalid_selectors(entry, message):
    with pytest.raises(ValueError, match=message):
        facts.validate_manifest({"artifact": entry})


def test_validate_manifest_accepts_direct_download_and_repository():
    facts.validate_manifest(
        {
            "artifact": {
                "default": {
                    "version": "1.0",
                    "url": "https://example.test/artifact-{{ version }}.tar.gz",
                }
            },
            "repository": {
                "default": {
                    "repo": "https://example.test/repo",
                    "packages": ["package"],
                }
            },
        }
    )


def test_expander_renders_generic_url_once_into_noarch_cache(expander, tmp_path):
    value = {
        "artifact": {
            "default": {
                "version": "1.0",
                "url": "https://example.test/artifact-{{ version }}.tar.gz",
            }
        }
    }

    expander.expand(value)

    artifact = value["artifact"]
    assert artifact["url"] == "https://example.test/artifact-1.0.tar.gz"
    assert artifact["cache"] == str(tmp_path / "noarch" / "artifact" / "artifact-1.0.tar.gz")
    assert not any(architecture in artifact for architecture in facts.SUPPORTED_ARCHITECTURES)


@pytest.mark.parametrize(
    ("template", "x86_64_component", "aarch64_component"),
    [
        ("https://example.test/artifact-{{ architecture }}.tar.gz", "x86_64", "aarch64"),
        ("https://example.test/artifact-{{ x86_64_or_aarch64 }}.tar.gz", "x86_64", "aarch64"),
        ("https://example.test/artifact-{{ amd64_or_arm64 }}.tar.gz", "amd64", "arm64"),
        (
            "https://example.test/artifact-{{ architecture | maybe_amd64 | maybe_arm64 }}.tar.gz",
            "amd64",
            "arm64",
        ),
    ],
)
def test_expander_renders_architecture_specific_urls(
    expander, tmp_path, template, x86_64_component, aarch64_component
):
    value = {"artifact": {"default": {"version": "1.0", "url": template}}}

    expander.expand(value)

    artifact = value["artifact"]
    assert set(facts.SUPPORTED_ARCHITECTURES) <= artifact.keys()
    assert artifact["url"] == artifact["x86_64"]["url"]
    assert artifact["x86_64"]["url"] == f"https://example.test/artifact-{x86_64_component}.tar.gz"
    assert artifact["aarch64"]["url"] == f"https://example.test/artifact-{aarch64_component}.tar.gz"
    assert Path(artifact["x86_64"]["cache"]).parent == tmp_path / "x86_64" / "artifact"
    assert Path(artifact["aarch64"]["cache"]).parent == tmp_path / "aarch64" / "artifact"


def test_expander_renders_generic_fallbacks_once(expander, tmp_path):
    value = {
        "artifact": {
            "default": {
                "version": "1.0",
                "url": [
                    "https://primary.example.test/artifact-{{ version }}.tar.gz",
                    "https://backup.example.test/artifact-{{ version }}.tar.gz",
                ],
            }
        }
    }

    expander.expand(value)

    artifact = value["artifact"]
    assert artifact["url"] == [
        "https://primary.example.test/artifact-1.0.tar.gz",
        "https://backup.example.test/artifact-1.0.tar.gz",
    ]
    assert artifact["cache"] == str(tmp_path / "noarch" / "artifact" / "artifact-1.0.tar.gz")


def test_expander_rejects_mixed_architecture_fallbacks(expander):
    value = {
        "artifact": {
            "default": {
                "version": "1.0",
                "url": [
                    "https://primary.example.test/artifact-{{ architecture }}.tar.gz",
                    "https://backup.example.test/artifact-{{ version }}.tar.gz",
                ],
            }
        }
    }

    with pytest.raises(ValueError, match="cannot mix architecture-specific and generic"):
        expander.expand(value)


def test_expander_renders_repository_and_slurm_cache(expander, tmp_path):
    value = {
        "repository": {
            "default": {
                "version": "1.0",
                "repo": "https://example.test/{{ os_version_major }}/{{ version }}",
                "packages": ["package"],
            }
        },
        "slurm": {
            "artifact": {
                "default": {
                    "version": "1.0",
                    "url": "https://example.test/artifact-{{ version }}.tar.gz",
                }
            }
        },
    }

    expander.expand(value)

    assert value["repository"]["repo"] == "https://example.test/22/1.0"
    assert value["slurm"]["artifact"]["url"] == "https://example.test/artifact-1.0.tar.gz"
    assert value["slurm"]["artifact"]["cache"] == str(
        tmp_path / "noarch" / "slurm" / "artifact" / "artifact-1.0.tar.gz"
    )


@pytest.mark.parametrize("architecture", facts.SUPPORTED_ARCHITECTURES)
@pytest.mark.parametrize(
    ("distribution", "os_version", "os_key"),
    [
        ("Ubuntu", "22.04", "ubuntu"),
        ("Ubuntu", "24.04", "ubuntu"),
        ("Oracle", "8.10", "oraclelinux"),
        ("Oracle", "9.6", "oraclelinux"),
    ],
)
def test_slurm_manifest_urls_and_caches(monkeypatch, tmp_path, architecture, distribution, os_version, os_key):
    slurm_version = "26.05.0-1.oci"
    monkeypatch.setattr(facts, "CACHE_PATH", tmp_path)
    monkeypatch.setattr(facts, "detect_architecture", lambda: architecture)
    monkeypatch.setattr(facts, "get_inventory_variable", lambda _: slurm_version)
    monkeypatch.setattr(facts, "get_distribution", lambda: distribution)
    monkeypatch.setattr(facts, "get_distribution_version", lambda: os_version)
    with FACTS_PATH.parent.parent.joinpath("versions.yaml").open(encoding="utf-8") as manifest_file:
        manifest = facts.yaml.safe_load(manifest_file)
    facts.validate_manifest(manifest)
    facts.Expander().expand(manifest)

    packages = ["slurm"]
    if os_key == "oraclelinux":
        packages += [
            "slurm-devel", "slurm-contribs", "slurm-perlapi", "slurm-torque", "slurm-openlava",
            "slurm-slurmctld", "slurm-slurmdbd", "slurm-slurmrestd", "slurm-pam_slurm",
            "slurm-libpmi", "slurm-slurmd", "slurm-sackd", "pmix", "pmix-devel",
        ]

    caches = set()
    for package in packages:
        key = package.replace("-", "_")
        artifact = manifest["slurm"][key]
        version = "5.0.9-1" if package.startswith("pmix") else slurm_version
        assert artifact["version"] == version
        assert artifact["url"] == artifact[architecture]["url"]
        assert artifact["cache"] == artifact[architecture]["cache"]
        for target_architecture in facts.SUPPORTED_ARCHITECTURES:
            if os_key == "ubuntu":
                deb_arch = {"x86_64": "amd64", "aarch64": "arm64"}[target_architecture]
                filename = f"slurm-{version}_{os_version}_{deb_arch}.deb"
            else:
                filename = f"{package}-{version}.el{os_version.split('.')[0]}.{target_architecture}.rpm"
            target = artifact[target_architecture]
            assert len(target["url"]) == 2
            assert "/n/hpctraininglab/" in target["url"][0]
            assert "/n/idxzjcdglx2s/" in target["url"][1]
            directory = "pmix" if package.startswith("pmix") else "slurm"
            assert all(url.endswith(f"/{directory}/{filename}") for url in target["url"])
            assert target["cache"] == str(tmp_path / target_architecture / "slurm" / key / filename)
            assert target["cache"] not in caches
            caches.add(target["cache"])

    assert set(manifest["slurm"]) == {package.replace("-", "_") for package in packages}
    assert ("openldap" in manifest) == (distribution == "Oracle" and os_version.startswith("8."))
    assert ("amd_container" in manifest) == (distribution == "Ubuntu")
    pending = [manifest]
    while pending:
        node = pending.pop()
        assert not set(facts.OS_KEYS).intersection(node)
        pending.extend(child for child in node.values() if isinstance(child, dict))


@pytest.mark.parametrize(
    ("distribution", "os_version", "selectors", "expected"),
    [
        ("Ubuntu", "22.04", ("default", "oraclelinux", "ubuntu"), "ubuntu"),
        ("Ubuntu", "22.04", ("default", "ubuntu", "ubuntu24", "ubuntu22"), "ubuntu22"),
        ("Ubuntu", "24.04", ("default", "ubuntu", "ubuntu22", "ubuntu24"), "ubuntu24"),
        ("Ubuntu", "22.04", ("default", "ubuntu24", "ubuntu"), "ubuntu"),
        ("Ubuntu", "24.04", ("default", "ubuntu22", "ubuntu"), "ubuntu"),
        ("Ubuntu", "22.04", ("default", "ubuntu24"), "default"),
        ("Ubuntu", "24.04", ("default", "ubuntu22"), "default"),
        ("Ubuntu", "22.04", ("ubuntu22",), "ubuntu22"),
        ("Ubuntu", "24.04", ("ubuntu24",), "ubuntu24"),
        ("Oracle", "8.10", ("default", "oraclelinux", "oraclelinux8"), "oraclelinux8"),
        ("Oracle", "9.6", ("default", "oraclelinux", "oraclelinux9"), "oraclelinux9"),
        ("Oracle", "8.10", ("default", "oraclelinux9", "oraclelinux"), "oraclelinux"),
        ("Oracle", "9.6", ("default", "oraclelinux8", "oraclelinux"), "oraclelinux"),
        ("Ubuntu", "24.04", ("default", "oraclelinux"), "default"),
        ("Oracle", "8.10", ("default", "oraclelinux9"), "default"),
        ("Oracle", "9.6", ("default", "oraclelinux8"), "default"),
        ("Oracle", "9.6", ("oraclelinux9",), "oraclelinux9"),
    ],
)
def test_expander_selects_os_repository(expander, monkeypatch, distribution, os_version, selectors, expected):
    monkeypatch.setattr(facts, "get_distribution", lambda: distribution)
    monkeypatch.setattr(facts, "get_distribution_version", lambda: os_version)
    value = {
        "repository": {
            os_key: {
                "version": "1.0",
                "repo": f"https://example.test/{os_key}/" + "{{ os_version_major }}/{{ version }}",
                "packages": [os_key],
            }
            for os_key in selectors
        }
    }
    if "default" in selectors:
        value["repository"]["default"]["key_url"] = "https://example.test/default/key"

    facts.validate_manifest(value)
    facts.Expander().expand(value)

    assert value["repository"] == {
        "version": "1.0",
        "repo": f"https://example.test/{expected}/{os_version.split('.')[0]}/1.0",
        "packages": [expected],
        **({"key_url": "https://example.test/default/key"} if expected == "default" else {}),
    }


@pytest.mark.parametrize("unmatched_selector", ["oraclelinux", "ubuntu24"])
def test_expander_prunes_unmatched_os_and_preserves_generic_siblings(expander, tmp_path, unmatched_selector):
    generic = {"version": "1.0", "url": "https://example.test/shared-{{ version }}.tar.gz"}
    # An invalid template in an unselected branch must never be rendered.
    unmatched = {unmatched_selector: {"version": "1.0", "url": "{{ architecture +"}}
    value = {
        "mixed": {"shared": {"default": generic.copy()}, "unavailable": unmatched.copy()},
        "unavailable_role": {"nested": {"artifact": unmatched.copy()}},
        "selected": {"ubuntu": generic.copy(), **unmatched},
    }
    facts.validate_manifest(value)

    expander.expand(value)

    assert set(value) == {"mixed", "selected"}
    assert set(value["mixed"]) == {"shared"}
    assert value["selected"]["url"] == "https://example.test/shared-1.0.tar.gz"
    assert value["selected"]["cache"] == str(tmp_path / "noarch" / "selected" / "shared-1.0.tar.gz")
    assert value["mixed"]["shared"]["cache"] == str(
        tmp_path / "noarch" / "mixed" / "shared" / "shared-1.0.tar.gz"
    )
