# Ansible Linting

https://ansible.readthedocs.io/projects/lint/

Install with `pip3 install ansible-lint`

Run with `ansible-lint ../playbooks/`

Autofix with `ansible-lint --fix ../playbooks/`

We are currently using the [`production` profile](https://ansible.readthedocs.io/projects/lint/profiles/#production) which ensures that content meets requirements for inclusion in [Ansible Automation Platform (AAP)](https://www.redhat.com/en/technologies/management/ansible) as validated or certified content.