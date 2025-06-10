# Ansible Linting

https://ansible.readthedocs.io/projects/lint/

Install with `pip3 install ansible-lint`

Run with `ansible-lint ../playbooks/`

Autofix with `ansible-lint --fix ../playbooks/`

We are currently using the [`min` profile](https://ansible.readthedocs.io/projects/lint/profiles/#min) which profile ensures that Ansible can load content.