# Development scripts

`generate_mgmt_bash_completion.py` regenerates the `mgmt` Bash completion template from the command tree reported by `mgmt --help`.

Run it from an environment where `mgmt` is installed and functional. The default output is the checked-in Ansible template:

```bash
python3 generate_mgmt_bash_completion.py
```

Use `--mgmt-cmd` to select another `mgmt` invocation and `--output` to write to a different destination. Review the generated template before committing it because the tool records the available commands and options from the chosen `mgmt` version.
