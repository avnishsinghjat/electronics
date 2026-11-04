# System status

The start page shows whether the FabTrack server is healthy. It refreshes every
30 seconds; press **Refresh** to check immediately.

| Row | Meaning | What to do if not OK |
| --- | --- | --- |
| Overall | `ok` when the database and data directory are healthy, otherwise `degraded`. | Check the rows below. |
| Version | Installed FabTrack version. | Quote it when reporting problems. |
| Database | Whether PostgreSQL answers, with the round-trip time. | Ask the administrator to check the `postgres` service. |
| Free disk in data directory | Free / total space where photos, documents and KiCad files are stored. Turns amber below 1 GiB. | Free space or extend the disk before uploading photos. |
| LLM provider | Status of the local AI model. Shows "not configured" until the AI gateway is set up (Settings > AI Models, Phase 9). | Nothing yet. |
| Air-gapped mode | `on` means FabTrack never contacts the internet. | Leave on unless your administrator approved online models. |

The same information is available to scripts and monitoring at `GET /api/health`.
