# data/raw

Source chunk text files for the retained reference project (broaching machine / Fagor CNC 8070).

Each file is a structured plain-text export of a technical manual, segmented into chunks with page, section, and title metadata headers in the format:

```
--- Pages: [N-M] | Section: <section_name> | Title: <title> ---
<chunk text>
```

## Files

| File | Manual |
|---|---|
| `chunks_manual_instrucciones_a218.txt` | A218 broaching machine operating and maintenance manual |
| `chunks_8070_quick_ref.txt` | Fagor CNC 8070 quick reference |
| `chunks_8070_installation_manual.txt` | Fagor CNC 8070 installation manual |
| `chunks_man_8070_err.txt` | Fagor CNC 8070 error manual |
| `chunks_manual_variables_cnc_8070.txt` | Fagor CNC 8070 CNC variables manual |

Additional chunk files for supplementary manuals (remote modules, programming manual, etc.) may be present. These are not part of the primary accepted corpus but can be onboarded individually via `run_operational_pipeline.py --source-chunks`.

This directory is excluded from version control (`.gitignore`). Source files must be obtained from the original document set.
