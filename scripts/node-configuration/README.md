# Node configuration scripts

`disable_ht.sh` enables or disables sibling CPU threads by writing to each CPU's `online` control file.

```bash
sudo ./disable_ht.sh 0
sudo ./disable_ht.sh 1
```

Use `0` to offline the script's selected sibling threads and `1` to online them again. This is a manual runtime change. For deployed cluster configuration, prefer the repository's Ansible hyperthreading role so the setting is managed consistently.
