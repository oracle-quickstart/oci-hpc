# Ansible Linting

https://ansible.readthedocs.io/projects/lint/

Install with `pip3 install ansible-lint`

Run with `ansible-lint --profile min ../playbooks/`

Autofix with `ansible-lint --profile min --fix ../playbooks/`

We are currently using the [`min` profile](https://ansible.readthedocs.io/projects/lint/profiles/#min) which ensures that ensures that Ansible can load content.  We will gradually increase the strictness of rules as time allows for development.

Note that the linter with `--fix` may need to be run a few times in order to suss out all the issues.