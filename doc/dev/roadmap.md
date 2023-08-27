# Roadmap

The major features remaining to be implemented in this project are captured below. They are specified in terms of days to indicate the general level of effort, but this is not to be taken as a predictor of the date they will be completed.

```{uml}
@startgantt

hide footbox

[Filesystem note spec] as [fs_spec] lasts 10 days

[Low-level filesystem API] as [fs_api] lasts 10 days
note bottom
    Note.to_folder(), Note.from_folder(), Note.to_file(), Note.from_file()
end note

[Filesystem session] as [fs_session] lasts 20 days

[Virtual session] as [virt_session] lasts 10 days

[Session sync capability] as [sync] lasts 30 days

[Sync CLI] as [sync_cli] lasts 10 days

[fs_spec] -> [fs_api]
[fs_api] -> [fs_session]
[fs_session] -> [sync]
[virt_session] -> [sync]
[sync] -> [sync_cli]

@endgantt
```

## Todo list

The following is a generated list of implementation todos aggregated from the code.

```{todolist}
```
